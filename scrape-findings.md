# Scrape Findings

Date: 2026-05-15
Scope: Consolidated findings from `gemini findings.md`, `claude findings.md`, and `Agent-Context/Communications/Agent-Notes/codex-findings.md`.
Mode: Analysis/documentation only. No application source code was changed.

## Executive Summary

The backend is able to use SearxNG for search discovery. A live in-container probe to `http://host.docker.internal:8080/search` returned HTTP `200` and search results.

The backend is not using SearxNG as a full article scraper. SearxNG returns result metadata such as title, URL, and snippet. The app then separately tries to fetch and parse the publisher URL through the article extraction chain:

`trafilatura -> newspaper4k -> Fundus -> Playwright -> Selenium`

The current failures are a combination of:

1. RSS is attempted, but it returns zero accepted candidates in the observed failing run.
2. RSS diagnostics are partly misleading because structured RSS search ignores the lane domain subset and scans the whole bucket.
3. Some RSS feed URLs are stale, timing out, or returning 404.
4. Search discovery works, but returned publisher URLs are frequently blocked by anti-bot systems, paywalls, rate limits, or Cloudflare-like protections.
5. Some extracted articles are rejected by relevance scoring as indirect mentions instead of direct coverage.
6. The API maps `SourceExtractionError` to HTTP `422`, so the visible UI/API error is a symptom of retrieval failure rather than the root cause.

## Source Files Compiled

- `gemini findings.md`
- `claude findings.md`
- `Agent-Context/Communications/Agent-Notes/codex-findings.md`, specifically the `2026-05-15 Docker Backend Retrieval / RSS Investigation` section

## What The System Currently Does

1. The analysis route receives a story URL or story description.
2. If a URL is present, the backend first tries direct extraction from that URL.
3. The backend builds a balanced source plan across ideological buckets.
4. RSS lanes are attempted first when `analysis_rss_first_enabled=True`.
5. If RSS does not produce enough usable candidates, the backend uses SearxNG site searches and open-web searches to discover more URLs.
6. Every discovered URL still needs article extraction from the publisher site.
7. Extracted candidates are relevance-scored and may be rejected if they only mention the topic instead of directly covering it.
8. If required source buckets cannot be retained, the backend raises `SourceExtractionError`, which becomes HTTP `422`.

## SearxNG Finding

SearxNG is working as a search backend in the live Docker setup. It is reachable from the backend container at:

`http://host.docker.internal:8080`

Codex verified that a direct in-container SearxNG query returned HTTP `200` and `18` results for a NYT site query.

SearxNG is not currently a full article extraction layer. The code uses it for result discovery, then hands each result URL to the article extractor. Changing the codebase could make the app use SearxNG snippets as degraded fallback evidence, but SearxNG snippets are too short and inconsistent to replace full article extraction.

Practical recommendation:

- Keep SearxNG as the discovery layer.
- Add a snippet-based fallback only as weak evidence, clearly labeled.
- Do not try to turn SearxNG itself into the main article scraper.

## RSS Findings

All three findings agree that RSS is involved. The most precise conclusion is:

RSS is attempted, but it produced zero accepted RSS candidates in the observed failing run.

Codex found that the latest failed Docker run recorded RSS bucket-lane attempts in `candidate_census_json`, but persisted `0` retrieval candidates with stage `rss`. That means RSS ran before preflight but returned no accepted URLs.

The important code-level issue is in `SourceAggregatorService._search_plan_step()`. For structured stories, it calls:

`self._rss_retriever.search_story(story_packet, bucket_spec, max_results=8)`

That call ignores `step["domains"]`. The diagnostic lane may say it is trying NYT/WaPo/CNN, but the actual RSS search scans the entire bucket. Because `analysis_rss_max_feeds_per_bucket` defaults to `3`, registry order can consume the feed budget before the intended domains are fetched.

Additional RSS issues:

- Reuters Agency RSS returned `404`.
- Mises RSS returned `404`.
- Antiwar RSS returned `404`.
- Washington Post RSS timed out in live testing.
- Claude reported C-SPAN as dead; Codex did not re-confirm that exact status in the latest live pass, so this should be rechecked before editing source registry data.
- Some major domains in the target buckets have no configured RSS feed.
- Short manually-entered story descriptions can parse poorly, e.g. `actors=["Trump China"]` and `action_verbs=[]`, which makes RSS story scoring reject topical items for low event-action overlap.

RSS recommendation:

1. Pass lane-specific domains into structured RSS search.
2. Persist actual feed attempts, feed HTTP status, item count, accepted count, and rejection reasons.
3. Repair or remove stale feed URLs.
4. Increase the per-bucket feed cap only after feed targeting is fixed.
5. Improve short-description story parsing so RSS scoring has real actors and action terms.

### 2026-05-15 RSS Link Audit

