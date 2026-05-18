"""Article Content Extraction Tool for CrewAI."""

import asyncio
import contextlib
import inspect
import ipaddress
import json
import logging
import socket
from collections.abc import Awaitable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any, TypedDict
from urllib.parse import urlparse

from crewai.tools.base_tool import BaseTool

from src.core.config import settings
from src.utils.url_utils import extract_domain

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "2026-05-18-crawl4ai-profiles-jsonld-firecrawl-v2"
_VERSION_LOGGED = False

ERROR_BLOCKED_CHALLENGE = "blocked_challenge"
ERROR_EMPTY_CONTENT = "empty_content"
ERROR_EXCEPTION = "exception"
ERROR_MISSING_API_KEY = "missing_api_key"
ERROR_PAYWALL_OR_SUBSCRIPTION = "paywall_or_subscription"
ERROR_PARSE_FAILURE = "parse_failure"
ERROR_SHORT_CONTENT = "short_content"
ERROR_TIMEOUT = "timeout"
ERROR_UNSAFE_URL = "unsafe_url"

MIN_EXTRACTION_TEXT_LENGTH = 100
PLAYWRIGHT_PAGE_TIMEOUT_MS = 25000
CONTENT_PREVIEW_CHARS = 10000
MULTI_ARTICLE_MAX_URLS = 10
MULTI_ARTICLE_CONCURRENCY_LIMIT = 4

_BLOCKED_SIGNATURES = (
    "access denied",
    "captcha",
    "robot",
    "bot detection",
    "verify you are human",
    "challenge",
    "geo.captcha-delivery.com",
    "datadome",
)

_PAYWALL_SIGNATURES = (
    "already a subscriber",
    "create a free account",
    "for subscribers",
    "log in to continue",
    "login to continue",
    "paywall",
    "register to continue",
    "sign in to continue",
    "subscribe to continue",
    "subscriber-only",
    "subscription required",
)

_ARTICLE_JSONLD_TYPES = {
    "article",
    "blogposting",
    "newsarticle",
    "reportagenewsarticle",
}


@dataclass(frozen=True)
class _Crawl4AIAttempt:
    label: str
    use_undetected: bool
    enable_stealth: bool


@dataclass(frozen=True)
class _Crawl4AIProfile:
    label: str
    wait_until: str
    wait_for: str | None = None
    js_code: str | list[str] | None = None
    text_mode: bool = False
    light_mode: bool = False
    avoid_ads: bool = True
    avoid_css: bool = False
    scan_full_page: bool = False
    scroll_delay: float = 0.2
    delay_before_return_html: float | None = None
    proxy_enabled: bool = False
    max_retries: int | None = None


class _MediaMetadata(TypedDict):
    og_image_url: str | None
    embedded_post_urls: list[str]
    image_alt_text: list[str]
    media_captions: list[str]


