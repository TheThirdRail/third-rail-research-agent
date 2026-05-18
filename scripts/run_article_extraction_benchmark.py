"""Manual live benchmark for the ArticleExtractor fallback stack."""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_URLS_PATH = PROJECT_ROOT / "Agent-Context" / "Research" / (
    "article_extraction_live_urls.txt"
)
LOCAL_EVIDENCE_PATHS = (
    PROJECT_ROOT / "Agent-Context" / "Communications" / "Agent-Notes" / (
        "codex-findings.md"
    ),
    PROJECT_ROOT / "Agent-Context" / "Communications" / "Agent-Notes" / (
        "docker-backend-log-errors-2026-05-16.md"
    ),
    PROJECT_ROOT / "token-usage" / "token-usage-report.json",
    PROJECT_ROOT / "token-usage" / "token-usage.jsonl",
)
URL_RE = re.compile(r"https?://[^\s\]\)\"'<>]+")
SKIP_HOST_FRAGMENTS = (
    "127.0.0.1",
    "localhost",
    "host.docker.internal",
    "eb2.3lift.com",
    "ad.doubleclick.net",
    "goto.walmart.com",
)
SKIP_PATH_FRAGMENTS = (
    "/feed",
    "/feeds",
    "/market-data/",
    "/rss",
    "/content-images/",
    "/dims3/",
)
SKIP_EXTENSIONS = (".gif", ".jpg", ".jpeg", ".png", ".svg", ".webp")


def _normalize_url(raw: str) -> str | None:
    candidate = raw.replace("\\n", "\n").splitlines()[0]
    candidate = candidate.strip().strip("`.,;)")
    if not candidate:
        return None

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    lowered = candidate.lower()
    if any(fragment in lowered for fragment in SKIP_HOST_FRAGMENTS):
        return None
    if any(fragment in lowered for fragment in SKIP_PATH_FRAGMENTS):
        return None
    if parsed.path.lower().endswith(SKIP_EXTENSIONS):
        return None
    return candidate


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        normalized = _normalize_url(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _urls_from_json(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        urls: list[str] = []
        for item in value:
            urls.extend(_urls_from_json(item))
        return urls
    if isinstance(value, dict):
        urls = []
        for key, item in value.items():
            if key.lower() in {
                "articles",
                "links_provided",
                "results",
                "source_url",
                "sourceurl",
                "url",
                "urls",
            }:
                urls.extend(_urls_from_json(item))
        return urls
    return []


def load_url_file(path: Path) -> list[str]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        try:
            return _dedupe_urls(_urls_from_json(json.loads(text)))
        except json.JSONDecodeError:
            pass

    urls: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        urls.extend(match.group(0) for match in URL_RE.finditer(stripped))
        if not URL_RE.search(stripped):
            urls.append(stripped)
    return _dedupe_urls(urls)


def discover_local_urls() -> list[str]:
    urls: list[str] = []
    for path in LOCAL_EVIDENCE_PATHS:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        urls.extend(match.group(0) for match in URL_RE.finditer(text))
        if path.suffix.lower() == ".json":
            with contextlib.suppress(json.JSONDecodeError):
                urls.extend(_urls_from_json(json.loads(text)))
    return _dedupe_urls(urls)


def benchmark_url(
    extractor: Any,
    url: str,
    *,
    minimum_text_length: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        article = extractor.extract(url)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        text_length = len(article.text or "")
        passed = (
            article.success
            and text_length >= minimum_text_length
            and article.error_code is None
        )
        if passed:
            reason = "ok"
        elif article.error_code:
            reason = article.error_code
        elif text_length < minimum_text_length:
            reason = "short_content"
        else:
            reason = article.error or "failed"
        return {
            "url": url,
            "domain": article.domain,
            "passed": passed,
            "success": article.success,
            "method": article.extractor_method,
            "status": "passed" if passed else "failed",
            "error_code": article.error_code,
            "error": article.error,
            "http_status": article.http_status,
            "text_length": text_length,
            "elapsed_ms": elapsed_ms,
            "reason": reason,
        }
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "url": url,
            "domain": urlparse(url).netloc,
            "passed": False,
            "success": False,
            "method": None,
            "status": "failed",
            "error_code": "exception",
            "error": str(exc),
            "http_status": None,
            "text_length": 0,
            "elapsed_ms": elapsed_ms,
            "reason": "exception",
        }


def render_markdown(
    results: list[dict[str, Any]],
    *,
    minimum_text_length: int,
) -> str:
    passed = sum(1 for item in results if item["passed"])
    total = len(results)
    lines = [
        "# Article Extraction Benchmark",
        "",
        f"- URLs: {total}",
        f"- Passed: {passed}",
        f"- Failed: {total - passed}",
        f"- Minimum text length: {minimum_text_length}",
        "",
        "| Result | Method | Error | HTTP | Chars | Time ms | Reason | URL |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for item in results:
        url = str(item["url"]).replace("|", "%7C")
        reason = str(item["reason"] or "").replace("|", "/")
        lines.append(
            "| {status} | {method} | {error_code} | {http_status} | "
            "{text_length} | {elapsed_ms} | {reason} | {url} |".format(
                status=item["status"],
                method=item["method"] or "",
                error_code=item["error_code"] or "",
                http_status=item["http_status"] or "",
                text_length=item["text_length"],
                elapsed_ms=item["elapsed_ms"],
                reason=reason,
                url=url,
            )
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a manual live URL benchmark through ArticleExtractor."
    )
    parser.add_argument(
        "--urls",
        type=Path,
        default=None,
        help=f"Text or JSON URL corpus. Defaults to {DEFAULT_URLS_PATH}.",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    from src.tools.article_extractor import MIN_EXTRACTION_TEXT_LENGTH, ArticleExtractor

    args = parse_args()
    urls_path = args.urls or DEFAULT_URLS_PATH
    urls = load_url_file(urls_path)
    if args.urls is None:
        urls = _dedupe_urls(urls + discover_local_urls())

    if args.limit > 0:
        urls = urls[: args.limit]
    if not urls:
        print(f"No benchmark URLs found in {urls_path}", file=sys.stderr)
        return 2

    extractor = ArticleExtractor()
    results = [
        benchmark_url(
            extractor,
            url,
            minimum_text_length=MIN_EXTRACTION_TEXT_LENGTH,
        )
        for url in urls
    ]
    payload = {
        "minimum_text_length": MIN_EXTRACTION_TEXT_LENGTH,
        "url_count": len(urls),
        "passed": sum(1 for item in results if item["passed"]),
        "failed": sum(1 for item in results if not item["passed"]),
        "results": results,
    }

    if args.format == "markdown":
        rendered = render_markdown(
            results,
            minimum_text_length=MIN_EXTRACTION_TEXT_LENGTH,
        )
    else:
        rendered = json.dumps(payload, indent=2, sort_keys=True)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
