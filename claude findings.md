# Claude Findings: Backend Article Extraction Failures

## Summary

The backend is failing to extract articles from nearly all sources. The analysis run ends with `source_extraction_error` because it cannot retain the minimum required sources. The root causes are:

1. **Dead/broken RSS feed URLs** returning 404s before article extraction even begins
2. **Anti-bot protection** (Cloudflare, paywalls, CAPTCHAs) blocking all extraction methods
3. **Inadequate fallback chain** - all 5 extractors (trafilatura, newspaper4k, fundus, playwright, selenium) fail against modern bot protection

---

## Detailed Diagnosis

### Problem 1: RSS Feed URLs Are Dead (404s)

The following feeds in `config/rss_feeds.yaml` are returning **404 Not Found**:

| Feed | URL | Status |
|------|-----|--------|
| Reuters | `reutersagency.com/feed/?taxonomy=best-topics&post_type=best` | 404 |
| C-SPAN | `www.c-span.org/podcasts/rss` | 404 |
| Mises Institute | `mises.org/feed/wire` | 404 |
| Antiwar.com | `www.antiwar.com/feed/` | 404 |

These feeds are attempted during the **RSS phase** of the bucket round-robin search (`_search_plan_step` with `phase == "rss"`). The RSS phase IS being attempted (the code path at line 837-855 of `source_aggregator_service.py` runs when `analysis_rss_first_enabled` is `True`, which is the default). However, the feeds themselves are dead, so the RSS phase yields zero results for those domains.

**Is the system attempting RSS feeds?** Yes. The `RssRetrievalService.search_story()` and `RssRetrievalService.search()` methods iterate through feeds matching target domains. But feeds that 404 are caught silently in `RSSAggregator.fetch_feed()` (line 140 of `rss_aggregator.py`: `logger.warning(f"Failed to fetch {feed_url}: {e}")`), producing no items.

### Problem 2: Article Extraction Blocked by Anti-Bot Systems

The logs show the extraction fallback chain failing for major news sites:

- **NYTimes**: 403 via newspaper4k, then "Blocked by anti-bot challenge while using Selenium"
- **Politico**: "Website protected with Cloudflare" via newspaper4k, selenium also blocked
- **WSJ**: 403 via newspaper4k
- **The Hill**: "Blocked by anti-bot challenge while using Selenium"

The extraction order is: trafilatura -> newspaper4k -> fundus -> playwright -> selenium

All 5 methods fail because:
- **Trafilatura/newspaper4k**: Simple HTTP clients, trivially blocked by Cloudflare/bot detection
- **Fundus**: Uses httpx with publisher-specific headers, but still a plain HTTP client
- **Playwright**: Headless Chromium is detected by modern anti-bot (Cloudflare Turnstile, DataDome)
- **Selenium**: Same issue - headless Chrome fingerprinting is well-known to anti-bot systems

### Problem 3: Even Successfully Extracted Articles Get Rejected

The logs show articles from WashingtonPost, CNN, Guardian, NY Post, etc. were extracted successfully (via newspaper4k/trafilatura) but then **rejected by the relevance scorer** with `coverage_type_not_direct: mention`. This means:
- The extraction itself worked for some sites
- But the relevance scoring found the articles were only tangentially related (mentions, not direct coverage)
- Combined with extraction failures on more relevant URLs, the system can't fill coverage buckets

---

## Why All Fallbacks Fail

The core issue is that **all extraction methods are fundamentally the same approach** (fetch HTML, parse text) with slightly different HTTP clients. None of them can bypass:

1. **Cloudflare Bot Management** (Turnstile challenges, JS challenges)
2. **DataDome** (behavioral fingerprinting)
3. **Hard paywalls** (NYT, WSJ require authentication)
4. **Rate limiting** with IP-based blocking

The Selenium fallback adds headless Chrome, but modern anti-bot systems specifically detect:
- `navigator.webdriver` flag
- Missing browser plugins/extensions
- Headless rendering fingerprints
- Docker container IP ranges (cloud/datacenter IPs)

---

## Recommended Alternatives