class _MediaHTMLParser(HTMLParser):
    """Small metadata parser for media pointers in article HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.image_urls: list[str] = []
        self.post_urls: list[str] = []
        self.alt_texts: list[str] = []
        self.captions: list[str] = []
        self._in_figcaption = False
        self._caption_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        if tag == "meta":
            key = (attr.get("property") or attr.get("name") or "").lower()
            content = attr.get("content", "").strip()
            if key in {"og:image", "twitter:image"} and content:
                self.image_urls.append(content)
        elif tag == "img":
            src = attr.get("src", "").strip()
            alt = attr.get("alt", "").strip()
            if src:
                self.image_urls.append(src)
            if alt:
                self.alt_texts.append(unescape(alt))
        elif tag in {"a", "blockquote", "iframe"}:
            href = (
                attr.get("href") or attr.get("cite") or attr.get("src") or ""
            ).strip()
            if self._is_social_url(href):
                self.post_urls.append(href)
        elif tag == "figcaption":
            self._in_figcaption = True
            self._caption_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_figcaption:
            self._caption_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "figcaption" and self._in_figcaption:
            caption = " ".join(
                part.strip() for part in self._caption_parts if part.strip()
            )
            if caption:
                self.captions.append(unescape(caption))
            self._in_figcaption = False
            self._caption_parts = []

    @staticmethod
    def _is_social_url(url: str) -> bool:
        return any(
            host in url.lower()
            for host in (
                "twitter.com/",
                "x.com/",
                "instagram.com/",
                "facebook.com/",
                "threads.net/",
                "tiktok.com/",
                "truthsocial.com/",
            )
        )


class _JSONLDHTMLParser(HTMLParser):
    """Collect application/ld+json script bodies without a full HTML dependency."""

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[str] = []
        self._capturing = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attr = {key.lower(): value or "" for key, value in attrs}
        if "ld+json" in attr.get("type", "").lower():
            self._capturing = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._capturing:
            block = "".join(self._parts).strip()
            if block:
                self.blocks.append(unescape(block))
            self._capturing = False
            self._parts = []


def _log_extractor_version_once() -> None:
    global _VERSION_LOGGED
    if _VERSION_LOGGED:
        return
    _VERSION_LOGGED = True
    logger.info("ArticleExtractor version %s loaded", EXTRACTOR_VERSION)


@dataclass
class ExtractedArticle:
    """Represents extracted article content."""

    title: str
    text: str
    author: str | None
    date: datetime | None
    domain: str
    url: str
    success: bool
    error: str | None = None
    error_code: str | None = None
    http_status: int | None = None
    extractor_method: str | None = None
    og_image_url: str | None = None
    embedded_post_urls: tuple[str, ...] = ()
    image_alt_text: tuple[str, ...] = ()
    media_captions: tuple[str, ...] = ()


class ArticleExtractor:
    """Extracts articles with local/browser fallbacks and Firecrawl last."""

    def _crawl4ai_attempts(self) -> tuple[_Crawl4AIAttempt, ...]:
        attempts = [
            _Crawl4AIAttempt(
                label="regular_stealth",
                use_undetected=False,
                enable_stealth=True,
            )
        ]
        if settings.crawl4ai_progressive_undetected_enabled:
            attempts.extend(
                [
                    _Crawl4AIAttempt(
                        label="undetected",
                        use_undetected=True,
                        enable_stealth=False,
                    ),
                    _Crawl4AIAttempt(
                        label="undetected_stealth",
                        use_undetected=True,
                        enable_stealth=True,
                    ),
                ]
            )
        return tuple(attempts)

    def _crawl4ai_profile(self, label: str) -> _Crawl4AIProfile:
        wait_for = self._crawl4ai_article_wait_for()
        if label == "dynamic_news":
            return _Crawl4AIProfile(
                label=label,
                wait_until="domcontentloaded",
                wait_for=wait_for,
                js_code=[
                    "window.scrollTo(0, document.body.scrollHeight);",
                    "window.scrollTo(0, 0);",
                ],
                scan_full_page=True,
                scroll_delay=0.35,
                delay_before_return_html=(
                    settings.crawl4ai_delay_before_return_html + 1.0
                ),
                max_retries=1,
            )
        if label == "protected_news":
            return _Crawl4AIProfile(
                label=label,
                wait_until="domcontentloaded",
                wait_for=wait_for,
                js_code=[
                    "window.scrollTo(0, document.body.scrollHeight);",
                    "window.scrollTo(0, 0);",
                ],
                scan_full_page=True,
                scroll_delay=0.35,
                delay_before_return_html=(
                    settings.crawl4ai_delay_before_return_html + 1.0
                ),
                proxy_enabled=bool((settings.crawl4ai_proxy_url or "").strip()),
                max_retries=2,
            )
        return _Crawl4AIProfile(
            label="default_news",
            wait_until="domcontentloaded",
            wait_for=wait_for,
            text_mode=True,
            light_mode=True,
            avoid_css=True,
            scan_full_page=False,
            delay_before_return_html=settings.crawl4ai_delay_before_return_html,
        )

    @staticmethod
    def _crawl4ai_article_wait_for() -> str:
        min_chars = max(
            MIN_EXTRACTION_TEXT_LENGTH,
            int(settings.crawl4ai_article_wait_min_chars or 0),
        )
        return (
            "js:() => { "
            "const selectors = ['article', 'main', '[role=\"main\"]', "
            "'.article-body', '.story-body', '.entry-content', 'body']; "
            "return selectors.some((selector) => { "
            "const node = document.querySelector(selector); "
            "return node && (node.innerText || '').trim().length >= "
            f"{min_chars}; "
            "}); "
            "}"
        )

    @staticmethod
    def _instantiate_supported(factory: Any, **kwargs: Any) -> Any:
        try:
            signature = inspect.signature(factory)
        except (TypeError, ValueError):
            return factory(**kwargs)

        if not any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        ):
            kwargs = {
                key: value for key, value in kwargs.items() if key in signature.parameters
            }
        return factory(**kwargs)

    def _import_crawl4ai_core(self) -> tuple[Any, Any, Any, Any]:
        from crawl4ai import (
            AsyncWebCrawler,
            BrowserConfig,
            CacheMode,
            CrawlerRunConfig,
        )

        return AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    def _build_crawl4ai_browser_config(
        self,
        BrowserConfig: Any,
        *,
        enable_stealth: bool,
        profile: _Crawl4AIProfile,
    ) -> Any:
        return self._instantiate_supported(
            BrowserConfig,
            browser_type="chromium",
            headless=settings.crawl4ai_headless,
            viewport_width=1365,
            viewport_height=768,
            user_agent_mode="random",
            enable_stealth=enable_stealth,
            text_mode=profile.text_mode,
            light_mode=profile.light_mode,
            avoid_ads=profile.avoid_ads,
            avoid_css=profile.avoid_css,
            verbose=False,
        )

    def _build_crawl4ai_run_config(
        self,
        CrawlerRunConfig: Any,
        CacheMode: Any,
        *,
        profile: _Crawl4AIProfile,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "cache_mode": CacheMode.BYPASS,
            "word_count_threshold": 10,
            "excluded_tags": [
                "script",
                "style",
                "noscript",
                "nav",
                "footer",
                "header",
                "form",
                "aside",
            ],
            "exclude_social_media_links": True,
            "exclude_external_images": True,
            "remove_overlay_elements": True,
            "remove_consent_popups": True,
            "magic": True,
            "simulate_user": True,
            "override_navigator": True,
            "wait_until": profile.wait_until,
            "page_timeout": settings.crawl4ai_page_timeout_ms,
            "delay_before_return_html": (
                profile.delay_before_return_html
                if profile.delay_before_return_html is not None
                else settings.crawl4ai_delay_before_return_html
            ),
            "scan_full_page": profile.scan_full_page,
            "scroll_delay": profile.scroll_delay,
            "user_agent_mode": "random",
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }
        if profile.wait_for:
            kwargs["wait_for"] = profile.wait_for
        if profile.js_code:
            kwargs["js_code"] = profile.js_code
        if profile.max_retries is not None:
            kwargs["max_retries"] = profile.max_retries
        if profile.proxy_enabled:
            proxy_url = (settings.crawl4ai_proxy_url or "").strip()
            if proxy_url:
                kwargs["proxy_config"] = {"server": proxy_url}

        with contextlib.suppress(Exception):
            from crawl4ai.content_filter_strategy import PruningContentFilter
            from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

            kwargs["markdown_generator"] = DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(
                    threshold=0.45,
                    threshold_type="dynamic",
                    min_word_threshold=5,
                ),
                options={
                    "ignore_images": True,
                    "skip_internal_links": True,
                    "body_width": 0,
                },
            )

        return self._instantiate_supported(CrawlerRunConfig, **kwargs)

    async def _article_from_crawl4ai_result(
        self, result: Any, *, url: str
    ) -> ExtractedArticle:
        status = self._coerce_status(
            self._payload_get_any(result, ("status_code", "statusCode"))
        )
        success = self._payload_get(result, "success")
        error_message = self._payload_get(result, "error_message")
        html_content = self._payload_get_any(result, ("cleaned_html", "html")) or ""
        markdown_text = self._markdown_text(self._payload_get(result, "markdown"))
        metadata = self._payload_get(result, "metadata") or {}
        title = (
            self._payload_get(metadata, "title")
            or self._payload_get(result, "title")
            or ""
        )
        classified_error = self._classify_content_failure(
            http_status=status,
            html_content=html_content,
            body_text=markdown_text,
            title=str(title),
            error_message=str(error_message or ""),
        )

        if success is False:
            if classified_error:
                return self._failure(
                    url=url,
                    error=str(error_message or f"Crawl4AI failed: {classified_error}"),
                    error_code=classified_error,
                    method="crawl4ai",
                    http_status=status,
                )
            return self._failure(
                url=url,
                error=str(error_message or "Crawl4AI extraction failed"),
                error_code=ERROR_PARSE_FAILURE,
                method="crawl4ai",
                http_status=status,
            )

        if classified_error:
            return self._failure(
                url=url,
                error=f"Crawl4AI returned {classified_error}",
                error_code=classified_error,
                method="crawl4ai",
                http_status=status,
            )

        if not markdown_text and html_content:
            article = await asyncio.to_thread(
                self._extract_from_html,
                url=url,
                html_content=html_content,
                method="crawl4ai",
                http_status=status,
                title_hint=str(title),
            )
            if article.success and len(article.text.strip()) < MIN_EXTRACTION_TEXT_LENGTH:
                return self._failure(
                    url=url,
                    error="Crawl4AI HTML fallback returned too little content",
                    error_code=ERROR_SHORT_CONTENT,
                    method="crawl4ai",
                    http_status=status,
                )
            return article

        if not markdown_text:
            return self._failure(
                url=url,
                error="No content extracted via Crawl4AI",
                error_code=ERROR_EMPTY_CONTENT,
                method="crawl4ai",
                http_status=status,
            )

        if len(markdown_text.strip()) < MIN_EXTRACTION_TEXT_LENGTH:
            return self._failure(
                url=url,
                error="Crawl4AI returned too little article text",
                error_code=ERROR_SHORT_CONTENT,
                method="crawl4ai",
                http_status=status,
            )

        media = self._extract_media_metadata(html_content)
        return ExtractedArticle(
            title=str(title or ""),
            text=markdown_text,
            author=None,
            date=None,
            domain=extract_domain(url),
            url=url,
            success=True,
            error=None,
            error_code=None,
            http_status=status,
            extractor_method="crawl4ai",
            og_image_url=media["og_image_url"],
            embedded_post_urls=tuple(media["embedded_post_urls"]),
            image_alt_text=tuple(media["image_alt_text"]),
            media_captions=tuple(media["media_captions"]),
        )

    async def _run_crawl4ai_attempt(
        self,
        *,
        url: str,
        attempt: _Crawl4AIAttempt,
        profile: _Crawl4AIProfile,
        AsyncWebCrawler: Any,
        BrowserConfig: Any,
        CacheMode: Any,
        CrawlerRunConfig: Any,
    ) -> ExtractedArticle:
        try:
            browser_config = self._build_crawl4ai_browser_config(
                BrowserConfig,
                enable_stealth=attempt.enable_stealth,
                profile=profile,
            )
            run_config = self._build_crawl4ai_run_config(
                CrawlerRunConfig,
                CacheMode,
                profile=profile,
            )

            crawler_kwargs: dict[str, Any] = {"config": browser_config}
            if attempt.use_undetected:
                try:
                    from crawl4ai import UndetectedAdapter
                    from crawl4ai.async_crawler_strategy import (
                        AsyncPlaywrightCrawlerStrategy,
                    )
                except Exception as exc:
                    return self._failure(
                        url=url,
                        error=f"Crawl4AI undetected browser unavailable: {exc}",
                        error_code=ERROR_EXCEPTION,
                        method="crawl4ai",
                    )

                crawler_kwargs["crawler_strategy"] = AsyncPlaywrightCrawlerStrategy(
                    browser_config=browser_config,
                    browser_adapter=UndetectedAdapter(),
                )

            async with AsyncWebCrawler(**crawler_kwargs) as crawler:
                result = await crawler.arun(url=url, config=run_config)

            return await self._article_from_crawl4ai_result(result, url=url)

        except TimeoutError:
            return self._failure(
                url=url,
                error="Crawl4AI timed out",
                error_code=ERROR_TIMEOUT,
                method="crawl4ai",
            )
        except Exception as exc:
            logger.warning(
                "Crawl4AI %s/%s failed for %s: %s",
                attempt.label,
                profile.label,
                url,
                exc,
            )
            return self._failure(
                url=url,
                error=str(exc),
                error_code=ERROR_EXCEPTION,
                method="crawl4ai",
            )

    def _failure(
        self,
        *,
        url: str,
        error: str,
        error_code: str,
        method: str,
        http_status: int | None = None,
    ) -> ExtractedArticle:
        return ExtractedArticle(
            title="",
            text="",
            author=None,
            date=None,
            domain=extract_domain(url),
            url=url,
            success=False,
            error=error,
            error_code=error_code,
            http_status=http_status,
            extractor_method=method,
        )

    def _looks_blocked(
        self,
        html_content: str = "",
        body_text: str = "",
        title: str = "",
    ) -> bool:
        haystack = f"{title}\n{body_text}\n{html_content}".lower()
        return any(sig in haystack for sig in _BLOCKED_SIGNATURES)

    def _looks_paywalled(
        self,
        html_content: str = "",
        body_text: str = "",
        title: str = "",
    ) -> bool:
        haystack = f"{title}\n{body_text}\n{html_content}".lower()
        return any(sig in haystack for sig in _PAYWALL_SIGNATURES)

    def _classify_content_failure(
        self,
        *,
        http_status: int | None = None,
        html_content: str = "",
        body_text: str = "",
        title: str = "",
        error_message: str | None = None,
    ) -> str | None:
        combined = f"{title}\n{body_text}\n{html_content}\n{error_message or ''}"
        if self._looks_paywalled(combined):
            return ERROR_PAYWALL_OR_SUBSCRIPTION
        if http_status in {403, 429} or self._looks_blocked(combined):
            return ERROR_BLOCKED_CHALLENGE
        if "timeout" in (error_message or "").lower():
            return ERROR_TIMEOUT
        return None

    @staticmethod
    def _is_retryable_short_failure(result: ExtractedArticle) -> bool:
        return result.error_code in {ERROR_EMPTY_CONTENT, ERROR_SHORT_CONTENT}

    def _unsafe_url_failure(
        self, url: str, *, method: str = "url_guard"
    ) -> ExtractedArticle | None:
        reason = self._public_url_error(url)
        if reason is None:
            return None
        return self._failure(
            url=url,
            error=f"Blocked unsafe article URL: {reason}",
            error_code=ERROR_UNSAFE_URL,
            method=method,
        )

    @staticmethod
    def _public_url_error(url: str) -> str | None:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            return "only http and https URLs are allowed"

        host = (parsed.hostname or "").strip().lower().rstrip(".")
        if not host:
            return "missing host"
        if host == "localhost":
            return "localhost is not allowed"

        addresses: list[str] = []
        try:
            addresses.append(str(ipaddress.ip_address(host)))
        except ValueError:
            try:
                resolved = socket.getaddrinfo(host, 80, type=socket.SOCK_STREAM)
            except OSError:
                resolved = []
            addresses.extend(str(item[4][0]) for item in resolved if item[4])

        for address in addresses:
            try:
                parsed_ip = ipaddress.ip_address(address)
            except ValueError:
                continue
            if (
                parsed_ip.is_loopback
                or parsed_ip.is_private
                or parsed_ip.is_link_local
                or parsed_ip.is_multicast
                or parsed_ip.is_reserved
                or parsed_ip.is_unspecified
            ):
                return f"non-public IP address {parsed_ip} is not allowed"
        return None

    @staticmethod
    def _payload_get(payload: Any, key: str) -> Any:
        if isinstance(payload, dict):
            return payload.get(key)
        return getattr(payload, key, None)

    @staticmethod
    def _coerce_status(value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            with contextlib.suppress(ValueError):
                return int(value)
        return None

    def _payload_get_any(self, payload: Any, keys: tuple[str, ...]) -> Any:
        for key in keys:
            value = self._payload_get(payload, key)
            if value not in (None, ""):
                return value
        return None

    def _markdown_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for key in ("fit_markdown", "raw_markdown", "markdown", "content"):
                text = self._markdown_text(value.get(key))
                if text:
                    return text
            return ""
        for attr in ("fit_markdown", "raw_markdown", "markdown", "content"):
            text = self._markdown_text(getattr(value, attr, None))
            if text:
                return text
        return str(value).strip()

    def _article_from_json_ld(
        self,
        *,
        url: str,
        html_content: str,
        method: str,
        http_status: int | None = None,
        title_hint: str | None = None,
    ) -> ExtractedArticle | None:
        parser = _JSONLDHTMLParser()
        with contextlib.suppress(Exception):
            parser.feed(html_content or "")

        for block in parser.blocks:
            with contextlib.suppress(json.JSONDecodeError, TypeError, ValueError):
                payload = json.loads(block)
                article = self._article_from_json_ld_payload(
                    payload,
                    url=url,
                    html_content=html_content,
                    method=method,
                    http_status=http_status,
                    title_hint=title_hint,
                )
                if article is not None:
                    return article
        return None

    def _article_from_json_ld_payload(
        self,
        payload: Any,
        *,
        url: str,
        html_content: str,
        method: str,
        http_status: int | None = None,
        title_hint: str | None = None,
    ) -> ExtractedArticle | None:
        for node in self._iter_json_ld_nodes(payload):
            if not self._json_ld_type_matches(node):
                continue

            text = self._json_ld_text(
                self._payload_get_any(
                    node,
                    ("articleBody", "text", "description"),
                )
            )
            if len(text) < MIN_EXTRACTION_TEXT_LENGTH:
                continue

            title = (
                self._json_ld_text(
                    self._payload_get_any(node, ("headline", "name"))
                )
                or title_hint
                or ""
            )
            media = self._extract_media_metadata(html_content)
            image_url = (
                self._json_ld_image_url(self._payload_get(node, "image"))
                or media["og_image_url"]
            )
            return ExtractedArticle(
                title=title,
                text=text,
                author=self._json_ld_author(self._payload_get(node, "author")),
                date=self._json_ld_date(
                    self._payload_get_any(
                        node,
                        ("datePublished", "dateCreated", "dateModified"),
                    )
                ),
                domain=extract_domain(url),
                url=url,
                success=True,
                error=None,
                error_code=None,
                http_status=http_status,
                extractor_method=method,
                og_image_url=image_url,
                embedded_post_urls=tuple(media["embedded_post_urls"]),
                image_alt_text=tuple(media["image_alt_text"]),
                media_captions=tuple(media["media_captions"]),
            )
        return None

    def _iter_json_ld_nodes(self, value: Any) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        if isinstance(value, dict):
            nodes.append(value)
            for child in value.values():
                if isinstance(child, (dict, list)):
                    nodes.extend(self._iter_json_ld_nodes(child))
        elif isinstance(value, list):
            for item in value:
                nodes.extend(self._iter_json_ld_nodes(item))
        return nodes

    @staticmethod
    def _json_ld_type_matches(node: dict[str, Any]) -> bool:
        raw_type = node.get("@type") or node.get("type")
        values = raw_type if isinstance(raw_type, list) else [raw_type]
        for value in values:
            normalized = str(value or "").rsplit("/", 1)[-1].lower()
            if normalized in _ARTICLE_JSONLD_TYPES:
                return True
        return False

    def _json_ld_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return " ".join(unescape(value).split())
        if isinstance(value, list):
            return " ".join(
                text for item in value if (text := self._json_ld_text(item))
            )
        if isinstance(value, dict):
            return self._json_ld_text(
                self._payload_get_any(
                    value,
                    ("text", "articleBody", "description", "name", "headline"),
                )
            )
        return " ".join(str(value).split())

    def _json_ld_author(self, value: Any) -> str | None:
        text = self._json_ld_text(value)
        return text or None

    def _json_ld_image_url(self, value: Any) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        if isinstance(value, list):
            for item in value:
                image_url = self._json_ld_image_url(item)
                if image_url:
                    return image_url
        if isinstance(value, dict):
            return self._json_ld_image_url(
                self._payload_get_any(value, ("url", "contentUrl"))
            )
        return None

    def _json_ld_date(self, value: Any) -> datetime | None:
        text = self._json_ld_text(value)
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        with contextlib.suppress(ValueError):
            return datetime.fromisoformat(text)
        return None

    def _extract_from_html(
        self,
        *,
        url: str,
        html_content: str,
        method: str,
        http_status: int | None = None,
        title_hint: str | None = None,
    ) -> ExtractedArticle:
        json_ld_article = self._article_from_json_ld(
            url=url,
            html_content=html_content,
            method=method,
            http_status=http_status,
            title_hint=title_hint,
        )
        if json_ld_article is not None:
            return json_ld_article

        classified_error = self._classify_content_failure(
            http_status=http_status,
            html_content=html_content,
            title=title_hint or "",
        )
        if classified_error:
            return self._failure(
                url=url,
                error=f"{method} returned {classified_error}",
                error_code=classified_error,
                method=method,
                http_status=http_status,
            )

        try:
            import trafilatura
        except Exception as exc:
            return self._failure(
                url=url,
                error=f"Trafilatura unavailable: {exc}",
                error_code=ERROR_EXCEPTION,
                method=method,
                http_status=http_status,
            )

        result = trafilatura.extract(
            html_content,
            include_comments=False,
            include_tables=False,
            output_format="txt",
        )
        metadata = trafilatura.extract_metadata(html_content)
        media = self._extract_media_metadata(html_content)

        title = (metadata.title if metadata else "") or (title_hint or "")
        author = metadata.author if metadata else None
        date = None
        if metadata and metadata.date:
            with contextlib.suppress(Exception):
                date = datetime.fromisoformat(metadata.date)

        if not result:
            return self._failure(
                url=url,
                error=f"No content extracted via {method}",
                error_code=ERROR_EMPTY_CONTENT,
                method=method,
                http_status=http_status,
            )

        return ExtractedArticle(
            title=title,
            text=result,
            author=author,
            date=date,
            domain=extract_domain(url),
            url=url,
            success=True,
            error=None,
            error_code=None,
            http_status=http_status,
            extractor_method=method,
            og_image_url=media["og_image_url"],
            embedded_post_urls=tuple(media["embedded_post_urls"]),
            image_alt_text=tuple(media["image_alt_text"]),
            media_captions=tuple(media["media_captions"]),
        )

    async def extract_crawl4ai_async(self, url: str) -> ExtractedArticle:
        """Extract using Crawl4AI as the primary article-body method."""
        guard = self._unsafe_url_failure(url, method="url_guard")
        if guard is not None:
            return guard

        try:
            AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig = (
                self._import_crawl4ai_core()
            )
        except Exception as exc:
            return self._failure(
                url=url,
                error=f"Crawl4AI unavailable: {exc}",
                error_code=ERROR_EXCEPTION,
                method="crawl4ai",
            )

        attempts = self._crawl4ai_attempts()
        default_profile = self._crawl4ai_profile("default_news")
        default_attempt = attempts[0]
        result = await self._run_crawl4ai_attempt(
            url=url,
            attempt=default_attempt,
            profile=default_profile,
            AsyncWebCrawler=AsyncWebCrawler,
            BrowserConfig=BrowserConfig,
            CacheMode=CacheMode,
            CrawlerRunConfig=CrawlerRunConfig,
        )

        if result.success:
            return result

        if self._is_retryable_short_failure(result):
            dynamic_profile = self._crawl4ai_profile("dynamic_news")
            dynamic_result = await self._run_crawl4ai_attempt(
                url=url,
                attempt=default_attempt,
                profile=dynamic_profile,
                AsyncWebCrawler=AsyncWebCrawler,
                BrowserConfig=BrowserConfig,
                CacheMode=CacheMode,
                CrawlerRunConfig=CrawlerRunConfig,
            )
            if dynamic_result.success:
                return dynamic_result
            if dynamic_result.error_code != ERROR_BLOCKED_CHALLENGE:
                return dynamic_result
            result = dynamic_result

        if result.error_code != ERROR_BLOCKED_CHALLENGE:
            return result

        last_blocked: ExtractedArticle | None = result
        protected_profile = self._crawl4ai_profile("protected_news")
        for attempt in attempts[1:]:
            result = await self._run_crawl4ai_attempt(
                url=url,
                attempt=attempt,
                profile=protected_profile,
                AsyncWebCrawler=AsyncWebCrawler,
                BrowserConfig=BrowserConfig,
                CacheMode=CacheMode,
                CrawlerRunConfig=CrawlerRunConfig,
            )

            if result.success:
                return result

            if result.error_code != ERROR_BLOCKED_CHALLENGE:
                if (
                    attempt.use_undetected
                    and last_blocked is not None
                    and result.error_code == ERROR_EXCEPTION
                ):
                    logger.info(
                        "Skipping Crawl4AI %s for %s after setup failure: %s",
                        attempt.label,
                        url,
                        result.error,
                    )
                    continue
                return result

            last_blocked = result
            logger.info(
                "Crawl4AI %s was blocked for %s; trying next protected enhancement",
                attempt.label,
                url,
            )

        if last_blocked is not None:
            return last_blocked
        return self._failure(
            url=url,
            error="Crawl4AI extraction failed before any attempt completed",
            error_code=ERROR_PARSE_FAILURE,
            method="crawl4ai",
        )

    def extract_crawl4ai(self, url: str) -> ExtractedArticle:
        """Run Crawl4AI from a synchronous caller."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.extract_crawl4ai_async(url))
        return self._failure(
            url=url,
            error="Crawl4AI sync extraction cannot run inside an asyncio event loop",
            error_code=ERROR_EXCEPTION,
            method="crawl4ai",
        )

    def extract_trafilatura(self, url: str) -> ExtractedArticle:
        """Extract using trafilatura as the first fallback method."""
        guard = self._unsafe_url_failure(url, method="url_guard")
        if guard is not None:
            return guard

        try:
            import trafilatura

            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return self._failure(
                    url=url,
                    error="Failed to download page",
                    error_code=ERROR_PARSE_FAILURE,
                    method="trafilatura",
                )

            return self._extract_from_html(
                url=url,
                html_content=downloaded,
                method="trafilatura",
            )
        except Exception as exc:
            logger.warning("Trafilatura failed for %s: %s", url, exc)
            return self._failure(
                url=url,
                error=str(exc),
                error_code=ERROR_EXCEPTION,
                method="trafilatura",
            )

    def extract_playwright(self, url: str) -> ExtractedArticle:
        """Extract using Playwright sync API (sync-only contexts)."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            return self._failure(
                url=url,
                error=(
                    "Playwright sync API cannot run inside an asyncio event loop; "
                    "call from a sync context or threadpool."
                ),
                error_code=ERROR_EXCEPTION,
                method="playwright_sync",
            )

        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            return self._failure(
                url=url,
                error=f"Playwright unavailable: {exc}",
                error_code=ERROR_EXCEPTION,
                method="playwright_sync",
            )

        try:
            html_content = ""
            body_text = ""
            title = ""
            status: int | None = None

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(args=["--no-sandbox"])
                try:
                    page = browser.new_page()
                    response = page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=PLAYWRIGHT_PAGE_TIMEOUT_MS,
                    )
                    if response is not None:
                        status = response.status
                    title = page.title() or ""
                    html_content = page.content()
                    with contextlib.suppress(Exception):
                        body_text = page.text_content("body") or ""
                finally:
                    browser.close()

            classified_error = self._classify_content_failure(
                http_status=status,
                html_content=html_content,
                body_text=body_text,
                title=title,
            )
            if classified_error:
                return self._failure(
                    url=url,
                    error=f"Playwright returned {classified_error}",
                    error_code=classified_error,
                    method="playwright_sync",
                    http_status=status,
                )

            if not html_content:
                return self._failure(
                    url=url,
                    error="Playwright returned empty content",
                    error_code=ERROR_EMPTY_CONTENT,
                    method="playwright_sync",
                    http_status=status,
                )

            return self._extract_from_html(
                url=url,
                html_content=html_content,
                method="playwright_sync",
                http_status=status,
                title_hint=title,
            )

        except PlaywrightTimeoutError:
            return self._failure(
                url=url,
                error="Playwright timed out",
                error_code=ERROR_TIMEOUT,
                method="playwright_sync",
            )
        except Exception as exc:
            logger.warning("Playwright sync extraction failed for %s: %s", url, exc)
            return self._failure(
                url=url,
                error=str(exc),
                error_code=ERROR_EXCEPTION,
                method="playwright_sync",
            )

    async def extract_trafilatura_async(self, url: str) -> ExtractedArticle:
        """Extract using trafilatura in a worker thread."""
        return await asyncio.to_thread(self.extract_trafilatura, url)

    def _firecrawl_options(
        self,
        *,
        only_main_content: bool,
        proxy_auto: bool,
        legacy_params: bool = False,
    ) -> dict[str, Any]:
        formats = ["markdown", "html", "rawHtml", "links"]
        location = {"country": "US", "languages": ["en-US", "en"]}
        if legacy_params:
            options: dict[str, Any] = {
                "formats": formats,
                "onlyMainContent": only_main_content,
                "waitFor": settings.firecrawl_wait_for_ms,
                "timeout": settings.firecrawl_timeout_ms,
                "location": location,
                "removeBase64Images": True,
                "blockAds": True,
                "maxAge": 0,
                "storeInCache": False,
            }
        else:
            options = {
                "formats": formats,
                "only_main_content": only_main_content,
                "wait_for": settings.firecrawl_wait_for_ms,
                "timeout": settings.firecrawl_timeout_ms,
                "location": location,
                "remove_base64_images": True,
                "block_ads": True,
                "max_age": 0,
                "store_in_cache": False,
            }
        if proxy_auto:
            options["proxy"] = "auto"
        return options

    def _scrape_firecrawl(
        self,
        client: Any,
        *,
        url: str,
        only_main_content: bool,
        proxy_auto: bool,
        legacy_app: bool,
    ) -> Any:
        options = self._firecrawl_options(
            only_main_content=only_main_content,
            proxy_auto=proxy_auto,
            legacy_params=legacy_app,
        )
        if legacy_app:
            try:
                return client.scrape_url(url, params=options)
            except TypeError:
                return client.scrape_url(url)

        try:
            return client.scrape(url=url, **options)
        except TypeError:
            legacy_options = self._firecrawl_options(
                only_main_content=only_main_content,
                proxy_auto=proxy_auto,
                legacy_params=True,
            )
            try:
                return client.scrape(url=url, **legacy_options)
            except TypeError:
                return client.scrape(url=url, formats=options["formats"])

    def _article_from_firecrawl_payload(
        self, result: Any, *, url: str
    ) -> ExtractedArticle:
        data = self._payload_get(result, "data") or result
        metadata = (
            self._payload_get(data, "metadata")
            or self._payload_get(result, "metadata")
            or {}
        )
        markdown_text = self._markdown_text(
            self._payload_get_any(data, ("markdown", "content"))
            or self._payload_get_any(result, ("markdown", "content"))
        )
        html_content = (
            self._payload_get_any(data, ("html", "rawHtml", "raw_html"))
            or self._payload_get_any(result, ("html", "rawHtml", "raw_html"))
            or ""
        )
        status = self._coerce_status(
            self._payload_get_any(data, ("status_code", "statusCode"))
            or self._payload_get_any(result, ("status_code", "statusCode"))
            or self._payload_get_any(metadata, ("status_code", "statusCode"))
        )
        title = (
            self._payload_get(metadata, "title")
            or self._payload_get(data, "title")
            or self._payload_get(result, "title")
            or ""
        )
        final_url = (
            self._payload_get(metadata, "sourceURL")
            or self._payload_get(metadata, "sourceUrl")
            or self._payload_get(metadata, "url")
            or self._payload_get(data, "url")
            or url
        )

        classified_error = self._classify_content_failure(
            http_status=status,
            html_content=html_content,
            body_text=markdown_text,
            title=str(title),
        )
        if classified_error:
            return self._failure(
                url=url,
                error=f"Firecrawl returned {classified_error}",
                error_code=classified_error,
                method="firecrawl",
                http_status=status,
            )

        if not markdown_text and html_content:
            article = self._extract_from_html(
                url=str(final_url),
                html_content=html_content,
                method="firecrawl",
                http_status=status,
                title_hint=str(title),
            )
            if article.success and len(article.text.strip()) < MIN_EXTRACTION_TEXT_LENGTH:
                return self._failure(
                    url=url,
                    error="Firecrawl HTML fallback returned too little content",
                    error_code=ERROR_SHORT_CONTENT,
                    method="firecrawl",
                    http_status=status,
                )
            return article

        if not markdown_text:
            return self._failure(
                url=url,
                error="No content extracted via Firecrawl",
                error_code=ERROR_EMPTY_CONTENT,
                method="firecrawl",
                http_status=status,
            )

        if len(markdown_text.strip()) < MIN_EXTRACTION_TEXT_LENGTH:
            return self._failure(
                url=url,
                error="Firecrawl returned too little article text",
                error_code=ERROR_SHORT_CONTENT,
                method="firecrawl",
                http_status=status,
            )

        media = self._extract_media_metadata(html_content)
        return ExtractedArticle(
            title=str(title or ""),
            text=markdown_text,
            author=None,
            date=None,
            domain=extract_domain(str(final_url)),
            url=str(final_url),
            success=True,
            error=None,
            error_code=None,
            http_status=status,
            extractor_method="firecrawl",
            og_image_url=media["og_image_url"],
            embedded_post_urls=tuple(media["embedded_post_urls"]),
            image_alt_text=tuple(media["image_alt_text"]),
            media_captions=tuple(media["media_captions"]),
        )

    def extract_firecrawl(self, url: str) -> ExtractedArticle:
        """Extract using Firecrawl cloud API as the final fallback."""
        guard = self._unsafe_url_failure(url, method="url_guard")
        if guard is not None:
            return guard

        api_key = (settings.firecrawl_api_key or "").strip()
        if not api_key:
            return self._failure(
                url=url,
                error="Firecrawl fallback skipped because FIRECRAWL_API_KEY is not configured",
                error_code=ERROR_MISSING_API_KEY,
                method="firecrawl_skipped",
            )

        try:
            try:
                from firecrawl import Firecrawl
            except Exception:
                Firecrawl = None
            try:
                from firecrawl import FirecrawlApp
            except Exception:
                FirecrawlApp = None

            if Firecrawl is not None:
                client = Firecrawl(api_key=api_key)
                legacy_app = False
            elif FirecrawlApp is not None:
                client = FirecrawlApp(api_key=api_key)
                legacy_app = True
            else:
                return self._failure(
                    url=url,
                    error="Firecrawl SDK unavailable",
                    error_code=ERROR_EXCEPTION,
                    method="firecrawl",
                )

            result = self._scrape_firecrawl(
                client,
                url=url,
                only_main_content=True,
                proxy_auto=False,
                legacy_app=legacy_app,
            )
            article = self._article_from_firecrawl_payload(result, url=url)
            if article.success:
                return article

            if self._is_retryable_short_failure(article):
                retry_result = self._scrape_firecrawl(
                    client,
                    url=url,
                    only_main_content=False,
                    proxy_auto=False,
                    legacy_app=legacy_app,
                )
                retry_article = self._article_from_firecrawl_payload(
                    retry_result,
                    url=url,
                )
                if retry_article.success:
                    return retry_article
                article = retry_article

            if (
                article.error_code == ERROR_BLOCKED_CHALLENGE
                and settings.firecrawl_proxy_auto_enabled
            ):
                proxy_result = self._scrape_firecrawl(
                    client,
                    url=url,
                    only_main_content=False,
                    proxy_auto=True,
                    legacy_app=legacy_app,
                )
                return self._article_from_firecrawl_payload(proxy_result, url=url)

            return article

        except Exception as exc:
            logger.warning("Firecrawl failed for %s: %s", url, exc)
            return self._failure(
                url=url,
                error=str(exc),
                error_code=ERROR_EXCEPTION,
                method="firecrawl",
            )

    async def extract_firecrawl_async(self, url: str) -> ExtractedArticle:
        """Extract using Firecrawl in a worker thread."""
        return await asyncio.to_thread(self.extract_firecrawl, url)

    async def extract_playwright_async(self, url: str) -> ExtractedArticle:
        """Extract using Playwright async API (fallback for dynamic/paywalled sites)."""
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except Exception as exc:
            return self._failure(
                url=url,
                error=f"Playwright unavailable: {exc}",
                error_code=ERROR_EXCEPTION,
                method="playwright_async",
            )

        try:
            html_content = ""
            body_text = ""
            title = ""
            status: int | None = None

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(args=["--no-sandbox"])
                try:
                    page = await browser.new_page()
                    response = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=PLAYWRIGHT_PAGE_TIMEOUT_MS,
                    )
                    if response is not None:
                        status = response.status
                    title = await page.title()
                    html_content = await page.content()
                    with contextlib.suppress(Exception):
                        body_text = await page.text_content("body") or ""
                finally:
                    await browser.close()

            classified_error = self._classify_content_failure(
                http_status=status,
                html_content=html_content,
                body_text=body_text,
                title=title,
            )
            if classified_error:
                return self._failure(
                    url=url,
                    error=f"Playwright returned {classified_error}",
                    error_code=classified_error,
                    method="playwright_async",
                    http_status=status,
                )

            if not html_content:
                return self._failure(
                    url=url,
                    error="Playwright returned empty content",
                    error_code=ERROR_EMPTY_CONTENT,
                    method="playwright_async",
                    http_status=status,
                )

            return await asyncio.to_thread(
                self._extract_from_html,
                url=url,
                html_content=html_content,
                method="playwright_async",
                http_status=status,
                title_hint=title,
            )

        except PlaywrightTimeoutError:
            return self._failure(
                url=url,
                error="Playwright timed out",
                error_code=ERROR_TIMEOUT,
                method="playwright_async",
            )
        except Exception as exc:
            logger.warning("Playwright async extraction failed for %s: %s", url, exc)
            return self._failure(
                url=url,
                error=str(exc),
                error_code=ERROR_EXCEPTION,
                method="playwright_async",
            )

    def extract(self, url: str) -> ExtractedArticle:
        """Extract article with automatic fallback."""
        _log_extractor_version_once()

        guard = self._unsafe_url_failure(url, method="url_guard")
        if guard is not None:
            return guard

        result = self.extract_crawl4ai(url)
        if result.success and len(result.text) > MIN_EXTRACTION_TEXT_LENGTH:
            return result

        logger.info("Falling back to trafilatura for %s", url)
        result = self.extract_trafilatura(url)
        if result.success and len(result.text) > MIN_EXTRACTION_TEXT_LENGTH:
            return result

        logger.info("Falling back to Playwright sync for %s", url)
        result = self.extract_playwright(url)
        if result.success and len(result.text) > MIN_EXTRACTION_TEXT_LENGTH:
            return result

        logger.info("Falling back to Firecrawl for %s", url)
        return self.extract_firecrawl(url)

    def _extract_media_metadata(self, html_content: str) -> _MediaMetadata:
        parser = _MediaHTMLParser()
        with contextlib.suppress(Exception):
            parser.feed(html_content or "")

        image_urls = self._dedupe(parser.image_urls)
        return {
            "og_image_url": image_urls[0] if image_urls else None,
            "embedded_post_urls": self._dedupe(parser.post_urls)[:10],
            "image_alt_text": self._dedupe(parser.alt_texts)[:10],
            "media_captions": self._dedupe(parser.captions)[:10],
        }

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    async def extract_async(self, url: str) -> ExtractedArticle:
        """Extract article with automatic fallback (async-safe)."""
        _log_extractor_version_once()

        guard = self._unsafe_url_failure(url, method="url_guard")
        if guard is not None:
            return guard

        result = await self.extract_crawl4ai_async(url)
        if result.success and len(result.text) > MIN_EXTRACTION_TEXT_LENGTH:
            return result

        logger.info("Falling back to trafilatura for %s", url)
        result = await self.extract_trafilatura_async(url)
        if result.success and len(result.text) > MIN_EXTRACTION_TEXT_LENGTH:
            return result

        logger.info("Falling back to Playwright async for %s", url)
        result = await self.extract_playwright_async(url)
        if result.success and len(result.text) > MIN_EXTRACTION_TEXT_LENGTH:
            return result

        logger.info("Falling back to Firecrawl for %s", url)
        return await self.extract_firecrawl_async(url)


class ArticleExtractorTool(BaseTool):
    """CrewAI tool for article content extraction."""

    name: str = "Article Extractor"
    description: str = """Extracts the full text content from a news article URL.
    Returns the article title, author, publication date, and full text.
    Use this to get the complete content of a news article for analysis."""

    def run(self, *args, **kwargs):
        """Return awaitable in async contexts to avoid blocking extraction."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return super().run(*args, **kwargs)
        return self._arun(*args, **kwargs)

    @staticmethod
    def _format_article_output(article: ExtractedArticle, url: str) -> str:
        if not article.success:
            error_code = f" [{article.error_code}]" if article.error_code else ""
            method = (
                f" via {article.extractor_method}" if article.extractor_method else ""
            )
            return f"Failed to extract article from {url}{method}{error_code}: {article.error}"

        date_str = article.date.strftime("%Y-%m-%d") if article.date else "Unknown"
        author_str = article.author or "Unknown"

        output = f"""=== EXTRACTED ARTICLE ===
Title: {article.title}
Source: {article.domain}
Author: {author_str}
Date: {date_str}
URL: {article.url}
Method: {article.extractor_method or "unknown"}

=== FULL TEXT ===
{article.text[:CONTENT_PREVIEW_CHARS]}
"""
        if len(article.text) > CONTENT_PREVIEW_CHARS:
            output += f"\n[Content truncated - showing first {CONTENT_PREVIEW_CHARS} characters]"

        return output

    def _run(self, url: str) -> str | Awaitable[str]:
        """Execute article extraction.

        Args:
            url: The URL of the article to extract

        Returns:
            Formatted string with article content
        """
        # Some CrewAI adapters call _run directly. Return an awaitable in async
        # contexts so blocking extraction paths are never invoked on the event loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            return self._arun(url)

        extractor = ArticleExtractor()
        article = extractor.extract(url)
        return self._format_article_output(article, url)

    async def _arun(self, url: str) -> str:
        """Execute article extraction asynchronously."""
        extractor = ArticleExtractor()
        article = await extractor.extract_async(url)
        return self._format_article_output(article, url)