Codex rechecked every configured RSS URL in `config/source_registry.yaml`, including topic feeds, with a live HTTP GET and `feedparser` parse. The first pass checked 71 feed URLs: 59 parsed successfully and 12 were broken or suspect. After repairing the stale set, the follow-up pass checked 65 configured feed URLs and all 65 returned at least one parsed feed entry.

The operator then supplied additional Reuters, AP, Bloomberg, Newsmax, USA Today, and Alex Jones Live feeds. Codex validated those feeds, corrected the zero-item Reuters Google News query to `site:reuters.com+when:24h`, corrected the AP Flipboard politics URL from `.rss2` to `.rss`, used `http://www.newsmax.com/rss/...` because those parse and redirect while direct `https://...` attempts timed out, and used `https://www.alexjoneslive.com/feed/` because the bare-domain feed returned `403`. After those updates, the registry audit checked 98 configured feeds and all 98 parsed successfully.

Codex then checked the remaining `Deep-RSS-Research.md` feed backlog against the registry. Of 111 deep-list URLs not already in `source_registry.yaml`, 74 parsed as feeds with entries and 37 failed or returned zero entries. The verified additions were promoted to `source_registry.yaml`, while failed/suspect feeds stayed out. The expanded registry audit checked 164 configured feeds and all 164 parsed successfully.

Applied corrections:

| Outlet | Broken URL / result | Replacement or action |
| --- | --- | --- |
| Reuters | `https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best` returned `404`; the supplied `allinurl:reuters.com` Google News query parsed zero items. | Added ReutersBest feeds, a working Google News `site:reuters.com+when:24h` feed, and Thomson Reuters investor feeds. |
| Associated Press | `https://rsshub.app/apnews/topics/apf-topnews` returned `403`; AP's advertised `https://apnews.com/index.rss` returned `401 Invalid client credentials`. | Added working FeedX, Noleron, and Flipboard AP mirrors. |
| C-SPAN | `https://www.c-span.org/podcasts/rss` returned `404`. | Replaced with `https://feeds.megaphone.fm/cspanwashingtontoday`. |
| MSNBC | `https://www.msnbc.com/feeds/latest` redirected to a non-feed article page. | Replaced with `https://www.msnbc.com/feed`. |
| Mises Institute | `https://mises.org/feed/wire` returned `404`. | Replaced with `https://mises.org/feed`. |
| Antiwar.com | `https://www.antiwar.com/feed/` returned `404`. | Replaced with `https://news.antiwar.com/feed/`. |
| Coast to Coast AM | `https://rss.premiereradio.net/podcast/coast.xml` returned `401`. | Replaced with `https://www.coasttocoastam.com/articles.rss`. |
| Forbes | `https://www.forbes.com/investing/feed/` returned `404`; operator could not find a replacement. | Removed Forbes RSS; keep Forbes available through search discovery. |
| USA Today | `https://rssfeeds.usatoday.com/usatoday-newstopstories` redirected to the homepage and parsed zero entries. | Replaced with a working Google News feed. |
| Newsmax | Direct `https://www.newsmax.com/rss/...` attempts timed out. | Added working `http://www.newsmax.com/rss/...` feed URLs, which parse and redirect to HTTPS. |
| Above Top Secret | `https://www.abovetopsecret.com/rss/news.xml` timed out or returned `522`. | Removed RSS URL. |
| Christianity Today | `http://feeds.christianitytoday.com/christianitytoday/ctmag` timed out. | Replaced with `https://www.christianitytoday.com/feed/`. |
| Washington Post | `https://feeds.washingtonpost.com/rss/politics` rechecked successfully with 11 parsed entries. | No config change. |
| Alex Jones Live | `https://alexjoneslive.com/feed` returned `403`. | Replaced prior feed with `https://www.alexjoneslive.com/feed/`. |

## Article Extraction Findings

The current fallback chain is:

`trafilatura -> newspaper4k -> Fundus -> Playwright -> Selenium`

The live Docker container has these libraries installed. Gemini suspected Fundus might be missing, but Codex verified `fundus=True` in the active container, and the live extractor version was `2026-05-14-fundus-fallback-v1`.

Observed extraction failures:

- The Hill: `newspaper4k` hit HTTP `429`; final row showed Selenium `blocked_challenge`.
- NYT: `newspaper4k` hit HTTP `403`; final row showed Selenium `blocked_challenge`.
- Politico: `newspaper4k` reported Cloudflare protection; Selenium also failed.
- WSJ: `newspaper4k` hit HTTP `403`.
- A CNN URL timed out in Selenium in another observed run.

The stored candidate record only keeps the final extractor result. This makes failures look like "Selenium failed" even when earlier extractors also failed. The app needs full fallback-chain diagnostics to make these runs debuggable.

Article extraction recommendation:

