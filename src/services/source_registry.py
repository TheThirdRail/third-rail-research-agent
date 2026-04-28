"""Canonical source registry service.

Loads config/source_registry.yaml and provides indexed lookups
for bias classification, RSS feeds, bucket planning, and search.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from src.core.config import settings

logger = logging.getLogger(__name__)

# Bias bucket group boundaries
LEFT_SIDE = {-4, -3, -2}
CENTER_SIDE = {-1, 0, 1}
RIGHT_SIDE = {2, 3, 4}


@dataclass(frozen=True)
class RegistryEntry:
    """A single outlet in the source registry."""

    name: str
    domain: str
    homepage_url: str
    bias: int
    bias_label: str
    category: str
    factual_rating: str
    rss_urls: tuple[str, ...]
    search_aliases: tuple[str, ...]
    syndication_group: str | None
    allow_in_analysis: bool
    notes: str


@dataclass
class BucketTargets:
    """Domain target lists for balanced source planning."""

    required: dict[str, list[str]] = field(default_factory=dict)
    optional: dict[str, list[str]] = field(default_factory=dict)


class SourceRegistry:
    """Loads and indexes the canonical source registry.

    Provides fast lookups by domain, bias bucket, category, and
    domain-list generation for balanced source planning.
    """

    def __init__(self, registry_path: Path | None = None) -> None:
        self._path = registry_path or (settings.config_dir / "source_registry.yaml")
        self._entries: list[RegistryEntry] = []
        self._by_domain: dict[str, RegistryEntry] = {}
        self._by_bias: dict[int, list[RegistryEntry]] = {}
        self._by_category: dict[str, list[RegistryEntry]] = {}
        self._bias_labels: dict[int, str] = {}
        self._factual_ratings: dict[str, int] = {}
        self._load()

    # ── public API ──────────────────────────────────────────────

    def lookup_domain(self, domain: str) -> RegistryEntry | None:
        """Lookup an outlet by normalized domain."""
        return self._by_domain.get(self._normalize(domain))

    def get_by_bias(self, bias: int) -> list[RegistryEntry]:
        """Get all outlets with a specific bias score."""
        return list(self._by_bias.get(bias, []))

    def get_by_category(self, category: str) -> list[RegistryEntry]:
        """Get all outlets in a specific category."""
        return list(self._by_category.get(category.lower(), []))

    def get_by_bucket_group(
        self, group: str
    ) -> list[RegistryEntry]:
        """Get outlets for a bucket group: 'left_side', 'center_side', 'right_side'."""
        bias_set = {"left_side": LEFT_SIDE, "center_side": CENTER_SIDE, "right_side": RIGHT_SIDE}.get(group, set())
        results: list[RegistryEntry] = []
        for bias_val in bias_set:
            results.extend(self._by_bias.get(bias_val, []))
        return results

    def get_analysis_outlets(self) -> list[RegistryEntry]:
        """Get all outlets allowed in analysis."""
        return [e for e in self._entries if e.allow_in_analysis]

    def get_domains_for_bias_range(
        self, min_bias: int, max_bias: int
    ) -> list[str]:
        """Get domains for outlets within a bias range (inclusive)."""
        return [
            e.domain
            for e in self._entries
            if min_bias <= e.bias <= max_bias and e.allow_in_analysis
        ]

    def get_rss_feeds_for_category(
        self, category: str
    ) -> list[dict[str, object]]:
        """Get RSS feed configs for a category, matching rss_feeds.yaml format."""
        feeds: list[dict[str, object]] = []
        for entry in self.get_by_category(category):
            for rss_url in entry.rss_urls:
                feeds.append(
                    {
                        "name": entry.name,
                        "url": rss_url,
                        "bias": entry.bias,
                        "category": entry.category,
                    }
                )
        return feeds

    def get_all_rss_feeds(self) -> dict[str, list[dict[str, object]]]:
        """Get all RSS feeds grouped by bias category label.

        Returns a dict matching the old rss_feeds.yaml structure for
        backward compatibility with RSSAggregator._load_feeds().
        """
        grouped: dict[str, list[dict[str, object]]] = {}
        bias_category_map = {
            0: "center",
            -1: "slight_left",
            -2: "lean_left",
            -3: "left",
            -4: "far_left",
            1: "slight_right",
            2: "lean_right",
            3: "right",
            4: "far_right",
        }

        for entry in self._entries:
            if not entry.rss_urls:
                continue
            # Use category if special, otherwise use bias-derived category
            if entry.category in (
                "libertarian",
                "independent",
                "fringe_conspiracy",
                "religion_spiritual",
                "supernatural",
            ):
                cat_key = entry.category
            else:
                cat_key = bias_category_map.get(entry.bias, "center")

            if cat_key not in grouped:
                grouped[cat_key] = []

            for rss_url in entry.rss_urls:
                grouped[cat_key].append(
                    {
                        "name": entry.name,
                        "url": rss_url,
                        "bias": entry.bias,
                        "category": entry.category,
                    }
                )

        return grouped

    def get_bias_label(self, bias: int) -> str:
        """Get human-readable label for a bias score."""
        return self._bias_labels.get(bias, "Unknown")

    def get_factual_rank(self, rating: str) -> int:
        """Get numeric rank for a factual rating string."""
        return self._factual_ratings.get(rating, 0)

    def is_known_domain(self, domain: str) -> bool:
        """Check if a domain exists in the registry."""
        return self._normalize(domain) in self._by_domain

    @property
    def entries(self) -> list[RegistryEntry]:
        """All registry entries."""
        return list(self._entries)

    # ── internals ──────────────────────────────────────────────

    @staticmethod
    def _normalize(domain: str) -> str:
        """Normalize domain for lookup (strip www., lowercase)."""
        d = domain.lower().strip()
        if d.startswith("www."):
            d = d[4:]
        return d

    def _load(self) -> None:
        """Load and index the registry YAML."""
        if not self._path.exists():
            logger.warning("Source registry not found at %s", self._path)
            return

        with open(self._path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        self._bias_labels = {int(k): v for k, v in data.get("bias_labels", {}).items()}
        self._factual_ratings = data.get("factual_ratings", {})

        for raw in data.get("sources", []):
            entry = RegistryEntry(
                name=raw["name"],
                domain=self._normalize(raw["domain"]),
                homepage_url=raw.get("homepage_url", ""),
                bias=int(raw.get("bias", 0)),
                bias_label=raw.get("bias_label", "Unknown"),
                category=raw.get("category", "mainstream"),
                factual_rating=raw.get("factual_rating", "mixed"),
                rss_urls=tuple(raw.get("rss_urls") or []),
                search_aliases=tuple(raw.get("search_aliases") or []),
                syndication_group=raw.get("syndication_group"),
                allow_in_analysis=raw.get("allow_in_analysis", True),
                notes=raw.get("notes", ""),
            )
            self._entries.append(entry)
            self._by_domain[entry.domain] = entry
            # Also index without www and with alternative TLDs
            if entry.domain == "bbc.com":
                self._by_domain["bbc.co.uk"] = entry

            self._by_bias.setdefault(entry.bias, []).append(entry)
            self._by_category.setdefault(entry.category, []).append(entry)

        logger.info(
            "Loaded %d outlets from source registry (%s)",
            len(self._entries),
            self._path.name,
        )


@lru_cache
def get_source_registry() -> SourceRegistry:
    """Get cached singleton source registry instance."""
    return SourceRegistry()
