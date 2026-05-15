# Failed RSS Feeds

Generated: 2026-05-15

These feeds were listed in `Deep-RSS-Research.md` but were not added to `config/source_registry.yaml` because they did not pass live RSS validation. A feed was treated as failed if it returned an HTTP error, timed out, could not be parsed as RSS/Atom, or parsed with zero entries.

The registry was left with only feeds that parsed successfully and returned entries.

| Line | Section | Source | Feed | Status | Reason | URL |
|---:|---|---|---|---|---|---|
| 75 | Lean Left | CNN | CNN Politics | 404 | Invalid XML: not well-formed | `http://rss.cnn.com/rss/edition_politics.rss` |
| 85 |  | Politico | Politico Picks | 403 | Invalid XML: not well-formed | `https://www.politico.com/rss/politicopicks.xml` |
| 94 |  | HuffPost | HuffPost All News | 200 | Parsed with zero entries | `https://www.huffpost.com/section/front-page/feed` |
| 114 |  | Common Dreams | Common Dreams Latest | 404 | Invalid XML: not well-formed | `https://www.commondreams.org/rss` |
| 135 | Local / Regional News | The News-Herald | The News-Herald RSS | 403 | HTTP forbidden | `https://www.news-herald.com/feed/` |
| 155 | Right | Daily Wire | Daily Wire All | 200 | Invalid XML: mismatched tag | `https://www.dailywire.com/feeds/rss.xml` |
| 194 | Libertarian | FEE | FEE Stories | 404 | Invalid XML: not well-formed | `https://fee.org/articles/rss` |
| 203 |  | Breaking Points | Breaking Points Podcast | 404 | HTTP not found | `https://feeds.simplecast.com/6MDKNyaU` |
| 205 |  | Glenn Greenwald | Glenn Greenwald Substack | 200 | Parsed with zero entries | `https://greenwald.substack.com/feed` |
| 207 |  | Joe Rogan | JRE Podcast | 404 | Invalid XML: mismatched tag | `https://podcasts.apple.com/us/podcast/the-joe-rogan-experience/id360084272` |
| 213 |  | Tim Pool | Timcast News | 404 | Invalid XML: not well-formed | `https://timcast.com/feed/` |
| 222 | Far Right / Conspiracy | Before It's News | BIN All News | 404 | Invalid XML: not well-formed | `https://beforeitsnews.com/feeds/all.xml` |
| 246 | Christian | Ancient Faith Ministries | Ancient Faith Podcasts | 404 | Invalid XML: mismatched tag | `https://www.ancientfaith.com/podcasts/rss` |
| 248 |  | Catholic News Agency | CNA Vatican Feed | 404 | Invalid XML: not well-formed | `https://www.catholicnewsagency.com/rss/vatican.xml` |
| 250 |  | Christianity Today | CT Magazine Feed | ConnectTimeout | Request timed out | `https://www.christianitytoday.com/ct/rss.xml` |
| 254 |  | First Things | First Things Articles | 404 | Invalid XML: syntax error | `https://firstthings.com/rss/all-articles` |
| 256 |  | National Catholic Register | NCR General News | 404 | Invalid XML: not well-formed | `https://www.ncregister.com/rss` |
| 271 | Hindu / India | Swarajya | Culture | 404 | Invalid XML: not well-formed | `https://swarajyamag.com/culture/rss` |
| 276 | Jewish | Chabad.org News | Chabad News Stories | 404 | Invalid XML: not well-formed | `https://www.chabad.org/tools/rss/default_cdo/rssid/1/jewish/News.htm` |
| 278 |  | Haaretz | News | 200 | Parsed with zero entries / invalid XML after redirect | `https://www.haaretz.com/misc/rss-feeds/1.4777193` |
| 282 |  | Tablet Magazine | Tablet Articles | 403 | Invalid XML: not well-formed | `https://www.tabletmag.com/feed` |
| 293 | Muslim / Middle East | MPAC | MPAC Updates | 404 | Invalid XML: syntax error | `https://www.mpac.org/feed/` |
| 297 |  | The Muslim Vibe | Podcast | 404 | Invalid XML: syntax error | `https://themuslimvibe.com/feed/podcast` |
| 302 | Pagan / New Age | Patheos | Pagan Channel | 404 | Invalid XML: not well-formed | `https://www.patheos.com/blogs/pagans/feed` |
| 306 |  | Witches & Pagans | Articles | ConnectTimeout | Request timed out | `https://witchesandpagans.com/feed.html` |
| 313 | Spiritual / Wellness | Elephant Journal | Daily | 500 | Server error | `https://www.elephantjournal.com/feed/` |
| 315 |  | Gaia | Blog Articles | 200 | Parsed with zero entries / invalid XML | `https://www.gaia.com/articles/feed` |
| 321 | Astrology / Metaphysics | Numerology.com | Numerology News | 404 | Invalid XML: not well-formed | `https://www.numerology.com/rss` |
| 330 | Paranormal / Fringe | Fate Mag | Feed | 404 | Invalid XML: not well-formed | `https://www.fatemag.com/feed` |
| 346 | Science / Technology / Health | Science | Politics | 410 | Gone | `https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science` |
| 350 |  | Scientific American | All | 404 | Invalid XML: syntax error | `https://www.scientificamerican.com/feed/all/` |
| 351 |  | Scientific American | Health | 404 | Invalid XML: syntax error | `https://www.scientificamerican.com/feed/health/` |
| 366 |  | MedlinePlus | All Health Info | 404 | Invalid XML: not well-formed | `https://medlineplus.gov/rss/all.xml` |
| 367 |  | MedlinePlus | Blood & Heart | 404 | Invalid XML: not well-formed | `https://medlineplus.gov/rss/bloodheartandcirculation.xml` |
| 369 |  | Mayo Clinic | All Health Topics | 200 | Parsed with zero entries / invalid XML after redirect | `https://www.mayoclinic.org/rss/all-health-information-topics` |
| 371 |  | WebMD | Health News | ConnectError | DNS lookup failed | `https://rssfeeds.webmd.com/rss/rss.aspx?RSSSource=RSS_PUBLIC` |
| 379 | Fitness / Lifestyle | Muscle & Fitness | Main RSS Feed | 200 | Parsed with zero entries / invalid XML | `https://www.muscleandfitness.com/feed/` |