class MultiArticleExtractorTool(BaseTool):
    """CrewAI tool for extracting multiple articles."""

    name: str = "Multi-Article Extractor"
    description: str = """Extracts content from multiple article URLs at once.
    Provide URLs separated by newlines or commas.
    Returns extracted content for each article."""

    @staticmethod
    def _parse_urls(urls: str) -> list[str]:
        url_list = []
        for line in urls.replace(",", "\n").split("\n"):
            url = line.strip()
            if url.startswith("http"):
                url_list.append(url)
        return url_list[:MULTI_ARTICLE_MAX_URLS]

    @staticmethod
    def _format_result(index: int, url: str, article: ExtractedArticle) -> str:
        if article.success:
            return (
                f"--- Article {index} ---\n"
                f"Title: {article.title}\n"
                f"Source: {article.domain}\n"
                f"URL: {url}\n"
                f"Method: {article.extractor_method or 'unknown'}\n"
                f"Length: {len(article.text)} characters\n"
            )
        return (
            f"--- Article {index} ---\n"
            f"URL: {url}\n"
            f"Method: {article.extractor_method or 'unknown'}\n"
            f"Error Code: {article.error_code or 'unknown'}\n"
            f"Error: {article.error}\n"
        )

    async def _extract_many_async(
        self, extractor: ArticleExtractor, url_list: list[str]
    ) -> list[ExtractedArticle]:
        semaphore = asyncio.Semaphore(MULTI_ARTICLE_CONCURRENCY_LIMIT)

        async def one(url: str) -> ExtractedArticle:
            async with semaphore:
                return await extractor.extract_async(url)

        return await asyncio.gather(*(one(url) for url in url_list))

    def _extract_many_sync(
        self, extractor: ArticleExtractor, url_list: list[str]
    ) -> list[ExtractedArticle]:
        max_workers = min(MULTI_ARTICLE_CONCURRENCY_LIMIT, len(url_list))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(extractor.extract, url_list))

    def run(self, *args, **kwargs):
        """Return awaitable in async contexts to avoid blocking extraction."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return super().run(*args, **kwargs)
        return self._arun(*args, **kwargs)

    def _run(self, urls: str) -> str | Awaitable[str]:
        """Extract multiple articles.

        Args:
            urls: Newline or comma-separated URLs

        Returns:
            Combined extraction results
        """
        # Some CrewAI adapters call _run directly. Return an awaitable in async
        # contexts so blocking extraction paths are never invoked on the event loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            return self._arun(urls)

        url_list = self._parse_urls(urls)

        if not url_list:
            return "No valid URLs provided."

        extractor = ArticleExtractor()
        articles = self._extract_many_sync(extractor, url_list)
        results = [
            self._format_result(i, url, article)
            for i, (url, article) in enumerate(zip(url_list, articles, strict=True), 1)
        ]

        return "\n".join(results)

    async def _arun(self, urls: str) -> str:
        """Extract multiple articles asynchronously."""
        url_list = self._parse_urls(urls)

        if not url_list:
            return "No valid URLs provided."

        extractor = ArticleExtractor()
        articles = await self._extract_many_async(extractor, url_list)
        results = [
            self._format_result(i, url, article)
            for i, (url, article) in enumerate(zip(url_list, articles, strict=True), 1)
        ]

        return "\n".join(results)