### Option 1: ScrapingBee (Recommended)
- **What**: Managed scraping API with rotating residential proxies and JavaScript rendering
- **Free tier**: 1,000 API credits/month (1 credit = 1 request without JS, 5 credits with JS)
- **Pricing**: $49/month for 150,000 credits, $99/month for 1M credits
- **Why it fits**: Handles Cloudflare, rotates IPs, renders JS, returns clean HTML
- **Integration**: Simple HTTP API, replace the `httpx.get()` calls in extraction methods

### Option 2: Zyte API (formerly Scrapinghub/Splash)
- **What**: AI-powered web scraping with automatic anti-bot bypass
- **Free tier**: $5 free credits (approximately 500 requests with smart browser)
- **Pricing**: Pay-as-you-go, ~$0.01 per request for smart browser mode
- **Why it fits**: Specifically designed for news extraction, automatic article detection
- **Integration**: Python SDK available, returns structured article data

### Option 3: Bright Data Web Unlocker
- **What**: Enterprise proxy network with CAPTCHA solving and fingerprint rotation
- **Free tier**: $5 trial credit
- **Pricing**: $3/CPM (cost per 1000 requests)
- **Why it fits**: Highest success rate against Cloudflare/DataDome
- **Integration**: Proxy-based, minimal code changes (just change proxy settings)

### Option 4: Crawl4AI (Free/Open Source)
- **What**: Open-source async web crawler with LLM-friendly output
- **Free tier**: Completely free, self-hosted
- **Pricing**: Free
- **Why it fits**: Built-in anti-detection (stealth mode, browser fingerprint randomization), async, outputs clean markdown
- **Limitations**: Still uses headless browser so won't bypass all Cloudflare, but better than raw Playwright/Selenium due to stealth patches
- **Integration**: Python library, could replace the playwright/selenium fallback

### Option 5: Diffbot Article API
- **What**: AI-powered article extraction API (structured data, not just HTML scraping)
- **Free tier**: 10,000 free API calls (generous)
- **Pricing**: $299/month for 250,000 calls
- **Why it fits**: Purpose-built for news article extraction, handles dynamic content
- **Integration**: REST API returns structured JSON with title, author, text, images

### Option 6: newspaper4k + Proxy Rotation (Budget Option)
- **What**: Keep existing extractors but route through a rotating proxy service
- **Free tier**: Some free proxy lists exist but unreliable
- **Pricing**: ~$5-20/month for residential proxy pools (e.g., ProxyScrape, WebShare)
- **Why it fits**: Minimal code changes, addresses IP blocking specifically
- **Limitations**: Won't solve JS challenge/CAPTCHA issues, only IP-based blocks

---

## Recommended Strategy

**Short-term fix**: Replace dead RSS feed URLs and add a ScrapingBee or Crawl4AI fallback as a new extraction method after selenium fails.

**Optimal approach**:
1. Fix broken RSS URLs (Reuters, C-SPAN, Mises, Antiwar have changed their feed locations)
2. Add **ScrapingBee** as the final fallback extractor (generous free tier for development, reasonable pricing for production)
3. For paywalled sites (NYT, WSJ), rely on RSS feed metadata (title + summary) rather than full-text extraction - the system already has `RssFallbackService` for this

**Architecture note**: The system's RSS feed phase (`rss_retrieval_service.py`) is well-designed and DOES attempt feeds before expensive extraction. The problem is simply that many feed URLs are stale (404). Fixing those URLs would restore the cheapest, most reliable source of article metadata without any extraction needed.

---

## Dead Feed Replacements (Quick Wins)

| Source | Dead URL | Likely Replacement |
|--------|----------|-------------------|
| Reuters | `reutersagency.com/feed/...` | Reuters removed public RSS; use `news.google.com/rss/search?q=site:reuters.com` or their API |
| C-SPAN | `c-span.org/podcasts/rss` | Site restructured; check `c-span.org/about/rss/` |
| Mises Institute | `mises.org/feed/wire` | Try `mises.org/wire/feed` or `mises.org/rss.xml` |
| Antiwar.com | `antiwar.com/feed/` | Try `original.antiwar.com/feed/` or `news.antiwar.com/feed/` |

---

## Additional Issue: LLM Connection Error

The logs also show: `LLM bias inference failed: litellm.InternalServerError: OpenAIException - Connection error.`

This means the bias classifier LLM call (used to determine left/center/right placement) is failing due to a network connectivity issue from within the Docker container. This is likely a separate issue (missing API key env var, or the LLM endpoint is unreachable from the container network).
