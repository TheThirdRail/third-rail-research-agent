"""Duplicate and syndication detection for source candidates."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from src.utils.url_utils import extract_domain

logger = logging.getLogger(__name__)

_WIRE_MARKERS = {
    "associated press",
    "ap news",
    "(ap)",
    "reuters",
    "(reuters)",
    "agence france-presse",
    "(afp)",
    "united press international",
    "(upi)",
}
_SHINGLE_SIZE = 5
_SIMILARITY_THRESHOLD = 0.70
_TITLE_SIMILARITY_THRESHOLD = 0.85
_WIRE_MARKER_BODY_SCAN_CHARS = 500


@dataclass
class DuplicateResult:
    """Result of duplicate detection check."""

    is_duplicate: bool
    duplicate_of: str | None
    reason: str
    similarity: float


def check_duplicate(
    url: str,
    title: str,
    body_text: str,
    author: str | None,
    existing_sources: list[dict[str, str]],
) -> DuplicateResult:
    """Check if a candidate is a duplicate of existing sources."""
    candidate_domain = extract_domain(url)

    for existing in existing_sources:
        existing_domain = existing.get("domain", extract_domain(existing["url"]))

        if candidate_domain == existing_domain:
            return DuplicateResult(True, existing["url"], "same_domain", 1.0)

        if _is_wire_rewrite(
            author, body_text, existing.get("author", ""), existing.get("body_text", "")
        ):
            return DuplicateResult(True, existing["url"], "wire_rewrite", 0.95)

        title_sim = _title_similarity(title, existing.get("title", ""))
        if title_sim >= _TITLE_SIMILARITY_THRESHOLD:
            return DuplicateResult(True, existing["url"], "title_match", title_sim)

        if body_text and existing.get("body_text"):
            body_sim = _shingle_similarity(body_text, existing["body_text"])
            if body_sim >= _SIMILARITY_THRESHOLD:
                return DuplicateResult(
                    True, existing["url"], "near_duplicate", body_sim
                )

    return DuplicateResult(False, None, "", 0.0)


def _title_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _is_wire_rewrite(
    auth_a: str | None, body_a: str, auth_b: str | None, body_b: str
) -> bool:
    for marker in _WIRE_MARKERS:
        a_has = (auth_a and marker in auth_a.lower()) or (
            body_a and marker in body_a[:_WIRE_MARKER_BODY_SCAN_CHARS].lower()
        )
        b_has = (auth_b and marker in auth_b.lower()) or (
            body_b and marker in body_b[:_WIRE_MARKER_BODY_SCAN_CHARS].lower()
        )
        if a_has and b_has:
            return True
    return False


def _norm(text: str) -> str:
    text = re.sub(r"[^\w\s]", "", text.lower().strip())
    return re.sub(r"\s+", " ", text)


def _shingle_similarity(text_a: str, text_b: str) -> float:
    a, b = _norm(text_a), _norm(text_b)
    if len(a) < _SHINGLE_SIZE or len(b) < _SHINGLE_SIZE:
        return 0.0
    sa = _make_shingles(a)
    sb = _make_shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _make_shingles(text: str) -> set[str]:
    words = text.split()
    if len(words) < _SHINGLE_SIZE:
        return {text}
    return {
        " ".join(words[i : i + _SHINGLE_SIZE])
        for i in range(len(words) - _SHINGLE_SIZE + 1)
    }
