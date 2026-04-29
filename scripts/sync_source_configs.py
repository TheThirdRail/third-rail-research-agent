"""Validate source config drift from the canonical source registry."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def validate_configs(config_dir: Path = CONFIG_DIR) -> list[str]:
    registry = load_yaml(config_dir / "source_registry.yaml")
    bias_sources = load_yaml(config_dir / "bias_sources.yaml")
    rss_feeds = load_yaml(config_dir / "rss_feeds.yaml")

    errors: list[str] = []
    sources = registry.get("sources", [])
    registry_by_domain = {
        str(source.get("domain", "")).replace("www.", ""): source
        for source in sources
        if isinstance(source, dict)
    }
    registry_rss_urls = {
        str(rss_url)
        for source in sources
        if isinstance(source, dict)
        for rss_url in (source.get("rss_urls") or [])
    }
    bias_map = bias_sources.get("sources", {})
    feed_urls = {
        str(feed.get("url"))
        for feeds in rss_feeds.get("feeds", {}).values()
        for feed in feeds
        if isinstance(feed, dict)
    }

    for domain, bias_entry in bias_map.items():
        normalized_domain = str(domain).replace("www.", "")
        registry_entry = registry_by_domain.get(normalized_domain)
        if not registry_entry and normalized_domain == "bbc.co.uk":
            registry_entry = registry_by_domain.get("bbc.com")
        if not registry_entry:
            errors.append(
                f"{domain} exists in bias_sources.yaml but not source_registry.yaml"
            )
            continue
        if int(bias_entry.get("bias", 0)) != int(registry_entry.get("bias", 0)):
            errors.append(f"{domain} bias differs from source_registry.yaml")

    for rss_url in feed_urls:
        if rss_url not in registry_rss_urls:
            errors.append(
                f"{rss_url} exists in rss_feeds.yaml but not source_registry.yaml"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate configs and exit non-zero on drift.",
    )
    args = parser.parse_args()

    errors = validate_configs()
    if errors:
        for error in errors:
            print(error)
        return 1
    if args.check:
        print("source configs are synchronized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