1. Persist every extractor attempt per URL, not just the final method.
2. Classify failures by cause: HTTP status, challenge page, paywall, timeout, empty content, parser failure.
3. Add an optional external extraction provider after local extractors fail.
4. Treat hard-paywall sources separately; do not pretend a scraping provider can legally or reliably extract subscriber-only content.

## Relevance Scoring Finding

Not every failure is a scrape failure. Several URLs were successfully extracted, but rejected as:

`coverage_type_not_direct: mention`

This affected candidates from sources such as Washington Post, CNN, Guardian, NY Post, and Washington Examiner in the latest failed run.

That means the system sometimes finds and reads articles, but they are only tangentially related to the requested story. This is a search/query precision issue, not a scraper issue.

Recommendation:

- Improve query generation for short story descriptions.
- Preserve search snippets and RSS metadata as context for why a candidate was discovered.
- Add diagnostics separating extraction failures from relevance failures in the UI/API response.

## HTTP 422 Finding

Gemini correctly identified that the visible `422 Unprocessable Entity` response is caused by source collection failure. The backend catches `SourceExtractionError` and maps it to HTTP `422`.

This status code is technically misleading for this failure mode. The request shape may be valid; the backend just could not gather enough acceptable sources.

Recommendation:

- Keep the detailed internal error, but return a clearer application error body.
- Consider using a more specific retrieval failure status or error code, e.g. `source_extraction_error`, while preserving compatibility for existing UI handling.

## External Extraction Options

### Jina Reader API

Best as a cheap first external fallback.

- Simple integration: prepend `https://r.jina.ai/` to the target URL.
- Official docs list unauthenticated and free-key rate limits.
- Codex spot-check found it returned useful Politico content.
- It returned block-like or unavailable responses for NYT and The Hill in spot checks, so it is not complete.

### Tavily Extract

Good low-cost extraction fallback if an API key is acceptable.

- Current docs list a free monthly credit allowance.
- Basic extract is cheap per group of successful URL extractions.
- Failed extractions are not charged according to the checked docs.

### Firecrawl

Good general scrape-to-markdown provider.

- Current pricing lists a free monthly credit allowance.
- Strong fit for markdown extraction and batch workflows.
- Not guaranteed to solve every anti-bot/paywall case.

### Browserless

Best fit for hard JavaScript and bot-detection cases.

- More appropriate as an expensive final fallback than as the default extractor.
- Browserless `/scrape` and `/unblock` are closer to the observed challenge-page failure mode.

### Crawl4AI

Best local/open-source candidate.

- Free and self-hosted.
- Better crawler controls and markdown output than a hand-rolled Playwright path.
- Still uses browser automation and will not reliably bypass serious anti-bot systems by itself.

### ScrapingBee / ZenRows / Zyte / Bright Data / Diffbot

Claude and Gemini recommended several managed scraping APIs. They are plausible options for anti-bot bypass, but their exact current free tiers and pricing should be rechecked from official docs before implementation.

The most relevant distinction:

- Proxy/unblocker services help with Cloudflare/DataDome/rate limiting.
- Article APIs help with structured extraction once access succeeds.
- Neither category should be treated as a paywall bypass strategy.

## Recommended Fix Plan

### Phase 1: Make RSS Truthful And Useful

- Fix structured RSS search so it honors lane domains.
- Persist RSS feed attempt diagnostics.
- Repair stale RSS URLs.
- Re-run the same failed story and confirm RSS candidates are either accepted or rejected with clear reasons.

### Phase 2: Improve Retrieval Error Visibility

- Persist full extractor attempt chains.
- Surface counts for RSS no-results, extraction failures, and relevance rejections separately.
- Make the API response explain why coverage buckets were missing.

### Phase 3: Improve Query Precision

- Improve short-description story parsing.
- Avoid parsed actors like `Trump China` when the intended actors are `Trump` and `China`.
- Ensure query expansion produces direct-coverage searches, not broad topic mentions.

### Phase 4: Add Optional External Extraction

- Start with Jina Reader or Tavily Extract as a low-cost external fallback.
- Add Firecrawl if markdown/batch extraction becomes more valuable.
- Keep Browserless or another unblocker as a final hard-case fallback.
- Store provider name, status, and cost/credit use in diagnostics.

### Phase 5: Consider Snippet-Based Degraded Evidence

- Use SearxNG snippets only when full extraction fails.
- Label snippet-only sources as partial evidence.
- Do not count snippet-only sources the same as full-text article evidence unless the report logic is explicitly designed for that weaker input.

## Consolidated Bottom Line

The backend can search with SearxNG. It cannot currently scrape full article bodies with SearxNG, and SearxNG should not be treated as a replacement for article extraction.

The highest-leverage fixes are not to add a paid scraper first. First, make RSS lane targeting accurate, repair feed URLs, and persist better diagnostics. Then add an external extraction provider as an optional fallback for publisher blocks.
