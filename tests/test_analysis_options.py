"""Tests for per-run analysis options.

Verifies that AnalysisOptions overrides resolve correctly against
Settings defaults, that options are persisted in AnalysisRun, and
that CLI flags build AnalysisOptions correctly.
"""

import json
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core import config as core_config
from src.database.models import AnalysisRun, Base, Source
from src.schemas.analysis_options import AnalysisOptions
from src.services.analysis_service import AnalysisService
from src.services.source_aggregator_service import (
    SourceAggregatorService,
    SourceCandidate,
)
from src.tools.bias_classifier import BiasResult
from src.tools.web_search import SearchResult


# ---------------------------------------------------------------------------
# AnalysisOptions schema tests
# ---------------------------------------------------------------------------


class TestAnalysisOptionsSchema:
    """Test that AnalysisOptions correctly represents per-run overrides."""

    def test_all_fields_default_to_none(self):
        opts = AnalysisOptions()
        dump = opts.model_dump(exclude_none=True)
        assert dump == {}

    def test_partial_override(self):
        opts = AnalysisOptions(
            strict_bucket_enforcement=False,
            embedding_provider="lmstudio",
        )
        dump = opts.model_dump(exclude_none=True)
        assert dump == {
            "strict_bucket_enforcement": False,
            "embedding_provider": "lmstudio",
        }

    def test_full_override(self):
        opts = AnalysisOptions(
            strict_bucket_enforcement=True,
            required_bucket_groups=["left_side", "right_side"],
            preferred_bucket_groups=["center"],
            enable_semantic_memory=True,
            enable_semantic_candidate_scoring=True,
            enable_semantic_query_expansion=True,
            enable_visual_evidence_resolution=True,
            enable_screenshot_capture=True,
            embedding_provider="lmstudio",
            embedding_model="qwen3-embedding-8b",
            vector_store="lancedb",
        )
        dump = opts.model_dump(exclude_none=True)
        assert len(dump) == 11

    def test_json_round_trip(self):
        opts = AnalysisOptions(
            enable_semantic_memory=True,
            vector_store="lancedb",
        )
        json_str = opts.model_dump_json()
        restored = AnalysisOptions.model_validate_json(json_str)
        assert restored.enable_semantic_memory is True
        assert restored.vector_store == "lancedb"


# ---------------------------------------------------------------------------
# _analysis_options_snapshot resolution tests
# ---------------------------------------------------------------------------


