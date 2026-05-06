"""Unit tests for SocialPostResolverService."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.schemas.visual_evidence import ResolvedSocialPost
from src.services.social_post_resolver_service import SocialPostResolverService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def resolver():
    """Return a fresh SocialPostResolverService instance."""
    return SocialPostResolverService()


# ---------------------------------------------------------------------------
# URL canonicalization
# ---------------------------------------------------------------------------


def test_canonicalize_rewrites_twitter_to_x(resolver):
    """twitter.com hosts should be rewritten to x.com."""
    result = resolver.canonicalize("https://twitter.com/user/status/123")
    assert "x.com" in result
    assert "twitter.com" not in result


def test_canonicalize_rewrites_mobile_facebook(resolver):
    """m.facebook.com should be rewritten to facebook.com."""
    result = resolver.canonicalize("https://m.facebook.com/post/456")
    assert "facebook.com" in result
    assert "m.facebook.com" not in result


def test_canonicalize_strips_utm_params(resolver):
    """Tracking parameters starting with utm_ should be removed."""
    url = "https://x.com/user/status/1?utm_source=share&utm_medium=web"
    result = resolver.canonicalize(url)
    assert "utm_source" not in result
    assert "utm_medium" not in result


def test_canonicalize_strips_fbclid(resolver):
    """The fbclid tracking parameter should be removed."""
    url = "https://facebook.com/post/1?fbclid=abc123"
    result = resolver.canonicalize(url)
    assert "fbclid" not in result


def test_canonicalize_strips_igshid(resolver):
    """The igshid tracking parameter should be removed."""
    url = "https://instagram.com/p/abc?igshid=xyz"
    result = resolver.canonicalize(url)
    assert "igshid" not in result


def test_canonicalize_preserves_non_tracking_params(resolver):
    """Non-tracking query parameters should be preserved."""
    url = "https://x.com/user/status/1?ref=homepage&lang=en"
    result = resolver.canonicalize(url)
    assert "ref=homepage" in result
    assert "lang=en" in result


def test_canonicalize_collapses_duplicate_slashes(resolver):
    """Consecutive slashes in the path should be collapsed to a single slash."""
    url = "https://x.com/user///status//123"
    result = resolver.canonicalize(url)
    assert "///" not in result.split("://", 1)[-1]
    assert "/user/status/123" in result


def test_canonicalize_defaults_to_https(resolver):
    """URLs without a scheme should default to https."""
    url = "//x.com/user/status/1"
    result = resolver.canonicalize(url)
    assert result.startswith("https://")


def test_canonicalize_strips_trailing_slash(resolver):
    """Trailing slashes on the path should be removed."""
    url = "https://x.com/user/status/1/"
    result = resolver.canonicalize(url)
    assert not result.endswith("/")


def test_canonicalize_removes_www_prefix(resolver):
    """The www. prefix on the host should be removed."""
    url = "https://www.instagram.com/p/abc"
    result = resolver.canonicalize(url)
    assert "www." not in result


def test_canonicalize_lowercases_host(resolver):
    """The hostname should be lowercased."""
    url = "https://X.COM/User/Status/1"
    result = resolver.canonicalize(url)
    # Host should be lowered, but path case is preserved by urlunparse
    assert "x.com" in result


def test_canonicalize_strips_fragment(resolver):
    """URL fragments should be dropped during canonicalization."""
    url = "https://x.com/user/status/1#comment"
    result = resolver.canonicalize(url)
    assert "#" not in result


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


def test_platform_from_url_x_dot_com():
    """x.com should resolve to platform 'x'."""
    assert (
        SocialPostResolverService.platform_from_url("https://x.com/user/status/1")
        == "x"
    )


def test_platform_from_url_twitter():
    """twitter.com should resolve to platform 'x'."""
    assert (
        SocialPostResolverService.platform_from_url("https://twitter.com/user/status/1")
        == "x"
    )


def test_platform_from_url_instagram():
    """instagram.com and subdomains should resolve to 'instagram'."""
    assert (
        SocialPostResolverService.platform_from_url("https://www.instagram.com/p/abc")
        == "instagram"
    )
    assert (
        SocialPostResolverService.platform_from_url("https://instagram.com/p/abc")
        == "instagram"
    )


def test_platform_from_url_threads():
    """threads.net and subdomains should resolve to 'threads'."""
    assert (
        SocialPostResolverService.platform_from_url(
            "https://www.threads.net/@user/post/123"
        )
        == "threads"
    )


def test_platform_from_url_facebook():
    """facebook.com and subdomains should resolve to 'facebook'."""
    assert (
        SocialPostResolverService.platform_from_url("https://www.facebook.com/post/456")
        == "facebook"
    )
    assert (
        SocialPostResolverService.platform_from_url("https://m.facebook.com/post/456")
        == "facebook"
    )


def test_platform_from_url_tiktok():
    """tiktok.com and subdomains should resolve to 'tiktok'."""
    assert (
        SocialPostResolverService.platform_from_url(
            "https://www.tiktok.com/@user/video/123"
        )
        == "tiktok"
    )


def test_platform_from_url_truthsocial():
    """truthsocial.com and subdomains should resolve to 'truthsocial'."""
    assert (
        SocialPostResolverService.platform_from_url(
            "https://truthsocial.com/@user/posts/1"
        )
        == "truthsocial"
    )


def test_platform_from_url_unknown_domain():
    """Unknown domains should return an empty string."""
    assert SocialPostResolverService.platform_from_url("https://example.com/page") == ""


def test_platform_from_url_youtube_is_unknown():
    """YouTube is not a supported social platform and should return empty."""
    assert (
        SocialPostResolverService.platform_from_url(
            "https://www.youtube.com/watch?v=abc"
        )
        == ""
    )


# ---------------------------------------------------------------------------
# oEmbed endpoint construction
# ---------------------------------------------------------------------------


def test_oembed_endpoint_for_x():
    """X platform should produce a publish.twitter.com oEmbed URL."""
    url = "https://x.com/user/status/123"
    endpoint = SocialPostResolverService._oembed_endpoint(url, "x")
    assert endpoint.startswith("https://publish.twitter.com/oembed?")
    assert "url=https" in endpoint
    assert "omit_script=true" in endpoint


def test_oembed_endpoint_for_tiktok():
    """TikTok should produce a tiktok.com oEmbed URL."""
    url = "https://www.tiktok.com/@user/video/123"
    endpoint = SocialPostResolverService._oembed_endpoint(url, "tiktok")
    assert endpoint.startswith("https://www.tiktok.com/oembed?")
    assert "url=https" in endpoint


def test_oembed_endpoint_for_instagram_is_empty():
    """Instagram has no oEmbed endpoint and should return empty."""
    assert (
        SocialPostResolverService._oembed_endpoint(
            "https://instagram.com/p/abc", "instagram"
        )
        == ""
    )


def test_oembed_endpoint_for_facebook_is_empty():
    """Facebook has no oEmbed endpoint and should return empty."""
    assert (
        SocialPostResolverService._oembed_endpoint(
            "https://facebook.com/post/1", "facebook"
        )
        == ""
    )


def test_oembed_endpoint_for_threads_is_empty():
    """Threads has no oEmbed endpoint and should return empty."""
    assert (
        SocialPostResolverService._oembed_endpoint(
            "https://threads.net/@user/post/1", "threads"
        )
        == ""
    )


def test_oembed_endpoint_for_truthsocial_is_empty():
    """Truth Social has no oEmbed endpoint and should return empty."""
    assert (
        SocialPostResolverService._oembed_endpoint(
            "https://truthsocial.com/@user/posts/1", "truthsocial"
        )
        == ""
    )


# ---------------------------------------------------------------------------
# Metadata text extraction
# ---------------------------------------------------------------------------


def test_metadata_text_strips_html_tags():
    """HTML tags in the payload 'html' field should be removed."""
    payload = {
        "title": "",
        "author_name": "",
        "html": "<blockquote>Hello <b>world</b></blockquote>",
    }
    result = SocialPostResolverService._metadata_text(payload)
    assert "<blockquote>" not in result
    assert "<b>" not in result
    assert "Hello" in result
    assert "world" in result


def test_metadata_text_unescapes_html_entities():
    """HTML entities like &amp; should be unescaped."""
    payload = {
        "title": "Tom &amp; Jerry",
        "author_name": "",
        "html": "",
    }
    result = SocialPostResolverService._metadata_text(payload)
    assert "Tom & Jerry" in result
    assert "&amp;" not in result


def test_metadata_text_empty_payload_returns_empty():
    """An empty payload should produce an empty metadata string."""
    assert SocialPostResolverService._metadata_text({}) == ""


def test_metadata_text_combines_title_author_html():
    """Metadata text should join title, author_name, and stripped html."""
    payload = {
        "title": "Breaking News",
        "author_name": "Reporter",
        "html": "<p>Story text</p>",
    }
    result = SocialPostResolverService._metadata_text(payload)
    assert "Breaking News" in result
    assert "Reporter" in result
    assert "Story text" in result


def test_metadata_text_skips_none_values():
    """None values in payload fields should not produce 'None' in output."""
    payload = {
        "title": None,
        "author_name": None,
        "html": None,
    }
    result = SocialPostResolverService._metadata_text(payload)
    assert "None" not in result


# ---------------------------------------------------------------------------
# Filtered query
# ---------------------------------------------------------------------------


def test_filtered_query_removes_utm_params():
    """Query strings with utm_ prefixed keys should be dropped."""
    result = SocialPostResolverService._filtered_query(
        "utm_source=twitter&utm_medium=social&keep=yes"
    )
    assert "utm_source" not in result
    assert "utm_medium" not in result
    assert "keep=yes" in result


def test_filtered_query_removes_fbclid_and_igshid():
    """fbclid and igshid keys should be dropped."""
    result = SocialPostResolverService._filtered_query("fbclid=abc&igshid=xyz&ok=1")
    assert "fbclid" not in result
    assert "igshid" not in result
    assert "ok=1" in result


def test_filtered_query_empty_input():
    """An empty query string should return empty."""
    assert SocialPostResolverService._filtered_query("") == ""


def test_filtered_query_preserves_all_when_no_tracking():
    """Non-tracking params should all be preserved."""
    result = SocialPostResolverService._filtered_query("a=1&b=2")
    assert "a=1" in result
    assert "b=2" in result


# ---------------------------------------------------------------------------
# resolve() - X platform with oEmbed success
# ---------------------------------------------------------------------------


def test_resolve_x_oembed_success(resolver):
    """Resolving an X post with a successful oEmbed call populates metadata."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "title": "Tweet Title",
        "author_name": "@journalist",
        "provider_name": "Twitter",
        "html": "<blockquote>Post content</blockquote>",
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response

    with patch(
        "src.services.social_post_resolver_service.httpx.Client",
        return_value=mock_client,
    ):
        result = resolver.resolve(
            "https://twitter.com/user/status/123",
            source_url="https://article.example.com",
        )

    assert isinstance(result, ResolvedSocialPost)
    assert result.success is True
    assert result.platform == "x"
    assert result.resolution_method == "oembed"
    assert result.author_name == "@journalist"
    assert result.provider_name == "Twitter"
    assert result.oembed_html == "<blockquote>Post content</blockquote>"
    assert result.metadata_text != ""
    assert result.source_url == "https://article.example.com"
    assert result.fallback_reason == ""
    # Canonical URL rewrite should appear in resolved_url
    assert "x.com" in result.resolved_url


