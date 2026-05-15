# Gemini Findings: Diagnosing Backend Retrieval Failures

## 1. Diagnosis of the 422 Error
The frequent `422 Unprocessable Entity` errors observed in the `research-agent-backend` logs are directly caused by extraction failures. In `src/api/routes/analyze.py`, when a `SourceExtractionError` is raised, it is explicitly caught and re-raised as an `HTTPException(status_code=422)`. This obscures the underlying stack trace in the standard access logs, but it confirms the analysis is failing during the source collection phase because the minimum required number of sources cannot be met.

## 2. Why Website Access is Failing
The application relies on `trafilatura`, `newspaper4k`, and `fundus` as its primary extraction tools. When tested against standard news sites (e.g., CNN), these tools fail to download the article. This is primarily because modern news publishers employ aggressive anti-bot protections (like Cloudflare, PerimeterX, and Datadome) that block standard python HTTP request libraries.

## 3. Why Browser Fallbacks Fail
The browser-based fallbacks (`Playwright` and `Selenium`) are also failing. When testing the extraction inside your docker container, the process times out during the `selenium` fallback step. Standard headless browsers are easily identified as bots by Cloudflare and are presented with an infinite CAPTCHA/Challenge page, leading to a timeout rather than returning the article content. Additionally, `fundus` may be missing from the environment entirely, further weakening the fallback chain.

## 4. Are RSS Feeds Being Attempted?
**Yes, RSS feeds are being attempted, but they still fail.**
The `RssRetrievalService` successfully pulls the RSS feeds to find alternative articles. However, RSS feeds typically only provide a title, a short summary, and a URL. To get the full story, the backend must still pass those RSS URLs into the `ArticleExtractor` to scrape the page. Since the underlying scraping methods are blocked by the publishers' anti-bot protections, the RSS URLs fail to extract just like the primary URL does. Ultimately, the system fails to gather the minimum number of retained sources required by `settings.retained_source_min` and aborts.

## 5. Recommended Alternative Website Reading Methods
Since the core issue is that standard scrapers and headless browsers are being blocked, you need a solution designed to bypass modern anti-bot protections and return LLM-ready text.

Here are the best alternatives with generous free tiers or reasonable pricing:

*   **Jina Reader API (`r.jina.ai`) - *Highly Recommended***
    *   **Cost**: Free tier is very generous (typically free for basic usage, very cheap beyond that).
    *   **How it works**: You simply prepend `https://r.jina.ai/` to your target URL. It handles all the browser rendering, Cloudflare bypassing, and proxy management on their end, returning clean, LLM-ready Markdown.
    *   **Integration**: Extremely easy to add to Python using a standard `httpx.get()` call.
*   **Firecrawl (`firecrawl.dev`)**
    *   **Cost**: 500 free credits/month.
    *   **How it works**: An API specifically built for LLM applications. It uses advanced residential proxies and browser rendering to bypass blocks and return structured Markdown.
*   **ZenRows (`zenrows.com`) or ScrapingBee (`scrapingbee.com`)**
    *   **Cost**: Free trials (1,000 API calls), then paid (starting around $49/mo).
    *   **How it works**: Professional web scraping APIs that guarantee bypassing of Cloudflare, Datadome, and captchas. They act as a proxy; you send a request to their API, and they return the raw HTML of the unblocked page.
*   **Browserless (`browserless.io`)**
    *   **Cost**: Very reasonable starter tier.
    *   **How it works**: Instead of running Playwright/Selenium inside your local Docker container (which gets blocked and is heavy), you connect your Playwright script to their cloud browsers, which are optimized to avoid detection.
