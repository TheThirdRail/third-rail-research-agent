"""Validate report sources against preflighted URLs."""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlparse

from src.core.exceptions import SourceExtractionError

_CORE_SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "Executive Summary": re.compile(
        r"^#{1,6}\s*(?:\d+\.?\s*)?executive summary\b", re.IGNORECASE
    ),
    "Source Matrix": re.compile(
        r"^#{1,6}\s*(?:\d+\.?\s*)?source matrix\b", re.IGNORECASE
    ),
    "All Sources & Citations": re.compile(
        r"^#{1,6}\s*(?:\d+\.?\s*)?all sources\s*&\s*citations\b",
        re.IGNORECASE,
    ),
}
_GENERIC_FILLER = {"n/a", "none", "no framing", "see report", "tbd", ""}


def validate_report_sources(report_markdown: str, allowed_urls: Iterable[str]) -> None:
    """Validate that report Source Matrix URLs are all preflighted.

    Raises SourceExtractionError if any URL is outside the allowed set.
    """
    validate_unique_core_sections(report_markdown)

    normalized_allowed = {_normalize_url(url) for url in allowed_urls if url}
    extracted_urls = _extract_source_matrix_urls(report_markdown)

    if not extracted_urls:
        raise SourceExtractionError("Report is missing Source Matrix URLs.")

    unknown = [
        url for url in extracted_urls if _normalize_url(url) not in normalized_allowed
    ]

    if unknown:
        raise SourceExtractionError(
            "Report includes sources not in preflight list: " + ", ".join(unknown[:5])
        )

    normalized_matrix = {_normalize_url(url) for url in extracted_urls if url}
    footnote_urls = _extract_footnote_urls(report_markdown)
    unknown_footnotes = [
        url for url in footnote_urls if _normalize_url(url) not in normalized_matrix
    ]

    if unknown_footnotes:
        raise SourceExtractionError(
            "Report footnotes reference URLs outside Source Matrix: "
            + ", ".join(unknown_footnotes[:5])
        )


def validate_unique_core_sections(report_markdown: str) -> None:
    """Ensure renderer-owned core sections occur at most once."""
    counts = _core_section_counts(report_markdown)
    duplicates = [name for name, count in counts.items() if count > 1]
    if duplicates:
        raise SourceExtractionError(
            "Report includes duplicate renderer-owned sections: "
            + ", ".join(duplicates)
        )


def validate_structured_section_payload(sections: object) -> None:
    """Reject section content that already contains renderer-owned headings."""
    if hasattr(sections, "model_dump"):
        data = sections.model_dump()
    elif hasattr(sections, "__dict__"):
        data = vars(sections)
    elif isinstance(sections, dict):
        data = sections
    else:
        return

    violations: list[str] = []
    for field_name, value in data.items():
        values: list[str] = []
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, list):
            values = [item for item in value if isinstance(item, str)]
        for text in values:
            for section_name, pattern in _CORE_SECTION_PATTERNS.items():
                if any(pattern.match(line.strip()) for line in text.splitlines()):
                    violations.append(f"{field_name} contains {section_name}")

    if violations:
        raise SourceExtractionError(
            "Structured report sections must not include renderer-owned headings: "
            + "; ".join(violations[:5])
        )


def _extract_source_matrix_urls(report_markdown: str) -> list[str]:
    lines = report_markdown.splitlines()
    start_idx = None

    for i, line in enumerate(lines):
        if re.match(r"^#{1,6}\s*\d*\.?\s*source matrix", line, re.IGNORECASE):
            start_idx = i
            break

    if start_idx is None:
        return []

    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        if re.match(r"^#{1,6}\s+", lines[j]):
            end_idx = j
            break

    section = "\n".join(lines[start_idx:end_idx])
    urls = re.findall(r"\[[^\]]+\]\((https?://[^)]+)\)", section)
    return urls


def _core_section_counts(report_markdown: str) -> dict[str, int]:
    counts = dict.fromkeys(_CORE_SECTION_PATTERNS, 0)
    for raw_line in report_markdown.splitlines():
        line = raw_line.strip()
        for name, pattern in _CORE_SECTION_PATTERNS.items():
            if pattern.match(line):
                counts[name] += 1
    return counts