# ---------------------------------------------------------------------------
# resolve() - X platform with oEmbed failure (graceful fallback)
# ---------------------------------------------------------------------------


def test_resolve_x_oembed_failure_falls_back(resolver):
    """When oEmbed fails for X, resolve should still succeed with a fallback reason."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "503 Service Unavailable",
        request=MagicMock(),
        response=MagicMock(status_code=503),
    )

    with patch(
        "src.services.social_post_resolver_service.httpx.Client",
        return_value=mock_client,
    ):
        result = resolver.resolve("https://x.com/user/status/999")

    assert result.success is True
    assert result.platform == "x"
    assert result.resolution_method == "canonical_url"
    assert result.fallback_reason != ""
    assert "oembed_failed" in result.fallback_reason


def test_resolve_x_oembed_timeout_falls_back(resolver):
    """When oEmbed times out for X, resolve should still succeed with a fallback reason."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")

    with patch(
        "src.services.social_post_resolver_service.httpx.Client",
        return_value=mock_client,
    ):
        result = resolver.resolve("https://x.com/user/status/999")

    assert result.success is True
    assert result.resolution_method == "canonical_url"
    assert "oembed_failed" in result.fallback_reason


def test_resolve_x_oembed_invalid_json_falls_back(resolver):
    """When oEmbed returns non-dict JSON, resolve should fall back cleanly."""
    mock_response = MagicMock()
    mock_response.json.return_value = ["not", "a", "dict"]
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response

    with patch(
        "src.services.social_post_resolver_service.httpx.Client",
        return_value=mock_client,
    ):
        result = resolver.resolve("https://x.com/user/status/999")

    assert result.success is True
    assert result.resolution_method == "canonical_url"
    assert result.fallback_reason == "oembed_invalid_response"