class TestOptionsSnapshotResolution:
    """Test that _analysis_options_snapshot merges options with settings defaults."""

    def test_no_options_uses_settings_defaults(self, monkeypatch):
        monkeypatch.setattr(core_config.settings, "strict_bucket_enforcement", True)
        monkeypatch.setattr(core_config.settings, "semantic_memory_enabled", False)
        monkeypatch.setattr(core_config.settings, "semantic_candidate_scoring_enabled", False)
        monkeypatch.setattr(core_config.settings, "semantic_query_expansion_enabled", False)
        monkeypatch.setattr(core_config.settings, "screenshot_capture_enabled", False)
        monkeypatch.setattr(core_config.settings, "embedding_provider", "fake")
        monkeypatch.setattr(core_config.settings, "embedding_model", "fake-hash-v1")
        monkeypatch.setattr(core_config.settings, "semantic_vector_store", "none")

        snapshot = AnalysisService._analysis_options_snapshot(None)

        assert snapshot["strict_bucket_enforcement"] is True
        assert snapshot["enable_semantic_memory"] is False
        assert snapshot["enable_semantic_candidate_scoring"] is False
        assert snapshot["enable_screenshot_capture"] is False
        assert snapshot["embedding_provider"] == "fake"
        assert snapshot["embedding_model"] == "fake-hash-v1"
        assert snapshot["vector_store"] == "none"

    def test_options_override_settings(self, monkeypatch):
        monkeypatch.setattr(core_config.settings, "strict_bucket_enforcement", True)
        monkeypatch.setattr(core_config.settings, "semantic_memory_enabled", False)
        monkeypatch.setattr(core_config.settings, "embedding_provider", "fake")
        monkeypatch.setattr(core_config.settings, "embedding_model", "fake-hash-v1")
        monkeypatch.setattr(core_config.settings, "semantic_vector_store", "none")
        monkeypatch.setattr(core_config.settings, "screenshot_capture_enabled", False)
        monkeypatch.setattr(core_config.settings, "semantic_candidate_scoring_enabled", False)
        monkeypatch.setattr(core_config.settings, "semantic_query_expansion_enabled", False)

        opts = AnalysisOptions(
            strict_bucket_enforcement=False,
            enable_semantic_memory=True,
            embedding_provider="lmstudio",
            embedding_model="qwen3-embedding-8b",
            vector_store="lancedb",
        )
        snapshot = AnalysisService._analysis_options_snapshot(opts)

        assert snapshot["strict_bucket_enforcement"] is False
        assert snapshot["enable_semantic_memory"] is True
        assert snapshot["embedding_provider"] == "lmstudio"
        assert snapshot["embedding_model"] == "qwen3-embedding-8b"
        assert snapshot["vector_store"] == "lancedb"

    def test_partial_options_fall_through_to_settings(self, monkeypatch):
        monkeypatch.setattr(core_config.settings, "strict_bucket_enforcement", True)
        monkeypatch.setattr(core_config.settings, "semantic_memory_enabled", True)
        monkeypatch.setattr(core_config.settings, "embedding_provider", "lmstudio")
        monkeypatch.setattr(core_config.settings, "embedding_model", "some-model")
        monkeypatch.setattr(core_config.settings, "semantic_vector_store", "lancedb")
        monkeypatch.setattr(core_config.settings, "screenshot_capture_enabled", False)
        monkeypatch.setattr(core_config.settings, "semantic_candidate_scoring_enabled", False)
        monkeypatch.setattr(core_config.settings, "semantic_query_expansion_enabled", False)

        # Only override strict; rest should come from settings
        opts = AnalysisOptions(strict_bucket_enforcement=False)
        snapshot = AnalysisService._analysis_options_snapshot(opts)

        assert snapshot["strict_bucket_enforcement"] is False
        assert snapshot["enable_semantic_memory"] is True
        assert snapshot["embedding_provider"] == "lmstudio"
        assert snapshot["embedding_model"] == "some-model"
        assert snapshot["vector_store"] == "lancedb"

    def test_required_bucket_groups_from_csv_setting(self, monkeypatch):
        monkeypatch.setattr(core_config.settings, "required_bucket_groups", "left_side,right_side")
        monkeypatch.setattr(core_config.settings, "exact_center_preferred", True)
        monkeypatch.setattr(core_config.settings, "strict_bucket_enforcement", True)
        monkeypatch.setattr(core_config.settings, "semantic_memory_enabled", False)
        monkeypatch.setattr(core_config.settings, "semantic_candidate_scoring_enabled", False)
        monkeypatch.setattr(core_config.settings, "semantic_query_expansion_enabled", False)
        monkeypatch.setattr(core_config.settings, "screenshot_capture_enabled", False)
        monkeypatch.setattr(core_config.settings, "embedding_provider", "fake")
        monkeypatch.setattr(core_config.settings, "embedding_model", "fake-hash-v1")
        monkeypatch.setattr(core_config.settings, "semantic_vector_store", "none")

        snapshot = AnalysisService._analysis_options_snapshot(None)

        assert snapshot["required_bucket_groups"] == ["left_side", "right_side"]
        assert snapshot["preferred_bucket_groups"] == ["center"]

    def test_required_bucket_groups_override(self, monkeypatch):
        monkeypatch.setattr(core_config.settings, "required_bucket_groups", "left_side,right_side")
        monkeypatch.setattr(core_config.settings, "exact_center_preferred", True)
        monkeypatch.setattr(core_config.settings, "strict_bucket_enforcement", True)
        monkeypatch.setattr(core_config.settings, "semantic_memory_enabled", False)
        monkeypatch.setattr(core_config.settings, "semantic_candidate_scoring_enabled", False)
        monkeypatch.setattr(core_config.settings, "semantic_query_expansion_enabled", False)
        monkeypatch.setattr(core_config.settings, "screenshot_capture_enabled", False)
        monkeypatch.setattr(core_config.settings, "embedding_provider", "fake")
        monkeypatch.setattr(core_config.settings, "embedding_model", "fake-hash-v1")
        monkeypatch.setattr(core_config.settings, "semantic_vector_store", "none")

        opts = AnalysisOptions(
            required_bucket_groups=["center"],
            preferred_bucket_groups=["left_side"],
        )
        snapshot = AnalysisService._analysis_options_snapshot(opts)

        assert snapshot["required_bucket_groups"] == ["center"]
        assert snapshot["preferred_bucket_groups"] == ["left_side"]


# ---------------------------------------------------------------------------
# Options persistence in AnalysisRun
# ---------------------------------------------------------------------------


