"""AllSides lookup helper for bias ratings."""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Mapping

import httpx

from src.tools.bias_classifier import BIAS_LABELS, BiasResult

logger = logging.getLogger(__name__)


class AllSidesClient:
    """Best-effort AllSides lookup by domain."""

    BASE_URL = "https://www.allsides.com"
    SEARCH_PATH = "/search"

    _LABEL_TO_SCORE = {
        "far left": -4,
        "left": -3,
        "lean left": -2,
        "center": 0,
        "lean right": 2,
        "right": 3,
        "far right": 4,
        "mixed": 0,
    }

    def lookup_domain(self, domain: str, timeout: float = 10.0) -> BiasResult | None:
        """Lookup a domain in AllSides.

        Returns a BiasResult if found, otherwise None.
        """
        domain = domain.lower().replace("www.", "").strip()
        if not domain:
            return None

        try:
            search_url = f"{self.BASE_URL}{self.SEARCH_PATH}"
            params = {"search": domain}
            html_text = self._get_text(search_url, params=params, timeout=timeout)
            if not html_text:
                return None

            detail_path = self._find_detail_path(html_text)
            if not detail_path:
                return None

            detail_url = f"{self.BASE_URL}{detail_path}"
            detail_html = self._get_text(detail_url, timeout=timeout)
            if not detail_html:
                return None

            bias_label = self._extract_bias_label(detail_html)
            if not bias_label:
                return None

            score = self._LABEL_TO_SCORE.get(bias_label.lower(), 0)
            return BiasResult(
                domain=domain,
                bias=score,
                bias_label=BIAS_LABELS.get(score, "Unknown"),
                confidence=0.6,
                method="allsides",
                factual_rating=None,
                category=None,
                source="AllSides",
                source_url=detail_url,
            )
        except Exception as exc:
            logger.debug("AllSides lookup failed for %s: %s", domain, exc)
            return None

    def _get_text(
        self,
        url: str,
        params: Mapping[str, str | int | float | bool | None] | None = None,
        timeout: float = 10.0,
    ) -> str | None:
        headers = {
            "User-Agent": "Mozilla/5.0 (ResearchAgent/2.0)",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.get(url, params=params, headers=headers)
                response.raise_for_status()
                return response.text
        except Exception as exc:
            logger.debug("AllSides HTTP error: %s", exc)
            return None

    def _find_detail_path(self, html_text: str) -> str | None:
        # Look for first media-bias or news-source link in search results
        patterns = [
            r'href="(/media-bias/[^"?]+)"',
            r'href="(/news-source/[^"?]+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, html_text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _extract_bias_label(self, html_text: str) -> str | None:
        # Strip HTML tags for easier searching
        text = html.unescape(re.sub(r"<[^>]+>", " ", html_text))
        text_lower = re.sub(r"\s+", " ", text).lower()

        # Try to locate bias rating near explicit labels
        match = re.search(
            r"bias\s+rating[^a-z]*(far left|left|lean left|center|lean right|right|far right|mixed|not rated)",
            text_lower,
        )
        if match:
            label = match.group(1)
            if label == "not rated":
                return None
            return label.title()

        # Fallback: find any of the known labels
        for label in [
            "Far Left",
            "Left",
            "Lean Left",
            "Center",
            "Lean Right",
            "Right",
            "Far Right",
            "Mixed",
        ]:
            if label.lower() in text_lower:
                return label

        return None
