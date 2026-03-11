"""Tests for cbqs.ml.phase_params — phase-specific parameter resolution."""
import pytest
import json
import tempfile
import os

from cbqs.ml.phase_params import (
    PHASES,
    PHASE_PARAM_SUFFIXES,
    PhaseParamResolver,
    make_phase_param_defs,
    validate_weights,
    validate_priorities,
    DEFAULTS,
)


# ============================================================
# Parameter definitions
# ============================================================

class TestParameterDefinitions:
    def test_all_phase_params_defined(self):
        """15 phase-specific params exist (3 phases x 5 suffixes)."""
        defs = make_phase_param_defs()
        assert len(defs) == 15

    def test_phase_param_names_follow_convention(self):
        """All keys follow sat_*, opt_sat_*, opt_* naming."""
        defs = make_phase_param_defs()
        for key in defs:
            parts = key.split('_', 1)
            # opt_sat prefix has two underscores before suffix
            prefix_found = False
            for phase in PHASES:
                for suffix in PHASE_PARAM_SUFFIXES:
                    if key == f"{phase}_{suffix}":
                        prefix_found = True
            assert prefix_found, f"Key {key} does not follow convention"

    def test_each_phase_has_5_params(self):
        """Each phase has exactly 5 parameter entries."""
        defs = make_phase_param_defs()
        for phase in PHASES:
            phase_keys = [
                k for k in defs
                if any(k == f"{phase}_{s}" for s in PHASE_PARAM_SUFFIXES)
            ]
            assert len(phase_keys) == 5, (
                f"Phase {phase} has {len(phase_keys)} params, expected 5"
            )


# ============================================================
# Resolution logic
# ============================================================

class TestResolutionLogic:
    def test_phase_specific_overrides_unprefixed(self):
        """sat_branching_bias=3 + branching_bias=5 -> sat gets 3."""
        store = {'sat_branching_bias': 3.0, 'branching_bias': 5.0}
        resolver = PhaseParamResolver(store, DEFAULTS)
        assert resolver.resolve('sat', 'branching_bias') == 3.0

    def test_unprefixed_fallback_when_no_phase_param(self):
        """branching_bias=5, no sat_branching_bias -> sat gets 5."""
        store = {'branching_bias': 5.0}
        resolver = PhaseParamResolver(store, DEFAULTS)
        assert resolver.resolve('sat', 'branching_bias') == 5.0

    def test_default_when_nothing_set(self):
        """No branching_bias, no sat_branching_bias -> default."""
        store = {}
        resolver = PhaseParamResolver(store, DEFAULTS)
        result = resolver.resolve('sat', 'branching_bias')
        assert result == DEFAULTS['branching_bias']

    def test_resolve_all_phases(self):
        """resolve_all returns dict with sat/opt_sat/opt keys."""
        store = {'branching_bias': 7.0}
        resolver = PhaseParamResolver(store, DEFAULTS)
        result = resolver.resolve_all()
        assert set(result.keys()) == set(PHASES)
        for phase in PHASES:
            assert set(result[phase].keys()) == set(PHASE_PARAM_SUFFIXES)
            assert result[phase]['branching_bias'] == 7.0

    def test_partial_phase_override(self):
        """Only sat_branching_bias set, others use unprefixed."""
        store = {
            'sat_branching_bias': 2.0,
            'branching_bias': 10.0,
            'branching_factor': 3.0,
        }
        resolver = PhaseParamResolver(store, DEFAULTS)
        result = resolver.resolve_all()
        # sat gets override
        assert result['sat']['branching_bias'] == 2.0
        # opt_sat and opt fall back to unprefixed
        assert result['opt_sat']['branching_bias'] == 10.0
        assert result['opt']['branching_bias'] == 10.0
        # branching_factor uses unprefixed for all
        for phase in PHASES:
            assert result[phase]['branching_factor'] == 3.0

    def test_resolve_invalid_phase_raises(self):
        """Resolving unknown phase raises ValueError."""
        store = {}
        resolver = PhaseParamResolver(store, DEFAULTS)
        with pytest.raises(ValueError, match="Unknown phase"):
            resolver.resolve('unknown', 'branching_bias')

    def test_resolve_invalid_suffix_raises(self):
        """Resolving unknown suffix raises ValueError."""
        store = {}
        resolver = PhaseParamResolver(store, DEFAULTS)
        with pytest.raises(ValueError, match="Unknown param suffix"):
            resolver.resolve('sat', 'unknown_param')