# ---------------------------------------------------------------------------
# resolve() - TikTok with oEmbed success
# ---------------------------------------------------------------------------


def test_resolve_tiktok_oembed_success(resolver):
    """TikTok posts should use the TikTok oEmbed endpoint and populate metadata."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "title": "Funny dance",
        "author_name": "@dancer",
        "provider_name": "TikTok",
        "html": "<iframe>embed</iframe>",
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response

    with patch(
        "src.services.social_post_resolver_service.httpx.Client",
        return_value=mock_client,
    ):
        result = resolver.resolve("https://www.tiktok.com/@user/video/123")

    assert result.success is True
    assert result.platform == "tiktok"
    assert result.resolution_method == "oembed"
    assert result.author_name == "@dancer"


# ---------------------------------------------------------------------------
# resolve() - Platforms without oEmbed (Instagram, Threads, Facebook, Truth Social)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected_platform",
    [
        ("https://www.instagram.com/p/abc123", "instagram"),
        ("https://www.threads.net/@user/post/123", "threads"),
        ("https://www.facebook.com/post/456", "facebook"),
        ("https://truthsocial.com/@user/posts/789", "truthsocial"),
    ],
    ids=["instagram", "threads", "facebook", "truthsocial"],
)
def test_resolve_platforms_without_oembed(resolver, url, expected_platform):
    """Platforms without oEmbed should resolve without crash, using canonical_url method."""
    result = resolver.resolve(url)

    assert result.success is True
    assert result.platform == expected_platform
    assert result.resolution_method == "canonical_url"
    assert result.fallback_reason == "oembed_unavailable_for_platform"
    assert result.metadata_text == ""
    assert result.author_name == ""
    assert result.oembed_html == ""


# ---------------------------------------------------------------------------
# resolve() - Unsupported domains
# ---------------------------------------------------------------------------


def test_resolve_unsupported_domain(resolver):
    """Unknown domains should fail with unsupported_social_platform reason."""
    result = resolver.resolve("https://example.com/some/page")

    assert result.success is False
    assert result.platform == ""
    assert result.fallback_reason == "unsupported_social_platform"
    assert result.original_url == "https://example.com/some/page"


def test_resolve_unsupported_domain_still_canonicalizes(resolver):
    """Even unsupported domains should have a canonicalized resolved_url."""
    result = resolver.resolve("https://www.example.com/path///double?utm_source=test")

    assert result.success is False
    assert "www." not in result.resolved_url
    assert "utm_source" not in result.resolved_url


# ---------------------------------------------------------------------------
# resolve() - source_url propagation
# ---------------------------------------------------------------------------


def test_resolve_propagates_source_url(resolver):
    """The source_url keyword argument should appear on the returned model."""
    result = resolver.resolve(
        "https://example.com/not-social",
        source_url="https://article.example.com/page",
    )
    assert result.source_url == "https://article.example.com/page"


def test_resolve_source_url_defaults_to_empty(resolver):
    """When source_url is omitted it should default to empty string."""
    result = resolver.resolve("https://example.com/page")
    assert result.source_url == ""


# ---------------------------------------------------------------------------
# resolve() - original_url vs resolved_url
# ---------------------------------------------------------------------------


def test_resolve_stores_original_url_unchanged(resolver):
    """The original_url field should contain the exact input URL."""
    raw = "https://twitter.com/user/status/1?utm_source=share"

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = httpx.ConnectError("refused")

    with patch(
        "src.services.social_post_resolver_service.httpx.Client",
        return_value=mock_client,
    ):
        result = resolver.resolve(raw)

    assert result.original_url == raw
    assert result.resolved_url != raw  # canonicalized version differs


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_canonicalize_whitespace_stripped(resolver):
    """Leading and trailing whitespace on the URL should be stripped."""
    result = resolver.canonicalize("  https://x.com/user/status/1  ")
    assert result.startswith("https://")
    assert not result.startswith(" ")


def test_platform_from_url_case_insensitive():
    """Platform detection should be case-insensitive for the host."""
    assert (
        SocialPostResolverService.platform_from_url("https://X.COM/user/status/1")
        == "x"
    )
    assert (
        SocialPostResolverService.platform_from_url("https://TWITTER.COM/user/status/1")
        == "x"
    )
    assert (
        SocialPostResolverService.platform_from_url("https://WWW.INSTAGRAM.COM/p/abc")
        == "instagram"
    )


def test_resolve_empty_oembed_fields_default_to_empty_strings(resolver):
    """When oEmbed returns null/missing fields, they should default to empty strings."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "author_name": None,
        "provider_name": None,
        "html": None,
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response

    with patch(
        "src.services.social_post_resolver_service.httpx.Client",
        return_value=mock_client,
    ):
        result = resolver.resolve("https://x.com/user/status/1")

    assert result.author_name == ""
    assert result.provider_name == ""
    assert result.oembed_html == ""


def test_metadata_text_handles_numeric_values():
    """Numeric payload values should be safely coerced to strings."""
    payload = {
        "title": 42,
        "author_name": 0,
        "html": "",
    }
    # Should not raise; int values are coerced via str()
    result = SocialPostResolverService._metadata_text(payload)
    assert "42" in result
