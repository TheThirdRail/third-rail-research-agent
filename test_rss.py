import sys
import os

sys.path.insert(0, os.path.abspath("."))
from src.tools.rss_aggregator import RSSAggregatorTool

tool = RSSAggregatorTool()
print("Searching for: senate, trump, cuba, blockade")
# Using comma separated keywords so that if any of them match it might show up, 
# but we want to see what is returned. The tool's search_feeds returns items where *any* keyword matches,
# but we want all of them. Let's write a custom filter to ensure ALL keywords are in the text.
aggregator = tool._run.__globals__['RSSAggregator']()
items = aggregator.fetch_all(max_age_hours=168)
keywords = ["senate", "trump", "cuba", "blockade"]

matches = []
for item in items:
    text = f"{item.title} {item.summary}".lower()
    if all(kw in text for kw in keywords):
        matches.append(item)

if not matches:
    print("No news items found matching all criteria.")
else:
    print(f"Found {len(matches)} news items matching ALL keywords:\n")
    for i, item in enumerate(matches[:20], 1):
        bias_label = tool._bias_to_label(item.bias)
        date_str = item.published.strftime("%Y-%m-%d") if item.published else "Unknown"
        print(f"{i}. [{bias_label}] {item.title}\n   Source: {item.source_name} | Date: {date_str}\n   URL: {item.url}\n")