# ============================================================
# Validation
# ============================================================

class TestValidation:
    def test_phase_bias_validates_gt_minus_one(self):
        """branching_bias must be > -1."""
        store = {'sat_branching_bias': -0.5}
        resolver = PhaseParamResolver(store, DEFAULTS)
        # -0.5 > -1, should be fine
        assert resolver.resolve('sat', 'branching_bias') == -0.5

        store2 = {'sat_branching_bias': -1.0}
        resolver2 = PhaseParamResolver(store2, DEFAULTS)
        with pytest.raises(ValueError, match="branching_bias must be > -1"):
            resolver2.resolve('sat', 'branching_bias')

        store3 = {'sat_branching_bias': -2.0}
        resolver3 = PhaseParamResolver(store3, DEFAULTS)
        with pytest.raises(ValueError, match="branching_bias must be > -1"):
            resolver3.resolve('sat', 'branching_bias')

    def test_phase_weights_validates_array(self):
        """branching_weights must be a list/array of non-negative numbers."""
        # Valid
        validate_weights([0.1, 0.2, 0.3], n_vars=3)

        # Wrong length
        with pytest.raises(ValueError, match="length"):
            validate_weights([0.1, 0.2], n_vars=3)

        # Negative value
        with pytest.raises(ValueError, match="non-negative"):
            validate_weights([0.1, -0.2, 0.3], n_vars=3)

        # None is valid (means unset)
        validate_weights(None, n_vars=3)

    def test_phase_priorities_validates_array(self):
        """variable_priorities must be a list/array of numbers."""
        # Valid
        validate_priorities([1, 2, 3], n_vars=3)

        # Wrong length
        with pytest.raises(ValueError, match="length"):
            validate_priorities([1, 2], n_vars=3)

        # None is valid (means unset)
        validate_priorities(None, n_vars=3)

    def test_branching_factor_validates_non_negative(self):
        """branching_factor must be >= 0."""
        store = {'sat_branching_factor': -1.0}
        resolver = PhaseParamResolver(store, DEFAULTS)
        with pytest.raises(ValueError, match="branching_factor must be non-negative"):
            resolver.resolve('sat', 'branching_factor')

    def test_bias_factor_validates_non_negative(self):
        """bias_factor must be >= 0."""
        store = {'opt_bias_factor': -0.1}
        resolver = PhaseParamResolver(store, DEFAULTS)
        with pytest.raises(ValueError, match="bias_factor must be non-negative"):
            resolver.resolve('opt', 'bias_factor')


# ============================================================
# Serialization
# ============================================================

class TestSerialization:
    def test_params_to_ctx_dict(self):
        """to_ctx_kwargs flattens resolved params for C layer."""
        store = {
            'branching_bias': 5.0,
            'branching_factor': 1.0,
            'bias_factor': 1.0,
        }
        resolver = PhaseParamResolver(store, DEFAULTS)
        ctx = resolver.to_ctx_kwargs()

        # Should have keys for each phase+suffix combination
        assert 'sat_branching_bias' in ctx
        assert 'opt_sat_branching_bias' in ctx
        assert 'opt_branching_bias' in ctx
        assert ctx['sat_branching_bias'] == 5.0
        assert ctx['opt_branching_bias'] == 5.0

    def test_round_trip_save_load(self):
        """Resolved params can be serialized to JSON and loaded back."""
        store = {
            'sat_branching_bias': 3.0,
            'branching_bias': 5.0,
            'branching_factor': 2.0,
        }
        resolver = PhaseParamResolver(store, DEFAULTS)
        resolved = resolver.resolve_all()

        # Serialize
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                          delete=False) as f:
            json.dump(resolved, f)
            tmp_path = f.name

        try:
            # Load
            with open(tmp_path, 'r') as f:
                loaded = json.load(f)

            assert loaded == resolved
            assert loaded['sat']['branching_bias'] == 3.0
            assert loaded['opt']['branching_bias'] == 5.0
        finally:
            os.unlink(tmp_path)

    def test_to_ctx_kwargs_all_15_keys(self):
        """to_ctx_kwargs produces exactly 15 keys."""
        store = {}
        resolver = PhaseParamResolver(store, DEFAULTS)
        ctx = resolver.to_ctx_kwargs()
        assert len(ctx) == 15
