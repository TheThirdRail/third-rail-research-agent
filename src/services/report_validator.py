"""Validate report sources against preflighted URLs."""

from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlparse

from src.core.exceptions import SourceExtractionError


def validate_report_sources(report_markdown: str, allowed_urls: Iterable[str]) -> None:
    """Validate that report Source Matrix URLs are all preflighted.

    Raises SourceExtractionError if any URL is outside the allowed set.
    """
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
