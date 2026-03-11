"""Tests for M7: Model.pyx phase-specific parameters.

Validates that phase-specific parameter definitions from ml.phase_params
are integrated into Model._PARAM_DEFS, that set_param/get_param works
for all 15 phase-specific params, and that _resolve_phase_params()
correctly resolves with fallback logic.
"""
import numpy as np
import pytest

pytest.importorskip("cbqs")

from copy import copy
from cbqs.Model import Model, _PARAM_DEFS, _KNOWN_PARAMS
from cbqs.Constants import MAXIMIZE
from cbqs.result import OptimizeResult
from cbqs.ml.phase_params import PHASES, PHASE_PARAM_SUFFIXES, DEFAULTS


def _make_small_model():
    """Create a small valid model for testing."""
    m = Model()
    x = m.add_variables(5)
    m.set_objective(x[0] + 2 * x[1] + 3 * x[2] + x[3] + x[4], sense=MAXIMIZE)
    m.add_constraint(x[0] + x[1] + x[2] + x[3] + x[4] <= 3)
    m.close()
    return m


# =============================================================================
# 1. Phase param defs are present in _PARAM_DEFS
# =============================================================================


class TestPhaseParamDefsPresent:
    """Verify all 15 phase-specific params are in _PARAM_DEFS."""

    def test_all_15_phase_params_in_param_defs(self):
        """All 15 phase-specific param keys exist in _PARAM_DEFS."""
        for phase in PHASES:
            for suffix in PHASE_PARAM_SUFFIXES:
                key = f"{phase}_{suffix}"
                assert key in _PARAM_DEFS, f"Missing {key} in _PARAM_DEFS"

    def test_all_15_phase_params_in_known_params(self):
        """All 15 phase-specific param keys exist in _KNOWN_PARAMS."""
        for phase in PHASES:
            for suffix in PHASE_PARAM_SUFFIXES:
                key = f"{phase}_{suffix}"
                assert key in _KNOWN_PARAMS, f"Missing {key} in _KNOWN_PARAMS"

    def test_phase_param_count(self):
        """Exactly 15 phase-specific params are added (3 phases x 5 suffixes)."""
        count = sum(
            1 for key in _PARAM_DEFS
            if any(key.startswith(f"{p}_") for p in PHASES)
        )
        assert count == 15


# =============================================================================
# 2. Setting phase-specific params
# =============================================================================


