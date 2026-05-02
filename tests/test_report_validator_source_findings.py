"""Tests for source findings validation in report_validator."""

from src.schemas.analysis_report_sections import SourceFinding
from src.services.report_validator import validate_source_findings


def test_validate_source_findings_all_present():
    """No warnings when all retained sources have valid findings."""
    findings = [
        SourceFinding(source_id="S1", key_framing="Progressive framing"),
        SourceFinding(source_id="S2", key_framing="Conservative framing"),
        SourceFinding(source_id="S3", key_framing="Centrist take"),
    ]
    warnings = validate_source_findings(findings, retained_source_count=3)
    assert warnings == []


def test_validate_source_findings_missing():
    """Warns when a retained source has no finding."""
    findings = [
        SourceFinding(source_id="S1", key_framing="Some framing"),
        # S2 is missing
        SourceFinding(source_id="S3", key_framing="Other framing"),
    ]
    warnings = validate_source_findings(findings, retained_source_count=3)
    assert any("S2" in w for w in warnings)
    assert any("Missing" in w for w in warnings)


def test_validate_source_findings_invalid_id():
    """Warns when a finding references a nonexistent source ID."""
    findings = [
        SourceFinding(source_id="S1", key_framing="Some framing"),
        SourceFinding(source_id="S2", key_framing="Other framing"),
        SourceFinding(source_id="S99", key_framing="Mystery source"),
    ]
    warnings = validate_source_findings(findings, retained_source_count=2)
    assert any("S99" in w for w in warnings)
    assert any("Invalid" in w for w in warnings)


def test_validate_source_findings_duplicate():
    """Warns on duplicate source findings."""
    findings = [
        SourceFinding(source_id="S1", key_framing="First"),
        SourceFinding(source_id="S1", key_framing="Duplicate"),
        SourceFinding(source_id="S2", key_framing="Other"),
    ]
    warnings = validate_source_findings(findings, retained_source_count=2)
    assert any("Duplicate" in w for w in warnings)


def test_validate_source_findings_empty_key_framing():
    """Warns when key framing is empty or generic filler."""
    findings = [
        SourceFinding(source_id="S1", key_framing=""),
        SourceFinding(source_id="S2", key_framing="N/A"),
        SourceFinding(source_id="S3", key_framing="Real analysis here"),
    ]
    warnings = validate_source_findings(findings, retained_source_count=3)
    assert any("Empty or generic" in w for w in warnings)
    assert any("S1" in w for w in warnings)
    assert any("S2" in w for w in warnings)


def test_validate_source_findings_case_insensitive_id_match():
    """Source IDs should match case-insensitively."""
    findings = [
        SourceFinding(source_id="s1", key_framing="Lowercase ID"),
        SourceFinding(source_id="s2", key_framing="Another lowercase"),
    ]
    warnings = validate_source_findings(findings, retained_source_count=2)
    # Should not have missing warnings (case-insensitive match)
    assert not any("Missing" in w for w in warnings)


def test_validate_source_findings_accepts_dicts():
    """Works with dict inputs (not just Pydantic models)."""
    findings = [
        {"source_id": "S1", "key_framing": "Framing one"},
        {"source_id": "S2", "key_framing": "Framing two"},
    ]
    warnings = validate_source_findings(findings, retained_source_count=2)
    assert warnings == []


def test_validate_source_findings_empty_list():
    """All retained sources are reported as missing when no findings exist."""
    warnings = validate_source_findings([], retained_source_count=3)
    assert any("S1" in w for w in warnings)
    assert any("S2" in w for w in warnings)
    assert any("S3" in w for w in warnings)
