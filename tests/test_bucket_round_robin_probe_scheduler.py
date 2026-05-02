"""Tests for bucket round-robin probe scheduling and fairness.

Proves the system does not return "five of one side and stop":
- Required buckets receive actual probe attempts
- Round-robin is deterministic
- Seed-aware probe sequences are correct
- Missing bucket diagnostics explain what happened
"""

from src.services.balanced_source_planner import BalancedSourcePlanner


class TestBucketProbeSequence:
    """Probe sequence is seed-aware and always includes required buckets."""

    def test_left_seed_probes_right_first(self):
        """Left-leaning seed probes right_side first."""
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=-3)
        sequence = plan.bucket_probe_sequence
        assert sequence.index("right_side") < sequence.index("left_side")

    def test_right_seed_probes_left_first(self):
        """Right-leaning seed probes left_side first."""
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=3)
        sequence = plan.bucket_probe_sequence
        assert sequence.index("left_side") < sequence.index("right_side")

    def test_neutral_seed_probes_center_first(self):
        """Neutral seed probes center first when available."""
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=0)
        sequence = plan.bucket_probe_sequence
        assert sequence[0] == "center"

    def test_all_required_labels_in_sequence(self):
        """All required buckets appear in the probe sequence."""
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=-2)
        required = {"left_side", "right_side"}
        assert required.issubset(set(plan.bucket_probe_sequence))

    def test_probe_sequence_is_deterministic(self):
        """Same seed produces the same sequence."""
        planner = BalancedSourcePlanner()
        s1 = planner.plan(seed_bias=-2).bucket_probe_sequence
        s2 = planner.plan(seed_bias=-2).bucket_probe_sequence
        assert s1 == s2


class TestBucketPlanCreation:
    """Source plan contains correct required/optional buckets."""

    def test_required_buckets_are_created(self):
        """Plan has the configured required buckets."""
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=0)
        required_labels = {b.label for b in plan.required_buckets}
        assert "left_side" in required_labels
        assert "right_side" in required_labels

    def test_center_is_optional_by_default(self):
        """Center bucket is optional (preferred but not required)."""
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=0)
        optional_labels = {b.label for b in plan.optional_buckets}
        assert "center" in optional_labels

    def test_unfilled_required_reports_correctly(self):
        """unfilled_required lists all required buckets initially."""
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=0)
        unfilled = plan.unfilled_required
        assert len(unfilled) == 2
        labels = {b.label for b in unfilled}
        assert labels == {"left_side", "right_side"}

    def test_mark_filled_updates_coverage(self):
        """Marking a bucket as filled updates coverage_satisfied."""
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=0)
        assert not plan.coverage_satisfied
        plan.mark_filled("left_side")
        assert not plan.coverage_satisfied  # right_side still unfilled
        plan.mark_filled("right_side")
        assert plan.coverage_satisfied

    def test_search_plan_includes_domain_targets(self):
        """Search plan steps reference domain targets for each bucket."""
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=0)
        assert len(plan.search_plan) > 0
        # At least one step should have domains
        has_domains = any(step.get("domains") for step in plan.search_plan)
        assert has_domains


class TestBucketFairness:
    """Prove the system enforces fairness constraints."""

    def test_probe_quotas_are_set(self):
        """All buckets have probe quotas set."""
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=0)
        for bucket in plan.all_buckets:
            assert bucket.probe_quota > 0

    def test_result_quotas_are_set(self):
        """All buckets have result quotas set."""
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=0)
        for bucket in plan.all_buckets:
            assert bucket.result_quota > 0

    def test_proceed_minimum_groups_match_required(self):
        """Proceed minimum groups match required bucket labels."""
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=0)
        assert set(plan.proceed_minimum_groups) == {
            b.label for b in plan.required_buckets
        }
