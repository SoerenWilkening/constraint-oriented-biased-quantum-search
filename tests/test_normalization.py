"""
Unit tests for cbqs.ml.normalization -- per-instance normalization and
renormalization of objective values.

Tests the InstanceNormalizer class which converts all problems to maximization
internally, tracks per-instance best/worst, normalizes via
(val - worst) / (best - worst), stores raw values, and renormalizes all
historical targets on each refit.
"""

import pytest

from cbqs.ml.normalization import InstanceNormalizer


# ===================================================================
# Normalization of Positive Objectives
# ===================================================================


class TestNormalizePositive:
    """Tests with positive objective values."""

    def test_normalize_positive_objectives(self):
        """Positive objectives normalized to [0, 1]."""
        norm = InstanceNormalizer()
        norm.register("inst1", 10.0)
        norm.register("inst1", 20.0)
        norm.register("inst1", 30.0)

        assert norm.normalize("inst1", 10.0) == pytest.approx(0.0)
        assert norm.normalize("inst1", 20.0) == pytest.approx(0.5)
        assert norm.normalize("inst1", 30.0) == pytest.approx(1.0)

    def test_normalize_to_zero_one_range(self):
        """All normalized values fall within [0, 1]."""
        norm = InstanceNormalizer()
        norm.register("inst1", 5.0)
        norm.register("inst1", 15.0)
        norm.register("inst1", 10.0)

        for raw in [5.0, 10.0, 15.0]:
            val = norm.normalize("inst1", raw)
            assert 0.0 <= val <= 1.0


# ===================================================================
# Normalization of Negative Objectives
# ===================================================================


class TestNormalizeNegative:
    """Tests with negative objective values."""

    def test_normalize_negative_objectives(self):
        """Negative objectives normalized correctly."""
        norm = InstanceNormalizer()
        norm.register("inst1", -30.0)
        norm.register("inst1", -10.0)

        # best=-10, worst=-30; (-30 - -30)/(-10 - -30) = 0/20 = 0
        assert norm.normalize("inst1", -30.0) == pytest.approx(0.0)
        # (-10 - -30)/(-10 - -30) = 20/20 = 1
        assert norm.normalize("inst1", -10.0) == pytest.approx(1.0)

    def test_normalize_mixed_sign_objectives(self):
        """Mixed positive and negative objectives normalized correctly."""
        norm = InstanceNormalizer()
        norm.register("inst1", -5.0)
        norm.register("inst1", 5.0)

        # best=5, worst=-5; (-5 - -5)/(5 - -5) = 0/10 = 0
        assert norm.normalize("inst1", -5.0) == pytest.approx(0.0)
        # (5 - -5)/(5 - -5) = 10/10 = 1
        assert norm.normalize("inst1", 5.0) == pytest.approx(1.0)
        # (0 - -5)/(5 - -5) = 5/10 = 0.5
        assert norm.normalize("inst1", 0.0) == pytest.approx(0.5)


# ===================================================================
# Minimization Conversion
# ===================================================================


class TestMinimizationConversion:
    """Tests that minimization is converted to maximization internally."""

    def test_minimization_converted_to_maximization(self):
        """Minimization objectives are negated internally for normalization.

        For minimization, lower raw values are better. After negation,
        higher internal values are better. The normalizer should assign
        a score of 1.0 to the best (lowest) raw value.
        """
        norm = InstanceNormalizer()
        # In minimization, 10.0 is better than 30.0
        norm.register("inst1", 10.0, is_minimization=True)
        norm.register("inst1", 30.0, is_minimization=True)

        # Best raw=10 (negated=-10 internally is worst negated? No --
        # negation flips: -10 < -30, so best_internal=-10, worst=-30.
        # Wait, maximization: best is highest. -10 > -30 so best=-10.
        # normalize(-10): (-10 - -30)/(-10 - -30) = 20/20 = 1.0
        # So raw=10 (negated=-10) normalizes to 1.0 (best).
        assert norm.normalize("inst1", 10.0) == pytest.approx(1.0)
        assert norm.normalize("inst1", 30.0) == pytest.approx(0.0)


# ===================================================================
# Best/Worst Tracking
# ===================================================================


class TestBestWorstTracking:
    """Tests that per-instance best/worst is tracked and updated."""

    def test_best_worst_tracking_updates(self):
        """Best and worst are updated as new values are registered."""
        norm = InstanceNormalizer()
        norm.register("inst1", 10.0)
        stats = norm.get_stats("inst1")
        assert stats["best"] == pytest.approx(10.0)
        assert stats["worst"] == pytest.approx(10.0)

        norm.register("inst1", 20.0)
        stats = norm.get_stats("inst1")
        assert stats["best"] == pytest.approx(20.0)
        assert stats["worst"] == pytest.approx(10.0)

        norm.register("inst1", 5.0)
        stats = norm.get_stats("inst1")
        assert stats["best"] == pytest.approx(20.0)
        assert stats["worst"] == pytest.approx(5.0)

    def test_best_eq_worst_returns_zero(self):
        """When best == worst, normalize returns 0.0."""
        norm = InstanceNormalizer()
        norm.register("inst1", 7.0)

        assert norm.normalize("inst1", 7.0) == pytest.approx(0.0)


# ===================================================================
# Renormalization
# ===================================================================


class TestRenormalization:
    """Tests for renormalize_all which recomputes all historical targets."""

    def test_renormalize_updates_historical_targets(self):
        """Renormalize recomputes all stored normalized values."""
        norm = InstanceNormalizer()
        norm.register("inst1", 10.0, config_idx=0)
        norm.register("inst1", 20.0, config_idx=1)

        results = norm.renormalize_all()
        # best=20, worst=10; (10-10)/(20-10)=0, (20-10)/(20-10)=1
        assert len(results) == 2
        by_cfg = {r[2]: r[1] for r in results}
        assert by_cfg[0] == pytest.approx(0.0)
        assert by_cfg[1] == pytest.approx(1.0)

    def test_renormalize_with_new_best(self):
        """After registering a new best, renormalize updates all."""
        norm = InstanceNormalizer()
        norm.register("inst1", 10.0, config_idx=0)
        norm.register("inst1", 20.0, config_idx=1)

        # Before new best
        results1 = norm.renormalize_all()
        by_cfg1 = {r[2]: r[1] for r in results1}
        assert by_cfg1[1] == pytest.approx(1.0)

        # Register new best
        norm.register("inst1", 30.0, config_idx=2)
        results2 = norm.renormalize_all()
        by_cfg2 = {r[2]: r[1] for r in results2}
        # Now best=30, worst=10; (10-10)/(30-10)=0, (20-10)/(30-10)=0.5,
        # (30-10)/(30-10)=1.0
        assert by_cfg2[0] == pytest.approx(0.0)
        assert by_cfg2[1] == pytest.approx(0.5)
        assert by_cfg2[2] == pytest.approx(1.0)

    def test_renormalize_with_new_worst(self):
        """After registering a new worst, renormalize updates all."""
        norm = InstanceNormalizer()
        norm.register("inst1", 10.0, config_idx=0)
        norm.register("inst1", 20.0, config_idx=1)

        # Register new worst
        norm.register("inst1", 0.0, config_idx=2)
        results = norm.renormalize_all()
        by_cfg = {r[2]: r[1] for r in results}
        # best=20, worst=0; (10-0)/(20-0)=0.5, (20-0)/(20-0)=1.0,
        # (0-0)/(20-0)=0.0
        assert by_cfg[0] == pytest.approx(0.5)
        assert by_cfg[1] == pytest.approx(1.0)
        assert by_cfg[2] == pytest.approx(0.0)
