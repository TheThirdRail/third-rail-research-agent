"""Tests for Settings.validate_feature_dependencies() and health check readiness.

Covers all known validation paths including semantic, embedding, vector store,
screenshot capture, OCR, and bucket enforcement configurations.
"""

import pytest

from src.core.config import Settings


def _make_settings(**overrides) -> Settings:
    """Build a minimal Settings object for validation testing.

    Uses safe defaults so tests only need to specify the fields under test.
    """
    defaults = {
        "app_env": "test",
        "llm_provider": "lmstudio",
        "semantic_candidate_scoring_enabled": False,
        "semantic_memory_enabled": False,
        "semantic_query_expansion_enabled": False,
        "embedding_provider": "fake",
        "embedding_model": "fake-hash-v1",
        "semantic_vector_store": "none",
        "screenshot_capture_enabled": False,
        "screenshot_ocr_enabled": False,
        "screenshot_ocr_engine": "pytesseract",
        "strict_bucket_enforcement": True,
        "retained_source_max": 5,
        "semantic_fail_open": True,
    }
    defaults.update(overrides)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# Semantic candidate scoring + embedding provider
# ---------------------------------------------------------------------------


class TestSemanticScoringValidation:

    def test_no_warning_when_scoring_disabled(self):
        s = _make_settings(semantic_candidate_scoring_enabled=False)
        assert not any("SEMANTIC_CANDIDATE_SCORING" in w for w in s.validate_feature_dependencies())

    def test_warning_when_scoring_enabled_with_fake_embeddings(self):
        s = _make_settings(
            semantic_candidate_scoring_enabled=True,
            embedding_provider="fake",
        )
        warnings = s.validate_feature_dependencies()
        assert any(
            "SEMANTIC_CANDIDATE_SCORING_ENABLED=true" in w and "fake" in w
            for w in warnings
        )

    def test_no_warning_when_scoring_enabled_with_real_embeddings(self):
        s = _make_settings(
            semantic_candidate_scoring_enabled=True,
            embedding_provider="lmstudio",
            embedding_model="some-model",
        )
        warnings = s.validate_feature_dependencies()
        assert not any("SEMANTIC_CANDIDATE_SCORING_ENABLED=true" in w and "fake" in w for w in warnings)


# ---------------------------------------------------------------------------
# Semantic memory + embedding provider
# ---------------------------------------------------------------------------


class TestSemanticMemoryValidation:

    def test_no_warning_when_memory_disabled(self):
        s = _make_settings(semantic_memory_enabled=False)
        assert not any("SEMANTIC_MEMORY_ENABLED" in w for w in s.validate_feature_dependencies())

    def test_warning_when_memory_enabled_with_fake_embeddings(self):
        s = _make_settings(
            semantic_memory_enabled=True,
            embedding_provider="fake",
        )
        warnings = s.validate_feature_dependencies()
        assert any(
            "SEMANTIC_MEMORY_ENABLED=true" in w and "fake" in w
            for w in warnings
        )


# ---------------------------------------------------------------------------
# Semantic query expansion + LLM
# ---------------------------------------------------------------------------


class TestSemanticQueryExpansionValidation:

    def test_warning_when_expansion_enabled_without_llm(self):
        s = _make_settings(
            semantic_query_expansion_enabled=True,
            llm_provider="",
        )
        warnings = s.validate_feature_dependencies()
        assert any("SEMANTIC_QUERY_EXPANSION_ENABLED=true" in w for w in warnings)

    def test_no_warning_when_expansion_enabled_with_llm(self):
        s = _make_settings(
            semantic_query_expansion_enabled=True,
            llm_provider="lmstudio",
        )
        warnings = s.validate_feature_dependencies()
        assert not any("SEMANTIC_QUERY_EXPANSION_ENABLED=true" in w for w in warnings)


# ---------------------------------------------------------------------------
# Embedding model mismatch
# ---------------------------------------------------------------------------


class TestEmbeddingModelValidation:

    def test_warning_when_real_provider_with_fake_model(self):
        s = _make_settings(
            embedding_provider="lmstudio",
            embedding_model="fake-hash-v1",
        )
        warnings = s.validate_feature_dependencies()
        assert any("fake-hash-v1" in w for w in warnings)

    def test_no_warning_when_fake_provider_with_fake_model(self):
        s = _make_settings(
            embedding_provider="fake",
            embedding_model="fake-hash-v1",
        )
        warnings = s.validate_feature_dependencies()
        assert not any("fake-hash-v1" in w and "EMBEDDING_PROVIDER" in w for w in warnings)

    def test_no_warning_when_real_provider_with_real_model(self):
        s = _make_settings(
            embedding_provider="lmstudio",
            embedding_model="qwen3-embedding-8b",
        )
        warnings = s.validate_feature_dependencies()
        assert not any("fake-hash-v1" in w for w in warnings)


# ---------------------------------------------------------------------------
# Vector store validation
# ---------------------------------------------------------------------------