def _make_test_db(tmp_path: Path):
    """Create an in-memory test database and session factory."""
    db_path = tmp_path / "options_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


class DummySearcher:
    def news_search(self, query, max_results=10, time_range="w"):
        return [
            SearchResult("CNN covers the event", "https://cnn.com/story", "left coverage", "cnn"),
            SearchResult("Fox covers the event", "https://foxnews.com/story", "right coverage", "fox"),
            SearchResult("Unrelated item", "https://sports.example.com/game", "sports", "sports"),
        ]

    def web_search(self, query, max_results=10):
        return []


def _bias_for(domain):
    mapping = {
        "reuters.com": (0, "Center"),
        "cnn.com": (-2, "Lean Left"),
        "foxnews.com": (3, "Right"),
        "sports.example.com": (0, "Center"),
    }
    bias, label = mapping.get(domain, (0, "Center"))
    return BiasResult(
        domain=domain,
        bias=bias,
        bias_label=label,
        confidence=1.0,
        method="dataset",
        factual_rating="high",
        category="mainstream",
    )


def _fake_extract_url(self, url, require_success=False):
    domain = urlparse(url).netloc.replace("www.", "")
    if domain == "sports.example.com":
        text = "Football playoffs and player trades dominated the desk."
        title = "Sports roundup"
    elif domain == "cnn.com":
        text = (
            "Test story about politics and governance. "
            "CNN emphasized regulatory concerns and civil-liberties."
        )
        title = "CNN covers the event"
    elif domain == "foxnews.com":
        text = (
            "Test story about politics and governance. "
            "Fox News focused on business compliance and costs."
        )
        title = "Fox covers the event"
    else:
        text = (
            "Test story about politics and governance. "
            "The order sets new standards for agencies."
        )
        title = "Story from " + domain
    return SourceCandidate(
        url=url,
        domain=domain,
        title=title,
        published_date=None,
        author=None,
        full_text=text * 8,
        extraction_error=None,
        extractor_method="test_extractor",
        http_status=200,
        bias_result=_bias_for(domain),
    )


def _apply_common_monkeypatches(monkeypatch, session_factory):
    """Wire up common analysis service monkeypatches."""
    monkeypatch.setattr(
        "src.services.analysis_service.get_session",
        lambda: session_factory(),
    )
    monkeypatch.setattr(
        SourceAggregatorService, "_init_searcher", lambda self: DummySearcher()
    )
    monkeypatch.setattr(SourceAggregatorService, "_extract_url", _fake_extract_url)
    monkeypatch.setattr(
        "src.services.rss_retrieval_service.RssRetrievalService.search",
        lambda self, query, *, domains, max_results=8: [],
    )
    monkeypatch.setattr(
        "src.services.rss_retrieval_service.RssRetrievalService.search_story",
        lambda self, story_packet, *, domains=None, max_results=8: [],
    )
    monkeypatch.setattr(
        "src.services.analysis_service.run_analysis",
        lambda description, url=None, prefetched_sources=None, visual_evidence_context=None: {
            "sections": {
                "executive_summary": "Summary.",
                "what_happened": "Event occurred.",
                "agreed_facts": "S1 and S2 agree.",
                "source_findings": [
                    {
                        "source_id": "S1",
                        "key_framing": "Left framing.",
                        "notable_claim": "Claim.",
                        "evidence_snippet": "Evidence.",
                        "confidence": 0.8,
                    }
                ],
            },
            "report": "",
            "story_description": description,
            "story_url": url,
        },
    )


def test_options_persisted_to_analysis_run(monkeypatch, tmp_path):
    """Per-run options are serialized into analysis_runs.options_snapshot_json."""
    session_factory = _make_test_db(tmp_path)
    _apply_common_monkeypatches(monkeypatch, session_factory)

    opts = AnalysisOptions(
        strict_bucket_enforcement=False,
        enable_semantic_memory=True,
        embedding_provider="lmstudio",
    )
    service = AnalysisService()
    result = service.analyze("Test story about politics", "https://reuters.com/seed", options=opts)

    with session_factory() as session:
        run = (
            session.query(AnalysisRun)
            .filter(AnalysisRun.story_id == result["story_id"])
            .one()
        )
        snapshot = json.loads(run.options_snapshot_json)

    assert snapshot["strict_bucket_enforcement"] is False
    assert snapshot["enable_semantic_memory"] is True
    assert snapshot["embedding_provider"] == "lmstudio"


