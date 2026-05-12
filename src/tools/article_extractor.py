"""Article Content Extraction Tool for CrewAI."""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, TypedDict, cast
from urllib.parse import urljoin

import httpx
from crewai.tools.base_tool import BaseTool

from src.core.config import settings
from src.utils.url_utils import (
    UnsafeUrlError,
    blocked_public_url_reason,
    extract_domain,
    validate_public_http_url,
)

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "2026-02-05-rss-selenium-fallback-v1"
_VERSION_LOGGED = False

ERROR_BLOCKED_CHALLENGE = "blocked_challenge"
ERROR_HTTP_403 = "http_403"
ERROR_EMPTY_CONTENT = "empty_content"
ERROR_TIMEOUT = "timeout"
ERROR_PARSE_FAILURE = "parse_failure"
ERROR_EXCEPTION = "exception"
ERROR_UNSAFE_URL = "unsafe_url"

MIN_EXTRACTION_TEXT_LENGTH = 100
PLAYWRIGHT_PAGE_TIMEOUT_MS = 25000


class MediaMetadata(TypedDict):
    og_image_url: str | None
    embedded_post_urls: list[str]
    image_alt_text: list[str]
    media_captions: list[str]


CONTENT_PREVIEW_CHARS = 10000
MULTI_ARTICLE_MAX_URLS = 10
MULTI_ARTICLE_CONCURRENCY_LIMIT = 4
MAX_SAFE_REDIRECTS = 5

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
    """Extracts article content from URLs using multiple methods."""

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

    def _unsafe_url_failure(
        self,
        *,
        url: str,
        method: str,
        reason: str,
    ) -> ExtractedArticle:
        return self._failure(
            url=url,
            error=reason,
            error_code=ERROR_UNSAFE_URL,
            method=method,
        )

    def _validate_url_for_fetch(
        self, url: str, *, method: str
    ) -> str | ExtractedArticle:
        try:
            return validate_public_http_url(url)
        except UnsafeUrlError as exc:
            return self._unsafe_url_failure(
                url=url,
                method=method,
                reason=exc.reason,
            )

    def _safe_prefetch_html(self, url: str) -> tuple[str, int | None, str]:
        current_url = validate_public_http_url(url)
        timeout = max(1, settings.analysis_rss_timeout_seconds)
        headers = {"User-Agent": "ResearchAgent/1.0"}

        with httpx.Client(
            follow_redirects=False,
            timeout=timeout,
            headers=headers,
        ) as client:
            for redirect_count in range(MAX_SAFE_REDIRECTS + 1):
                response = client.get(current_url)
                if response.is_redirect:
                    if redirect_count >= MAX_SAFE_REDIRECTS:
                        raise UnsafeUrlError("too_many_redirects")
                    location = response.headers.get("location")
                    if not location:
                        raise UnsafeUrlError("invalid_redirect")
                    current_url = validate_public_http_url(
                        urljoin(str(response.url), location)
                    )
                    continue

                response.raise_for_status()
                final_url = validate_public_http_url(str(response.url))
                return response.text, response.status_code, final_url

        raise UnsafeUrlError("too_many_redirects")

    def _extract_from_html(
        self,
        *,
        url: str,
        html_content: str,
        method: str,
        http_status: int | None = None,
        title_hint: str | None = None,
    ) -> ExtractedArticle:
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

    def extract_trafilatura(self, url: str) -> ExtractedArticle:
        """Extract using trafilatura (primary method)."""
        validated = self._validate_url_for_fetch(url, method="trafilatura")
        if isinstance(validated, ExtractedArticle):
            return validated

        try:
            downloaded, http_status, final_url = self._safe_prefetch_html(validated)
            if not downloaded:
                return self._failure(
                    url=url,
                    error="Failed to download page",
                    error_code=ERROR_PARSE_FAILURE,
                    method="trafilatura",
                )

            return self._extract_from_html(
                url=final_url,
                html_content=downloaded,
                method="trafilatura",
                http_status=http_status,
            )
        except UnsafeUrlError as exc:
            return self._unsafe_url_failure(
                url=url,
                method="trafilatura",
                reason=exc.reason,
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            code = ERROR_HTTP_403 if status == 403 else ERROR_EXCEPTION
            logger.warning("Trafilatura fetch failed for %s: %s", url, exc)
            return self._failure(
                url=url,
                error=f"HTTP status {status}",
                error_code=code,
                method="trafilatura",
                http_status=status,
            )
        except Exception as exc:
            logger.warning("Trafilatura failed for %s: %s", url, exc)
            return self._failure(
                url=url,
                error=str(exc),
                error_code=ERROR_EXCEPTION,
                method="trafilatura",
            )

    def extract_newspaper(self, url: str) -> ExtractedArticle:
        """Extract using newspaper4k (fallback method)."""
        validated = self._validate_url_for_fetch(url, method="newspaper4k")
        if isinstance(validated, ExtractedArticle):
            return validated

        try:
            from newspaper import Article

            downloaded, http_status, final_url = self._safe_prefetch_html(validated)
            article = Article(final_url)
            article.download(input_html=downloaded)
            article.parse()

            date = None
            if article.publish_date:
                if isinstance(article.publish_date, datetime):
                    date = article.publish_date
                else:
                    with contextlib.suppress(Exception):
                        date = datetime.fromisoformat(str(article.publish_date))

            authors = article.authors
            author = authors[0] if authors else None

            if not article.text:
                return self._failure(
                    url=url,
                    error="No content extracted via newspaper4k",
                    error_code=ERROR_EMPTY_CONTENT,
                    method="newspaper4k",
                )

            return ExtractedArticle(
                title=article.title or "",
                text=article.text,
                author=author,
                date=date,
                domain=extract_domain(final_url),
                url=final_url,
                success=True,
                error=None,
                error_code=None,
                http_status=http_status,
                extractor_method="newspaper4k",
                og_image_url=article.top_image or None,
            )

        except UnsafeUrlError as exc:
            return self._unsafe_url_failure(
                url=url,
                method="newspaper4k",
                reason=exc.reason,
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            code = ERROR_HTTP_403 if status_code == 403 else ERROR_EXCEPTION
            return self._failure(
                url=url,
                error=f"HTTP status {status_code}",
                error_code=code,
                method="newspaper4k",
                http_status=status_code,
            )
        except Exception as exc:
            logger.warning("Newspaper4k failed for %s: %s", url, exc)
            msg = str(exc)
            code = (
                ERROR_HTTP_403 if "status code 403" in msg.lower() else ERROR_EXCEPTION
            )
            fallback_status: int | None = 403 if code == ERROR_HTTP_403 else None
            return self._failure(
                url=url,
                error=msg,
                error_code=code,
                method="newspaper4k",
                http_status=fallback_status,
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

        validated = self._validate_url_for_fetch(url, method="playwright_sync")
        if isinstance(validated, ExtractedArticle):
            return validated

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
                    page.route("**/*", self._guarded_playwright_route)
                    response = page.goto(
                        validated,
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

            if status == 403 or self._looks_blocked(html_content, body_text, title):
                return self._failure(
                    url=url,
                    error="Blocked by anti-bot challenge while using Playwright",
                    error_code=ERROR_BLOCKED_CHALLENGE,
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
                url=validated,
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

    def _chrome_binary_location(self) -> str | None:
        candidates = (
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
        )
        for candidate in candidates:
            if Path(candidate).exists():
                return candidate
        return None

    def _chromedriver_location(self) -> str | None:
        candidates = (
            "/usr/bin/chromedriver",
            "/usr/lib/chromium/chromedriver",
        )
        for candidate in candidates:
            if Path(candidate).exists():
                return candidate
        return None

    def _selenium_user_agents(self) -> list[str]:
        raw = settings.selenium_user_agents or ""
        user_agents = [item.strip() for item in raw.split("||") if item.strip()]
        if not user_agents:
            return [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ]
        return user_agents

    def _extract_selenium_sync(
        self, url: str, user_agent: str | None
    ) -> ExtractedArticle:
        """Extract page using Selenium Chrome driver."""
        validated = self._validate_url_for_fetch(url, method="selenium")
        if isinstance(validated, ExtractedArticle):
            return validated

        try:
            from selenium import webdriver
            from selenium.common.exceptions import TimeoutException, WebDriverException
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
        except Exception as exc:
            return self._failure(
                url=url,
                error=f"Selenium unavailable: {exc}",
                error_code=ERROR_EXCEPTION,
                method="selenium",
            )

        options = Options()
        if settings.selenium_headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1440,2200")
        if user_agent:
            options.add_argument(f"--user-agent={user_agent}")

        chrome_binary = self._chrome_binary_location()
        if chrome_binary:
            options.binary_location = chrome_binary

        driver = None
        try:
            chromedriver = self._chromedriver_location()
            service = (
                Service(executable_path=chromedriver) if chromedriver else Service()
            )
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(settings.selenium_timeout_seconds)
            driver.get(validated)

            html_content = driver.page_source or ""
            title = driver.title or ""
            body_text = ""
            with contextlib.suppress(Exception):
                body_text = driver.find_element(By.TAG_NAME, "body").text or ""

            if self._looks_blocked(html_content, body_text, title):
                return self._failure(
                    url=url,
                    error="Blocked by anti-bot challenge while using Selenium",
                    error_code=ERROR_BLOCKED_CHALLENGE,
                    method="selenium",
                )

            if not html_content:
                return self._failure(
                    url=url,
                    error="Selenium returned empty content",
                    error_code=ERROR_EMPTY_CONTENT,
                    method="selenium",
                )

            return self._extract_from_html(
                url=url,
                html_content=html_content,
                method="selenium",
                title_hint=title,
            )

        except TimeoutException:
            return self._failure(
                url=url,
                error="Selenium timed out",
                error_code=ERROR_TIMEOUT,
                method="selenium",
            )
        except WebDriverException as exc:
            logger.warning("Selenium extraction failed for %s: %s", url, exc)
            return self._failure(
                url=url,
                error=str(exc),
                error_code=ERROR_EXCEPTION,
                method="selenium",
            )
        except Exception as exc:
            logger.warning("Selenium extraction failed for %s: %s", url, exc)
            return self._failure(
                url=url,
                error=str(exc),
                error_code=ERROR_EXCEPTION,
                method="selenium",
            )
        finally:
            if driver is not None:
                with contextlib.suppress(Exception):
                    driver.quit()

    def extract_selenium(self, url: str) -> ExtractedArticle:
        """Try Selenium extraction with configurable user-agent attempts."""
        if not settings.enable_selenium_fallback:
            return self._failure(
                url=url,
                error="Selenium fallback disabled",
                error_code=ERROR_EXCEPTION,
                method="selenium",
            )

        user_agents = self._selenium_user_agents()
        max_attempts = max(1, settings.max_selenium_attempts)
        attempts = user_agents[:max_attempts]

        last_result: ExtractedArticle | None = None
        for user_agent in attempts:
            result = self._extract_selenium_sync(url, user_agent)
            if result.success:
                return result
            last_result = result
            if result.error_code == ERROR_BLOCKED_CHALLENGE:
                continue

        return last_result or self._failure(
            url=url,
            error="Selenium fallback failed",
            error_code=ERROR_EXCEPTION,
            method="selenium",
        )

    async def extract_trafilatura_async(self, url: str) -> ExtractedArticle:
        """Extract using trafilatura in a thread to avoid blocking."""
        return await asyncio.to_thread(self.extract_trafilatura, url)

    async def extract_newspaper_async(self, url: str) -> ExtractedArticle:
        """Extract using newspaper4k in a thread to avoid blocking."""
        return await asyncio.to_thread(self.extract_newspaper, url)

    async def extract_playwright_async(self, url: str) -> ExtractedArticle:
        """Extract using Playwright async API (fallback for dynamic/paywalled sites)."""
        validated = self._validate_url_for_fetch(url, method="playwright_async")
        if isinstance(validated, ExtractedArticle):
            return validated

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
                    await page.route("**/*", self._guarded_playwright_route_async)
                    response = await page.goto(
                        validated,
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

            if status == 403 or self._looks_blocked(html_content, body_text, title):
                return self._failure(
                    url=url,
                    error="Blocked by anti-bot challenge while using Playwright",
                    error_code=ERROR_BLOCKED_CHALLENGE,
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
                url=validated,
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

    async def extract_selenium_async(self, url: str) -> ExtractedArticle:
        """Run Selenium extraction in a worker thread."""
        return await asyncio.to_thread(self.extract_selenium, url)

    @staticmethod
    def _guarded_playwright_route(route: Any) -> None:
        reason = blocked_public_url_reason(route.request.url)
        if reason:
            route.abort()
            return
        route.continue_()

    @staticmethod
    async def _guarded_playwright_route_async(route: Any) -> None:
        reason = blocked_public_url_reason(route.request.url)
        if reason:
            await route.abort()
            return
        await route.continue_()

    def extract(self, url: str) -> ExtractedArticle:
        """Extract article with automatic fallback."""
        _log_extractor_version_once()
        validated = self._validate_url_for_fetch(url, method="url_validation")
        if isinstance(validated, ExtractedArticle):
            return validated

        result = self.extract_trafilatura(validated)
        if result.success and len(result.text) > MIN_EXTRACTION_TEXT_LENGTH:
            return result

        logger.info("Falling back to newspaper4k for %s", url)
        result = self.extract_newspaper(validated)
        if result.success and len(result.text) > MIN_EXTRACTION_TEXT_LENGTH:
            return result

        logger.info("Falling back to Playwright sync for %s", url)
        result = self.extract_playwright(validated)
        if result.success and len(result.text) > MIN_EXTRACTION_TEXT_LENGTH:
            return result

        # Selenium cannot intercept redirects or subresource requests here, so
        # automatic untrusted fallback stays disabled.
        return result

    def _extract_media_metadata(self, html_content: str) -> MediaMetadata:
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
        validated = self._validate_url_for_fetch(url, method="url_validation")
        if isinstance(validated, ExtractedArticle):
            return validated

        result = await self.extract_trafilatura_async(validated)
        if result.success and len(result.text) > MIN_EXTRACTION_TEXT_LENGTH:
            return result

        logger.info("Falling back to newspaper4k for %s", url)
        result = await self.extract_newspaper_async(validated)
        if result.success and len(result.text) > MIN_EXTRACTION_TEXT_LENGTH:
            return result

        logger.info("Falling back to Playwright async for %s", url)
        result = await self.extract_playwright_async(validated)
        if result.success and len(result.text) > MIN_EXTRACTION_TEXT_LENGTH:
            return result

        # Selenium cannot intercept redirects or subresource requests here, so
        # automatic untrusted fallback stays disabled.
        return result


class ArticleExtractorTool(BaseTool):
    """CrewAI tool for article content extraction."""

    name: str = "Article Extractor"
    description: str = """Extracts the full text content from a news article URL.
    Returns the article title, author, publication date, and full text.
    Use this to get the complete content of a news article for analysis."""

    def run(self, *args: Any, **kwargs: Any) -> str | Awaitable[str]:
        """Return awaitable in async contexts to avoid sync Playwright in event loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return cast(str, super().run(*args, **kwargs))
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
        # contexts so sync extraction paths are never invoked on the event loop.
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

    def run(self, *args: Any, **kwargs: Any) -> str | Awaitable[str]:
        """Return awaitable in async contexts to avoid sync Playwright in event loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return cast(str, super().run(*args, **kwargs))
        return self._arun(*args, **kwargs)

    def _run(self, urls: str) -> str | Awaitable[str]:
        """Extract multiple articles.

        Args:
            urls: Newline or comma-separated URLs

        Returns:
            Combined extraction results
        """
        # Some CrewAI adapters call _run directly. Return an awaitable in async
        # contexts so sync extraction paths are never invoked on the event loop.
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