class TestVectorStoreValidation:

    def test_no_warning_when_vector_store_none(self):
        s = _make_settings(semantic_vector_store="none")
        warnings = s.validate_feature_dependencies()
        assert not any("SEMANTIC_VECTOR_STORE=lancedb" in w for w in warnings)

    def test_warning_when_lancedb_selected_but_package_missing(self, monkeypatch):
        """Simulate lancedb import failure."""
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "lancedb":
                raise ImportError("No module named 'lancedb'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        s = _make_settings(semantic_vector_store="lancedb")
        warnings = s.validate_feature_dependencies()
        assert any("SEMANTIC_VECTOR_STORE=lancedb" in w and "not installed" in w for w in warnings)

    def test_warning_when_lancedb_set_but_semantic_features_disabled(self):
        s = _make_settings(
            semantic_vector_store="lancedb",
            semantic_memory_enabled=False,
            semantic_candidate_scoring_enabled=False,
        )
        warnings = s.validate_feature_dependencies()
        assert any("will not be used" in w for w in warnings)

    def test_no_warning_when_lancedb_set_with_semantic_memory_enabled(self):
        s = _make_settings(
            semantic_vector_store="lancedb",
            semantic_memory_enabled=True,
            embedding_provider="lmstudio",
            embedding_model="some-model",
        )
        warnings = s.validate_feature_dependencies()
        assert not any("will not be used" in w for w in warnings)


# ---------------------------------------------------------------------------
# Screenshot capture validation
# ---------------------------------------------------------------------------


class TestScreenshotCaptureValidation:

    def test_no_warning_when_screenshot_disabled(self):
        s = _make_settings(screenshot_capture_enabled=False)
        warnings = s.validate_feature_dependencies()
        assert not any("SCREENSHOT_CAPTURE_ENABLED" in w for w in warnings)

    def test_warning_when_screenshot_enabled_but_playwright_missing(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "playwright":
                raise ImportError("No module named 'playwright'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        s = _make_settings(screenshot_capture_enabled=True)
        warnings = s.validate_feature_dependencies()
        assert any(
            "SCREENSHOT_CAPTURE_ENABLED=true" in w and "playwright" in w.lower()
            for w in warnings
        )


# ---------------------------------------------------------------------------
# OCR validation
# ---------------------------------------------------------------------------


class TestOCRValidation:

    def test_no_warning_when_ocr_disabled(self):
        s = _make_settings(screenshot_ocr_enabled=False)
        warnings = s.validate_feature_dependencies()
        assert not any("SCREENSHOT_OCR" in w for w in warnings)

    def test_warning_when_ocr_enabled_without_screenshot_capture(self):
        s = _make_settings(
            screenshot_ocr_enabled=True,
            screenshot_capture_enabled=False,
        )
        warnings = s.validate_feature_dependencies()
        assert any(
            "SCREENSHOT_OCR_ENABLED=true" in w and "SCREENSHOT_CAPTURE_ENABLED=false" in w
            for w in warnings
        )

    def test_warning_when_ocr_engine_unsupported(self):
        s = _make_settings(
            screenshot_ocr_enabled=True,
            screenshot_capture_enabled=True,
            screenshot_ocr_engine="unsupported_engine",
        )
        warnings = s.validate_feature_dependencies()
        assert any("unsupported_engine" in w for w in warnings)

    def test_warning_when_pytesseract_package_missing(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pytesseract":
                raise ImportError("No module named 'pytesseract'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        s = _make_settings(
            screenshot_ocr_enabled=True,
            screenshot_capture_enabled=True,
            screenshot_ocr_engine="pytesseract",
        )
        warnings = s.validate_feature_dependencies()
        assert any("pytesseract" in w and "not installed" in w for w in warnings)


# ---------------------------------------------------------------------------
# Bucket enforcement validation
# ---------------------------------------------------------------------------


class TestBucketEnforcementValidation:

    def test_warning_when_strict_with_too_few_sources(self):
        s = _make_settings(
            strict_bucket_enforcement=True,
            retained_source_max=1,
        )
        warnings = s.validate_feature_dependencies()
        assert any("RETAINED_SOURCE_MAX" in w for w in warnings)

    def test_no_warning_when_strict_with_enough_sources(self):
        s = _make_settings(
            strict_bucket_enforcement=True,
            retained_source_max=5,
        )
        warnings = s.validate_feature_dependencies()
        assert not any("RETAINED_SOURCE_MAX" in w for w in warnings)

    def test_no_warning_when_not_strict(self):
        s = _make_settings(
            strict_bucket_enforcement=False,
            retained_source_max=1,
        )
        warnings = s.validate_feature_dependencies()
        assert not any("RETAINED_SOURCE_MAX" in w for w in warnings)


# ---------------------------------------------------------------------------
# Compound / edge cases
# ---------------------------------------------------------------------------


class TestCompoundValidation:

    def test_clean_config_produces_no_warnings(self):
        """A fully default config should produce no warnings."""
        s = _make_settings()
        warnings = s.validate_feature_dependencies()
        assert warnings == []

    def test_multiple_issues_produce_multiple_warnings(self):
        s = _make_settings(
            semantic_candidate_scoring_enabled=True,
            semantic_memory_enabled=True,
            embedding_provider="fake",
            screenshot_ocr_enabled=True,
            screenshot_capture_enabled=False,
        )
        warnings = s.validate_feature_dependencies()
        # Should have at least: scoring+fake, memory+fake, OCR without capture
        assert len(warnings) >= 3
