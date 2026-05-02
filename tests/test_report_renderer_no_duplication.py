"""Regression tests for report rendering — no duplication, repair, structure."""

from src.services.report_renderer import ReportRenderer, ReportSections, SourceRecord


def _make_sources(count: int = 3) -> list[SourceRecord]:
    """Build a list of test source records."""
    return [
        SourceRecord(
            source_id=f"S{i}",
            title=f"Test Article {i}",
            domain=f"source{i}.com",
            url=f"https://source{i}.com/article-{i}",
            bias=(-2 + i),
            bias_label=["Left", "Center-Left", "Center", "Center-Right", "Right"][
                min(i, 4)
            ],
            confidence=0.85,
            key_framing=f"Framing for S{i}" if i % 2 == 1 else "",
            notable_claim=f"Claim for S{i}" if i % 2 == 0 else "",
        )
        for i in range(1, count + 1)
    ]


def _make_sections(**overrides: str) -> ReportSections:
    """Build a test report sections object."""
    defaults = {
        "executive_summary": "Summary of the story.",
        "what_happened": "The event occurred.",
        "agreed_facts": "Fact A. Fact B.",
    }
    defaults.update(overrides)
    return ReportSections(**defaults)


class TestNoReportDuplication:
    """Ensure rendered reports contain exactly one of each owned section."""

    def test_single_source_matrix(self):
        """Rendered report contains exactly one Source Matrix."""
        renderer = ReportRenderer()
        report = renderer.render(_make_sources(), _make_sections())
        assert report.count("## Source Matrix") == 1

    def test_single_all_sources_citations(self):
        """Rendered report contains exactly one All Sources & Citations."""
        renderer = ReportRenderer()
        report = renderer.render(_make_sources(), _make_sections())
        assert report.count("## All Sources & Citations") == 1

    def test_single_executive_summary(self):
        """Rendered report has exactly one Executive Summary section."""
        renderer = ReportRenderer()
        report = renderer.render(_make_sources(), _make_sections())
        assert report.count("## Executive Summary") == 1

    def test_no_duplicate_evidence_limitations(self):
        """Evidence limitations banner appears at most once."""
        renderer = ReportRenderer()
        report = renderer.render(
            _make_sources(),
            _make_sections(),
            missing_buckets=["far_left"],
        )
        assert report.count("## Evidence Limitations") == 1

    def test_footnotes_match_source_count(self):
        """Footnote count matches source count."""
        sources = _make_sources(4)
        renderer = ReportRenderer()
        report = renderer.render(sources, _make_sections())
        for i in range(1, 5):
            assert f"[^{i}]:" in report

    def test_no_markdown_headings_leak_from_sections(self):
        """Section content with headings is rejected by validator."""
        from src.services.report_validator import validate_structured_section_payload

        sections = _make_sections(
            executive_summary="## Source Matrix\n\nSneaky duplicate"
        )
        try:
            validate_structured_section_payload(sections)
            assert False, "Should have raised"
        except Exception:
            pass  # Expected


class TestSourceMatrixKeyFraming:
    """Source Matrix key framing / claim fields are populated or repaired."""

    def test_key_framing_populated_when_present(self):
        """Source Matrix shows key framing from source findings."""
        sources = [
            SourceRecord(
                source_id="S1",
                title="Article One",
                domain="example.com",
                url="https://example.com/1",
                bias=-2,
                bias_label="Left",
                confidence=0.9,
                key_framing="Progressive framing of event",
            )
        ]
        renderer = ReportRenderer()
        report = renderer.render(sources, _make_sections())
        assert "Progressive framing of event" in report

    def test_em_dash_fallback_when_no_framing(self):
        """Source Matrix shows — when no key framing or claim exists."""
        sources = [
            SourceRecord(
                source_id="S1",
                title="Article One",
                domain="example.com",
                url="https://example.com/1",
                bias=-2,
                bias_label="Left",
                confidence=0.9,
                key_framing="",
                notable_claim="",
            )
        ]
        renderer = ReportRenderer()
        report = renderer.render(sources, _make_sections())
        assert "— |" in report

    def test_repair_fills_empty_framing_from_title(self):
        """repair_source_findings populates empty framing from title."""
        sources = [
            SourceRecord(
                source_id="S1",
                title="Big Important Headline",
                domain="example.com",
                url="https://example.com/1",
                bias=0,
                bias_label="Center",
                confidence=0.8,
                key_framing="",
                notable_claim="",
            )
        ]
        renderer = ReportRenderer()
        repaired = renderer.repair_source_findings(sources)
        assert repaired[0].key_framing.startswith("[Auto]")
        assert "Big Important Headline" in repaired[0].key_framing

    def test_repair_does_not_overwrite_existing_framing(self):
        """repair_source_findings preserves existing key framing."""
        sources = [
            SourceRecord(
                source_id="S1",
                title="Article",
                domain="example.com",
                url="https://example.com/1",
                bias=0,
                bias_label="Center",
                confidence=0.8,
                key_framing="Real framing from crew",
                notable_claim="",
            )
        ]
        renderer = ReportRenderer()
        repaired = renderer.repair_source_findings(sources)
        assert repaired[0].key_framing == "Real framing from crew"

    def test_repair_preserves_notable_claim_without_framing(self):
        """When notable_claim exists but key_framing is empty, no repair."""
        sources = [
            SourceRecord(
                source_id="S1",
                title="Article",
                domain="example.com",
                url="https://example.com/1",
                bias=0,
                bias_label="Center",
                confidence=0.8,
                key_framing="",
                notable_claim="Important claim here",
            )
        ]
        renderer = ReportRenderer()
        repaired = renderer.repair_source_findings(sources)
        # Should NOT add auto-framing since notable_claim exists
        assert not repaired[0].key_framing.startswith("[Auto]")


class TestReportPayloadExtraction:
    """Crew payload parsing and section extraction."""

    def test_structured_sections_from_dict_payload(self):
        """AnalysisReportSections.from_crew_payload parses structured JSON."""
        from src.schemas.analysis_report_sections import AnalysisReportSections

        payload = {
            "sections": {
                "executive_summary": "Test summary",
                "what_happened": "Event description",
                "source_findings": [
                    {"source_id": "S1", "key_framing": "Left framing"},
                ],
            }
        }
        sections = AnalysisReportSections.from_crew_payload(payload)
        assert sections.executive_summary == "Test summary"
        assert len(sections.source_findings) == 1
        assert sections.source_findings[0].source_id == "S1"

    def test_markdown_crew_payload_is_rejected(self):
        """Crew payload containing Markdown headings is rejected."""
        from src.schemas.analysis_report_sections import AnalysisReportSections

        payload = {"report": "## Executive Summary\n\nSome text here."}
        try:
            AnalysisReportSections.from_crew_payload(payload)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass  # Expected