def _extract_footnote_urls(report_markdown: str) -> list[str]:
    """Extract URLs from GFM footnote definitions, if present."""
    urls: list[str] = []
    for line in report_markdown.splitlines():
        if not re.match(r"^\[\^\d+\]:", line.strip()):
            continue
        match = re.search(r"(https?://\S+)", line)
        if not match:
            continue
        urls.append(match.group(1).rstrip(").,;"))
    return urls


def _normalize_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
    except Exception:
        return url.lower().rstrip("/")


def validate_evidence_limits(
    report_markdown: str, missing_buckets: list[str]
) -> list[str]:
    """Validate that missing-bucket evidence limits banner is present.

    Returns list of validation warnings (empty if all checks pass).
    """
    warnings: list[str] = []

    if missing_buckets and "evidence limitation" not in report_markdown.lower():
        warnings.append(
            f"Report is missing evidence limitations banner. "
            f"Missing buckets: {', '.join(missing_buckets)}"
        )

    return warnings


def validate_orphaned_citations(report_markdown: str) -> list[str]:
    """Check for citation markers that don't have corresponding footnotes.

    Returns list of orphaned citation markers.
    """
    # Find all citation markers used in the text
    text_citations = set(re.findall(r"\[\^(\d+)\]", report_markdown))

    # Find all footnote definitions
    footnote_defs = set()
    for line in report_markdown.splitlines():
        match = re.match(r"^\[\^(\d+)\]:", line.strip())
        if match:
            footnote_defs.add(match.group(1))

    orphaned = text_citations - footnote_defs
    warnings = []
    if orphaned:
        warnings.append(
            f"Orphaned citation markers without footnote definitions: "
            f"{', '.join(f'[^{n}]' for n in sorted(orphaned, key=int))}"
        )

    return warnings


def validate_source_findings(
    source_findings: list[object],
    retained_source_count: int,
) -> list[str]:
    """Validate source findings completeness and correctness.

    Checks that:
    - Every retained source has a source finding.
    - Source IDs match expected S1, S2, etc. pattern.
    - Key framing is not empty or generic filler.
    - No duplicate source IDs exist.

    Args:
        source_findings: List of SourceFinding objects (or dicts).
        retained_source_count: Number of retained sources in the report.

    Returns:
        List of validation warning strings (empty if all checks pass).
    """
    warnings: list[str] = []
    expected_ids = {f"S{i}" for i in range(1, retained_source_count + 1)}

    # Normalize findings to dicts
    findings: list[dict[str, str]] = []
    for f in source_findings:
        if hasattr(f, "model_dump"):
            findings.append(f.model_dump())  # type: ignore[union-attr]
        elif isinstance(f, dict):
            findings.append(f)

    # Check for missing source findings
    found_ids: list[str] = []
    for finding in findings:
        sid = str(finding.get("source_id", "")).strip().upper()
        found_ids.append(sid)

    found_set = set(found_ids)
    missing = expected_ids - found_set
    if missing:
        warnings.append(f"Missing source findings for: {', '.join(sorted(missing))}")

    # Check for invalid source IDs
    invalid = found_set - expected_ids
    if invalid:
        warnings.append(f"Invalid source IDs in findings: {', '.join(sorted(invalid))}")

    # Check for duplicate source IDs
    seen: set[str] = set()
    duplicates: list[str] = []
    for sid in found_ids:
        if sid in seen:
            duplicates.append(sid)
        seen.add(sid)
    if duplicates:
        warnings.append(f"Duplicate source findings: {', '.join(duplicates)}")

    # Check for empty key framing
    empty_framing: list[str] = []
    for finding in findings:
        sid = str(finding.get("source_id", "")).strip().upper()
        framing = str(finding.get("key_framing", "")).strip()
        if framing.lower() in _GENERIC_FILLER:
            empty_framing.append(sid)
    if empty_framing:
        warnings.append(
            f"Empty or generic key framing for: {', '.join(sorted(empty_framing))}"
        )

    return warnings
