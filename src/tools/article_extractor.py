"""Article Content Extraction Tool for CrewAI."""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from crewai.tools.base_tool import BaseTool

from src.core.config import settings

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "2026-02-05-rss-selenium-fallback-v1"
_VERSION_LOGGED = False

ERROR_BLOCKED_CHALLENGE = "blocked_challenge"
ERROR_HTTP_403 = "http_403"
ERROR_EMPTY_CONTENT = "empty_content"
ERROR_TIMEOUT = "timeout"
ERROR_PARSE_FAILURE = "parse_failure"
ERROR_EXCEPTION = "exception"

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

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.replace("www.", "")
        except Exception:
            return ""

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
            domain=self._extract_domain(url),
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
            domain=self._extract_domain(url),
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

    def extract_newspaper(self, url: str) -> ExtractedArticle:
        """Extract using newspaper4k (fallback method)."""
        try:
            from newspaper import Article

            article = Article(url)
            article.download()
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
                domain=self._extract_domain(url),
                url=url,
                success=True,
                error=None,
                error_code=None,
                extractor_method="newspaper4k",
                og_image_url=article.top_image or None,
            )

        except Exception as exc:
            logger.warning("Newspaper4k failed for %s: %s", url, exc)
            msg = str(exc)
            code = (
                ERROR_HTTP_403 if "status code 403" in msg.lower() else ERROR_EXCEPTION
            )
            status = 403 if code == ERROR_HTTP_403 else None
            return self._failure(
                url=url,
                error=msg,
                error_code=code,
                method="newspaper4k",
                http_status=status,
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
                        url, wait_until="domcontentloaded", timeout=25000
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
            driver.get(url)

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
                        url, wait_until="domcontentloaded", timeout=25000
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

    async def extract_selenium_async(self, url: str) -> ExtractedArticle:
        """Run Selenium extraction in a worker thread."""
        return await asyncio.to_thread(self.extract_selenium, url)

    def extract(self, url: str) -> ExtractedArticle:
        """Extract article with automatic fallback."""
        _log_extractor_version_once()

        result = self.extract_trafilatura(url)
        if result.success and len(result.text) > 100:
            return result

        logger.info("Falling back to newspaper4k for %s", url)
        result = self.extract_newspaper(url)
        if result.success and len(result.text) > 100:
            return result

        logger.info("Falling back to Playwright sync for %s", url)
        result = self.extract_playwright(url)
        if result.success and len(result.text) > 100:
            return result

        if settings.enable_selenium_fallback:
            logger.info("Falling back to Selenium for %s", url)
            selenium_result = self.extract_selenium(url)
            if selenium_result.success and len(selenium_result.text) > 100:
                return selenium_result
            return selenium_result

        return result

    def _extract_media_metadata(self, html_content: str) -> dict[str, object]:
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

        result = await self.extract_trafilatura_async(url)
        if result.success and len(result.text) > 100:
            return result

        logger.info("Falling back to newspaper4k for %s", url)
        result = await self.extract_newspaper_async(url)
        if result.success and len(result.text) > 100:
            return result

        logger.info("Falling back to Playwright async for %s", url)
        result = await self.extract_playwright_async(url)
        if result.success and len(result.text) > 100:
            return result

        if settings.enable_selenium_fallback:
            logger.info("Falling back to Selenium for %s", url)
            selenium_result = await self.extract_selenium_async(url)
            if selenium_result.success and len(selenium_result.text) > 100:
                return selenium_result
            return selenium_result

        return result


class ArticleExtractorTool(BaseTool):
    """CrewAI tool for article content extraction."""

    name: str = "Article Extractor"
    description: str = """Extracts the full text content from a news article URL.
    Returns the article title, author, publication date, and full text.
    Use this to get the complete content of a news article for analysis."""

    def run(self, *args, **kwargs):
        """Return awaitable in async contexts to avoid sync Playwright in event loop."""
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
{article.text[:10000]}
"""
        if len(article.text) > 10000:
            output += "\n[Content truncated - showing first 10000 characters]"

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

    def run(self, *args, **kwargs):
        """Return awaitable in async contexts to avoid sync Playwright in event loop."""
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
        # contexts so sync extraction paths are never invoked on the event loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            return self._arun(urls)

        url_list = []
        for line in urls.replace(",", "\n").split("\n"):
            url = line.strip()
            if url.startswith("http"):
                url_list.append(url)

        if not url_list:
            return "No valid URLs provided."

        extractor = ArticleExtractor()
        results = []

        for i, url in enumerate(url_list[:10], 1):
            article = extractor.extract(url)

            if article.success:
                results.append(
                    f"--- Article {i} ---\n"
                    f"Title: {article.title}\n"
                    f"Source: {article.domain}\n"
                    f"URL: {url}\n"
                    f"Method: {article.extractor_method or 'unknown'}\n"
                    f"Length: {len(article.text)} characters\n"
                )
            else:
                results.append(
                    f"--- Article {i} ---\n"
                    f"URL: {url}\n"
                    f"Method: {article.extractor_method or 'unknown'}\n"
                    f"Error Code: {article.error_code or 'unknown'}\n"
                    f"Error: {article.error}\n"
                )

        return "\n".join(results)

    async def _arun(self, urls: str) -> str:
        """Extract multiple articles asynchronously."""
        url_list = []
        for line in urls.replace(",", "\n").split("\n"):
            url = line.strip()
            if url.startswith("http"):
                url_list.append(url)

        if not url_list:
            return "No valid URLs provided."

        extractor = ArticleExtractor()
        results = []

        for i, url in enumerate(url_list[:10], 1):
            article = await extractor.extract_async(url)

            if article.success:
                results.append(
                    f"--- Article {i} ---\n"
                    f"Title: {article.title}\n"
                    f"Source: {article.domain}\n"
                    f"URL: {url}\n"
                    f"Method: {article.extractor_method or 'unknown'}\n"
                    f"Length: {len(article.text)} characters\n"
                )
            else:
                results.append(
                    f"--- Article {i} ---\n"
                    f"URL: {url}\n"
                    f"Method: {article.extractor_method or 'unknown'}\n"
                    f"Error Code: {article.error_code or 'unknown'}\n"
                    f"Error: {article.error}\n"
                )

        return "\n".join(results)