class TestSetPhaseParams:
    """Verify set_param works for phase-specific parameters."""

    def test_set_sat_branching_weights(self):
        """set_param('sat_branching_weights', array) stores the value."""
        m = _make_small_model()
        weights = [1.0, 2.0, 3.0, 4.0, 5.0]
        m.set_param('sat_branching_weights', weights)
        assert m.get_param('sat_branching_weights') == weights

    def test_set_opt_sat_branching_bias(self):
        """set_param('opt_sat_branching_bias', 3.0) stores the float."""
        m = Model()
        m.set_param('opt_sat_branching_bias', 3.0)
        assert m.get_param('opt_sat_branching_bias') == 3.0

    def test_set_opt_variable_priorities(self):
        """set_param('opt_variable_priorities', array) stores the value."""
        m = _make_small_model()
        priorities = [5.0, 4.0, 3.0, 2.0, 1.0]
        m.set_param('opt_variable_priorities', priorities)
        assert m.get_param('opt_variable_priorities') == priorities

    def test_set_phase_param_validates_bias(self):
        """set_param('sat_branching_bias', -2) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="branching_bias must be"):
            m.set_param('sat_branching_bias', -2.0)

    def test_set_phase_param_validates_factor(self):
        """set_param('opt_branching_factor', -1) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="branching_factor must be"):
            m.set_param('opt_branching_factor', -1.0)

    def test_set_phase_param_none_resets(self):
        """set_param('sat_branching_bias', None) resets to default."""
        m = Model()
        m.set_param('sat_branching_bias', 10.0)
        m.set_param('sat_branching_bias', None)
        assert m.get_param('sat_branching_bias') == DEFAULTS['branching_bias']

    def test_set_sat_branching_factor(self):
        """set_param('sat_branching_factor', 2.5) stores the float."""
        m = Model()
        m.set_param('sat_branching_factor', 2.5)
        assert m.get_param('sat_branching_factor') == 2.5

    def test_set_opt_bias_factor(self):
        """set_param('opt_bias_factor', 0.5) stores the float."""
        m = Model()
        m.set_param('opt_bias_factor', 0.5)
        assert m.get_param('opt_bias_factor') == 0.5

    def test_set_phase_weights_validates_negative(self):
        """set_param('sat_branching_weights', negative) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="non-negative"):
            m.set_param('sat_branching_weights', [1.0, -1.0])

    def test_set_phase_weights_validates_length(self):
        """set_param('opt_sat_branching_weights', wrong length) raises ValueError."""
        m = _make_small_model()
        with pytest.raises(ValueError, match="length"):
            m.set_param('opt_sat_branching_weights', [1.0, 2.0])

    def test_set_phase_priorities_validates_length(self):
        """set_param('sat_variable_priorities', wrong length) raises ValueError."""
        m = _make_small_model()
        with pytest.raises(ValueError, match="length"):
            m.set_param('sat_variable_priorities', [1.0, 2.0])


# =============================================================================
# 3. Resolution via _resolve_phase_params
# =============================================================================


class TestResolvePhaseParams:
    """Verify _resolve_phase_params() resolves correctly."""

    def test_resolve_uses_phase_specific_when_set(self):
        """Phase-specific param overrides unprefixed."""
        m = Model()
        m.set_param('branching_bias', 5.0)
        m.set_param('sat_branching_bias', 3.0)
        resolved = m._resolve_phase_params()
        assert resolved['sat']['branching_bias'] == 3.0

    def test_resolve_falls_back_to_unprefixed(self):
        """When no phase-specific set, uses unprefixed."""
        m = Model()
        m.set_param('branching_bias', 7.0)
        resolved = m._resolve_phase_params()
        assert resolved['sat']['branching_bias'] == 7.0
        assert resolved['opt_sat']['branching_bias'] == 7.0
        assert resolved['opt']['branching_bias'] == 7.0

    def test_resolve_uses_default_when_nothing_set(self):
        """When nothing set, uses built-in default."""
        m = Model()
        resolved = m._resolve_phase_params()
        assert resolved['sat']['branching_factor'] == DEFAULTS['branching_factor']

    def test_resolve_returns_all_three_phases(self):
        """resolve_all returns dict with sat, opt_sat, opt keys."""
        m = Model()
        resolved = m._resolve_phase_params()
        assert set(resolved.keys()) == {'sat', 'opt_sat', 'opt'}

    def test_resolve_each_phase_has_5_params(self):
        """Each phase in resolved dict has all 5 suffixes."""
        m = Model()
        resolved = m._resolve_phase_params()
        for phase in PHASES:
            assert set(resolved[phase].keys()) == set(PHASE_PARAM_SUFFIXES)

    def test_resolve_partial_phase_override(self):
        """Only sat_branching_bias set, others use unprefixed bias."""
        m = Model()
        m.set_param('branching_bias', 5.0)
        m.set_param('sat_branching_bias', 2.0)
        resolved = m._resolve_phase_params()
        assert resolved['sat']['branching_bias'] == 2.0
        assert resolved['opt_sat']['branching_bias'] == 5.0
        assert resolved['opt']['branching_bias'] == 5.0

    def test_resolve_weights_phase_specific(self):
        """Phase-specific weights resolve correctly."""
        m = _make_small_model()
        w = [1.0, 2.0, 3.0, 4.0, 5.0]
        m.set_param('sat_branching_weights', w)
        resolved = m._resolve_phase_params()
        assert resolved['sat']['branching_weights'] == w
        assert resolved['opt']['branching_weights'] is None


# =============================================================================
# 4. Backwards compatibility
# =============================================================================


class TestBackwardsCompat:
    """Verify unprefixed params still work as before."""

    def test_unprefixed_params_still_work(self):
        """set_param('branching_bias', 10.0) still works."""
        m = Model()
        m.set_param('branching_bias', 10.0)
        assert m.get_param('branching_bias') == 10.0

    def test_existing_solve_unchanged(self):
        """Solve with only unprefixed params still works."""
        m = _make_small_model()
        m.set_param('stopping_time', 1)
        m.set_param('num_workers', 1)
        m.set_param('branching_bias', 5.0)
        result = m.solve()
        assert isinstance(result, OptimizeResult)

    def test_copy_preserves_phase_params(self):
        """copy() preserves phase-specific params."""
        m = Model()
        m.set_param('sat_branching_bias', 42.0)
        m.set_param('opt_branching_factor', 2.0)
        m2 = copy(m)
        assert m2.get_param('sat_branching_bias') == 42.0
        assert m2.get_param('opt_branching_factor') == 2.0

    def test_get_param_default_for_phase_params(self):
        """get_param returns built-in default for unset phase params."""
        m = Model()
        assert m.get_param('sat_branching_factor') == DEFAULTS['branching_factor']
        assert m.get_param('opt_branching_bias') == DEFAULTS['branching_bias']
        assert m.get_param('sat_branching_weights') is None
        assert m.get_param('opt_variable_priorities') is None


# =============================================================================
# 5. Type coercion for phase params
# =============================================================================


class TestPhaseParamCoercion:
    """Verify type coercion for phase-specific scalar params."""

    def test_coerce_phase_bias_str_to_float(self):
        """set_param('sat_branching_bias', '3.0') coerces to float."""
        m = Model()
        m.set_param('sat_branching_bias', '3.0')
        val = m.get_param('sat_branching_bias')
        assert isinstance(val, float)
        assert val == 3.0

    def test_coerce_phase_factor_int_to_float(self):
        """set_param('opt_branching_factor', 2) coerces to float."""
        m = Model()
        m.set_param('opt_branching_factor', 2)
        val = m.get_param('opt_branching_factor')
        assert isinstance(val, float)
        assert val == 2.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
