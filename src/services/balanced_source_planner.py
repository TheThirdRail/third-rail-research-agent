"""Balanced source planner service.

Deterministic bucket-based planning that ensures cross-spectrum
coverage before source gathering begins.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.services.source_registry import (
    LEFT_SIDE,
    RIGHT_SIDE,
    RegistryEntry,
    get_source_registry,
)

logger = logging.getLogger(__name__)


@dataclass
class BucketSpec:
    """Specification for a single bias bucket to fill."""

    label: str
    bias_values: set[int]
    required: bool
    domain_targets: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    filled: bool = False


@dataclass
class SourcePlan:
    """Output from the balanced source planner."""

    required_buckets: list[BucketSpec]
    optional_buckets: list[BucketSpec]
    domain_targets_per_bucket: dict[str, list[str]]
    search_plan: list[dict[str, object]]
    seed_bias: int | None
    seed_domain: str | None

    @property
    def all_buckets(self) -> list[BucketSpec]:
        return self.required_buckets + self.optional_buckets

    @property
    def required_labels(self) -> list[str]:
        return [b.label for b in self.required_buckets]

    def mark_filled(self, label: str) -> None:
        """Mark a bucket as filled."""
        for bucket in self.all_buckets:
            if bucket.label == label:
                bucket.filled = True
                return

    @property
    def unfilled_required(self) -> list[BucketSpec]:
        return [b for b in self.required_buckets if not b.filled]

    @property
    def coverage_satisfied(self) -> bool:
        return all(b.filled for b in self.required_buckets)


class BalancedSourcePlanner:
    """Deterministic source planning with seed-aware bucket rules.

    Decides which bias buckets must be filled and which curated
    outlets to target for each bucket, before any searching begins.
    """

    def __init__(self) -> None:
        self._registry = get_source_registry()

    def plan(
        self,
        seed_bias: int | None = None,
        seed_domain: str | None = None,
        include_fringe: bool = False,
        include_libertarian: bool = True,
    ) -> SourcePlan:
        """Generate a balanced source plan based on seed context.

        Args:
            seed_bias: Bias score of the seed article (-4 to +4), if known.
            seed_domain: Domain of the seed article, if known.
            include_fringe: Include a fringe/conspiracy bucket.
            include_libertarian: Include a libertarian/independent bucket.

        Returns:
            SourcePlan with required and optional buckets.
        """
        required: list[BucketSpec] = []
        optional: list[BucketSpec] = []

        if seed_bias is not None and seed_bias <= -3:
            # Far-left seed → need center + right
            required.append(self._make_bucket("center", {-1, 0, 1}, required=True))
            required.append(self._make_bucket("right_side", {2, 3, 4}, required=True))
            optional.append(self._make_bucket("left_side", {-4, -3, -2}, required=False))

        elif seed_bias is not None and seed_bias >= 3:
            # Far-right seed → need center + left
            required.append(self._make_bucket("center", {-1, 0, 1}, required=True))
            required.append(self._make_bucket("left_side", {-4, -3, -2}, required=True))
            optional.append(self._make_bucket("right_side", {2, 3, 4}, required=False))

        else:
            # Center, unknown, or moderate seed → need all three
            required.append(self._make_bucket("left_side", {-4, -3, -2}, required=True))
            required.append(self._make_bucket("center", {-1, 0, 1}, required=True))
            required.append(self._make_bucket("right_side", {2, 3, 4}, required=True))

        if include_libertarian:
            optional.append(self._make_bucket_by_category("libertarian", required=False))

        if include_fringe:
            optional.append(self._make_bucket_by_category("fringe_conspiracy", required=False))

        # Build domain targets per bucket
        domain_targets: dict[str, list[str]] = {}
        for bucket in required + optional:
            domain_targets[bucket.label] = bucket.domain_targets

        # Build search plan
        search_plan = self._build_search_plan(required, optional, seed_domain)

        plan = SourcePlan(
            required_buckets=required,
            optional_buckets=optional,
            domain_targets_per_bucket=domain_targets,
            search_plan=search_plan,
            seed_bias=seed_bias,
            seed_domain=seed_domain,
        )

        logger.info(
            "Source plan: required=%s optional=%s seed_bias=%s",
            [b.label for b in required],
            [b.label for b in optional],
            seed_bias,
        )

        return plan

    def classify_bias_to_bucket(self, bias: int) -> str:
        """Map a bias score to its bucket label."""
        if bias in LEFT_SIDE:
            return "left_side"
        if bias in RIGHT_SIDE:
            return "right_side"
        return "center"

    def _make_bucket(
        self, label: str, bias_values: set[int], *, required: bool
    ) -> BucketSpec:
        """Create a bias-based bucket with curated domain targets."""
        domains: list[str] = []
        for bias_val in sorted(bias_values):
            for entry in self._registry.get_by_bias(bias_val):
                if entry.allow_in_analysis:
                    domains.append(entry.domain)
        return BucketSpec(
            label=label,
            bias_values=bias_values,
            required=required,
            domain_targets=domains,
        )

    def _make_bucket_by_category(
        self, category: str, *, required: bool
    ) -> BucketSpec:
        """Create a category-based bucket."""
        entries = self._registry.get_by_category(category)
        domains = [e.domain for e in entries if e.allow_in_analysis]
        return BucketSpec(
            label=category,
            bias_values=set(),
            required=required,
            domain_targets=domains,
        )

    def _build_search_plan(
        self,
        required: list[BucketSpec],
        optional: list[BucketSpec],
        seed_domain: str | None,
    ) -> list[dict[str, object]]:
        """Build ordered search plan: RSS first, curated domain, open web."""
        plan: list[dict[str, object]] = []

        for bucket in required:
            # Skip seed domain in targets
            targets = [
                d for d in bucket.domain_targets if d != seed_domain
            ]
            if targets:
                plan.append(
                    {
                        "phase": "rss_curated",
                        "bucket": bucket.label,
                        "domains": targets[:5],
                        "required": True,
                    }
                )
                plan.append(
                    {
                        "phase": "site_search",
                        "bucket": bucket.label,
                        "domains": targets[:5],
                        "required": True,
                    }
                )
            plan.append(
                {
                    "phase": "open_web",
                    "bucket": bucket.label,
                    "domains": [],
                    "required": True,
                }
            )

        for bucket in optional:
            targets = [
                d for d in bucket.domain_targets if d != seed_domain
            ]
            if targets:
                plan.append(
                    {
                        "phase": "rss_curated",
                        "bucket": bucket.label,
                        "domains": targets[:3],
                        "required": False,
                    }
                )

        return plan