def test_default_options_persisted_when_no_overrides(monkeypatch, tmp_path):
    """When no AnalysisOptions are passed, settings defaults are still persisted."""
    session_factory = _make_test_db(tmp_path)
    _apply_common_monkeypatches(monkeypatch, session_factory)

    service = AnalysisService()
    result = service.analyze("Test story", "https://reuters.com/seed")

    with session_factory() as session:
        run = (
            session.query(AnalysisRun)
            .filter(AnalysisRun.story_id == result["story_id"])
            .one()
        )
        snapshot = json.loads(run.options_snapshot_json)

    # Snapshot should contain all resolved fields
    assert "strict_bucket_enforcement" in snapshot
    assert "enable_semantic_memory" in snapshot
    assert "embedding_provider" in snapshot
    assert "vector_store" in snapshot


def test_analysis_result_includes_options_snapshot(monkeypatch, tmp_path):
    """The analysis result dict includes the resolved options snapshot."""
    session_factory = _make_test_db(tmp_path)
    _apply_common_monkeypatches(monkeypatch, session_factory)

    opts = AnalysisOptions(vector_store="lancedb")
    service = AnalysisService()
    result = service.analyze("Test story", "https://reuters.com/seed", options=opts)

    assert "analysis_options" in result
    assert result["analysis_options"]["vector_store"] == "lancedb"


def test_diagnostics_include_options_snapshot(monkeypatch, tmp_path):
    """get_diagnostics returns the options snapshot from the analysis run."""
    session_factory = _make_test_db(tmp_path)
    _apply_common_monkeypatches(monkeypatch, session_factory)

    opts = AnalysisOptions(
        enable_screenshot_capture=True,
        embedding_model="test-model",
    )
    service = AnalysisService()
    result = service.analyze("Test story", "https://reuters.com/seed", options=opts)

    diagnostics = AnalysisService().get_diagnostics(result["story_id"])
    assert diagnostics is not None
    run_opts = diagnostics["analysis_run"]["options_snapshot"]
    assert run_opts["enable_screenshot_capture"] is True
    assert run_opts["embedding_model"] == "test-model"


# ---------------------------------------------------------------------------
# CLI option flags
# ---------------------------------------------------------------------------


class TestCLIOptionFlags:
    """Test that CLI flags are correctly wired to AnalysisOptions."""

    def test_analyze_help_shows_option_flags(self):
        from src.cli import main as cli_main

        result = CliRunner().invoke(cli_main.cli, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "--strict" in result.output
        assert "--no-strict" in result.output
        assert "--semantic-memory" in result.output
        assert "--semantic-scoring" in result.output
        assert "--visual-evidence" in result.output
        assert "--screenshot" in result.output
        assert "--embedding-provider" in result.output
        assert "--embedding-model" in result.output
        assert "--vector-store" in result.output

    def test_cli_flags_build_analysis_options(self, monkeypatch, tmp_path):
        """CLI flags pass through to AnalysisService.analyze() as options."""
        from src.cli import main as cli_main

        captured_options = []

        def fake_analyze(self, description, url=None, options=None):
            captured_options.append(options)
            return {
                "story_id": "test-id",
                "report": "# Report",
                "status": "analyzed",
            }

        monkeypatch.setattr(cli_main, "init_db", lambda: None)
        monkeypatch.setattr(AnalysisService, "analyze", fake_analyze)

        result = CliRunner().invoke(
            cli_main.cli,
            [
                "analyze",
                "--describe", "Test story",
                "--no-strict",
                "--semantic-memory",
                "--embedding-provider", "lmstudio",
                "--vector-store", "lancedb",
            ],
        )

        assert result.exit_code == 0
        assert len(captured_options) == 1
        opts = captured_options[0]
        assert opts is not None
        assert opts.strict_bucket_enforcement is False
        assert opts.enable_semantic_memory is True
        assert opts.embedding_provider == "lmstudio"
        assert opts.vector_store == "lancedb"

    def test_cli_no_flags_passes_none_options(self, monkeypatch):
        """When no option flags are given, options is None."""
        from src.cli import main as cli_main

        captured_options = []

        def fake_analyze(self, description, url=None, options=None):
            captured_options.append(options)
            return {
                "story_id": "test-id",
                "report": "# Report",
                "status": "analyzed",
            }

        monkeypatch.setattr(cli_main, "init_db", lambda: None)
        monkeypatch.setattr(AnalysisService, "analyze", fake_analyze)

        result = CliRunner().invoke(
            cli_main.cli,
            ["analyze", "--describe", "Test story"],
        )

        assert result.exit_code == 0
        assert len(captured_options) == 1
        assert captured_options[0] is None
