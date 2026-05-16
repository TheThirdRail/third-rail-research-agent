"""Resolve social-post media pointers into canonical metadata."""

from __future__ import annotations

import html
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from src.schemas.visual_evidence import ResolvedSocialPost


class SocialPostResolverService:
    """Canonicalize social post URLs and optionally collect public metadata."""

    OEMBED_TIMEOUT_SECONDS = 5.0

    def resolve(self, post_url: str, *, source_url: str = "") -> ResolvedSocialPost:
        """Return canonical social-post metadata with a structured fallback."""
        platform = self.platform_from_url(post_url)
        resolved_url = self.canonicalize(post_url)
        if not platform:
            return ResolvedSocialPost(
                source_url=source_url,
                original_url=post_url,
                resolved_url=resolved_url,
                platform="",
                success=False,
                fallback_reason="unsupported_social_platform",
            )

        metadata = self._fetch_oembed(resolved_url, platform)
        return ResolvedSocialPost(
            source_url=source_url,
            original_url=post_url,
            resolved_url=resolved_url,
            platform=platform,
            metadata_text=metadata.get("metadata_text", ""),
            author_name=metadata.get("author_name", ""),
            provider_name=metadata.get("provider_name", ""),
            oembed_html=metadata.get("html", ""),
            resolution_method=metadata.get("resolution_method", "canonical_url"),
            success=True,
            fallback_reason=metadata.get("fallback_reason", ""),
        )

    def canonicalize(self, post_url: str) -> str:
        """Canonicalize common public social post URLs."""
        parsed = urlparse(post_url.strip())
        host = parsed.netloc.lower().removeprefix("www.")
        path = re.sub(r"/+", "/", parsed.path).rstrip("/")
        query = self._filtered_query(parsed.query)

        if host == "twitter.com":
            host = "x.com"
        elif host == "m.facebook.com":
            host = "facebook.com"

        return urlunparse((parsed.scheme or "https", host, path, "", query, ""))

    @classmethod
    def platform_from_url(cls, post_url: str) -> str:
        host = urlparse(post_url).netloc.lower().removeprefix("www.")
        if host in {"x.com", "twitter.com"}:
            return "x"
        if host.endswith("instagram.com"):
            return "instagram"
        if host.endswith("threads.net"):
            return "threads"
        if host.endswith("facebook.com"):
            return "facebook"
        if host.endswith("tiktok.com"):
            return "tiktok"
        if host.endswith("truthsocial.com"):
            return "truthsocial"
        return ""

    def _fetch_oembed(self, resolved_url: str, platform: str) -> dict[str, str]:
        endpoint = self._oembed_endpoint(resolved_url, platform)
        if not endpoint:
            return {
                "resolution_method": "canonical_url",
                "fallback_reason": "oembed_unavailable_for_platform",
            }
        try:
            with httpx.Client(timeout=self.OEMBED_TIMEOUT_SECONDS) as client:
                response = client.get(endpoint)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return {
                "resolution_method": "canonical_url",
                "fallback_reason": f"oembed_failed: {exc}",
            }
        if not isinstance(payload, dict):
            return {
                "resolution_method": "canonical_url",
                "fallback_reason": "oembed_invalid_response",
            }
        return {
            "metadata_text": self._metadata_text(payload),
            "author_name": str(payload.get("author_name") or ""),
            "provider_name": str(payload.get("provider_name") or ""),
            "html": str(payload.get("html") or ""),
            "resolution_method": "oembed",
        }

    @staticmethod
    def _filtered_query(query: str) -> str:
        allowed = []
        for key, value in parse_qsl(query, keep_blank_values=False):
            lowered = key.lower()
            if lowered.startswith("utm_") or lowered in {"fbclid", "igshid"}:
                continue
            allowed.append((key, value))
        return urlencode(allowed)

    @staticmethod
    def _oembed_endpoint(resolved_url: str, platform: str) -> str:
        if platform == "x":
            return "https://publish.twitter.com/oembed?" + urlencode(
                {"url": resolved_url, "omit_script": "true"}
            )
        if platform == "tiktok":
            return "https://www.tiktok.com/oembed?" + urlencode({"url": resolved_url})
        return ""

    @staticmethod
    def _metadata_text(payload: dict[str, object]) -> str:
        parts = [
            str(payload.get("title") or ""),
            str(payload.get("author_name") or ""),
            re.sub(r"<[^>]+>", " ", str(payload.get("html") or "")),
        ]
        return html.unescape(" ".join(part for part in parts if part).strip())
