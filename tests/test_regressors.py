"""Tests for cbqs.ml.regressors module.

Tests VariableRegressor, InstanceRegressor, and PhasePredictor classes
covering fit/predict shape, post-processing, warm-start, multi-output
modes, save/load roundtrip, and composite prediction.
"""
import os
import tempfile

import numpy as np
import pytest

from cbqs.ml.regressors import (
    VariableRegressor,
    InstanceRegressor,
    PhasePredictor,
)


# ---------------------------------------------------------------------------
# VariableRegressor tests
# ---------------------------------------------------------------------------

class TestVariableRegressor:

    def test_var_regressor_fit_predict_shape(self):
        """Fit on stacked (n_samples*n_vars, 20) and predict (n_vars, k)."""
        rng = np.random.RandomState(42)
        n_vars_a, n_vars_b = 5, 8
        n_features = 20
        n_outputs = 2

        X_list = [
            rng.randn(n_vars_a, n_features),
            rng.randn(n_vars_b, n_features),
        ]
        y_list = [
            rng.randn(n_vars_a, n_outputs),
            rng.randn(n_vars_b, n_outputs),
        ]

        reg = VariableRegressor(n_outputs=n_outputs, n_estimators=10,
                                random_state=42)
        reg.fit(X_list, y_list)

        # Predict for a single instance with 6 variables
        X_new = rng.randn(6, n_features)
        pred = reg.predict(X_new)
        assert pred.shape == (6, n_outputs)

    def test_var_regressor_weights_nonnegative(self):
        """Post-processing clips weights to non-negative."""
        raw = np.array([-0.5, 0.0, 1.2, -3.0, 0.7])
        clipped = VariableRegressor.postprocess_weights(raw)
        assert np.all(clipped >= 0)
        np.testing.assert_array_equal(clipped, [0.0, 0.0, 1.2, 0.0, 0.7])

    def test_var_regressor_warm_start_adds_trees(self):
        """Tree count increases after add_trees and refit."""
        rng = np.random.RandomState(42)
        n_outputs = 2

        X_list = [rng.randn(5, 20)]
        y_list = [rng.randn(5, n_outputs)]

        reg = VariableRegressor(n_outputs=n_outputs, n_estimators=10,
                                random_state=42)
        reg.fit(X_list, y_list)
        assert reg.model.n_estimators == 10

        reg.add_trees(20)
        assert reg.model.n_estimators == 30

        # Refit should work with the new tree count
        reg.fit(X_list, y_list)
        assert len(reg.model.estimators_) == 30

    def test_var_regressor_multi_output_sat(self):
        """SAT mode: k=2 outputs [weight, priority]."""
        rng = np.random.RandomState(42)
        n_outputs = 2

        X_list = [rng.randn(5, 20)]
        y_list = [rng.randn(5, n_outputs)]

        reg = VariableRegressor(n_outputs=n_outputs, n_estimators=10,
                                random_state=42)
        reg.fit(X_list, y_list)

        pred = reg.predict(rng.randn(5, 20))
        assert pred.shape == (5, 2)

    def test_var_regressor_multi_output_opt(self):
        """OPT mode: k=4 outputs [opt_sat_w, opt_sat_p, opt_w, opt_p]."""
        rng = np.random.RandomState(42)
        n_outputs = 4

        X_list = [rng.randn(5, 20)]
        y_list = [rng.randn(5, n_outputs)]

        reg = VariableRegressor(n_outputs=n_outputs, n_estimators=10,
                                random_state=42)
        reg.fit(X_list, y_list)

        pred = reg.predict(rng.randn(5, 20))
        assert pred.shape == (5, 4)


# ---------------------------------------------------------------------------
# InstanceRegressor tests
# ---------------------------------------------------------------------------

class TestInstanceRegressor:

    def test_inst_regressor_fit_predict_shape(self):
        """Fit on (n_samples, 11) and predict (n_outputs,) per instance."""
        rng = np.random.RandomState(42)
        n_samples = 20
        n_features = 11
        n_outputs = 3

        X = rng.randn(n_samples, n_features)
        y = rng.randn(n_samples, n_outputs)

        reg = InstanceRegressor(n_outputs=n_outputs, n_estimators=10,
                                random_state=42)
        reg.fit(X, y)

        X_new = rng.randn(1, n_features)
        pred = reg.predict(X_new)
        assert pred.shape == (n_outputs,)

    def test_inst_regressor_bias_clipped(self):
        """Post-processing clips bias > -1."""
        raw = np.array([-2.0, 0.5, 1.0])
        result = InstanceRegressor.postprocess_globals(raw, mode='sat')
        assert result['bias'] > -1

    def test_inst_regressor_factors_nonneg(self):
        """Post-processing clips factors >= 0."""
        raw = np.array([-2.0, -0.5, -1.0])
        result = InstanceRegressor.postprocess_globals(raw, mode='sat')
        assert result['branching_factor'] >= 0
        assert result['bias_factor'] >= 0

    def test_inst_regressor_warm_start_adds_trees(self):
        """Tree count increases after add_trees and refit."""
        rng = np.random.RandomState(42)

        X = rng.randn(10, 11)
        y = rng.randn(10, 3)

        reg = InstanceRegressor(n_outputs=3, n_estimators=10,
                                random_state=42)
        reg.fit(X, y)
        assert reg.model.n_estimators == 10

        reg.add_trees(15)
        assert reg.model.n_estimators == 25

        reg.fit(X, y)
        assert len(reg.model.estimators_) == 25

    def test_inst_regressor_sat_output(self):
        """SAT mode: k=3 outputs [bias, branching_factor, bias_factor]."""
        rng = np.random.RandomState(42)

        X = rng.randn(10, 11)
        y = rng.randn(10, 3)

        reg = InstanceRegressor(n_outputs=3, n_estimators=10,
                                random_state=42)
        reg.fit(X, y)

        pred = reg.predict(rng.randn(1, 11))
        assert pred.shape == (3,)

        result = InstanceRegressor.postprocess_globals(pred, mode='sat')
        assert 'bias' in result
        assert 'branching_factor' in result
        assert 'bias_factor' in result

    def test_inst_regressor_opt_output(self):
        """OPT mode: k=6 outputs [opt_sat_bias, opt_sat_bf, opt_sat_bif,
        opt_bias, opt_bf, opt_bif]."""
        rng = np.random.RandomState(42)

        X = rng.randn(10, 11)
        y = rng.randn(10, 6)

        reg = InstanceRegressor(n_outputs=6, n_estimators=10,
                                random_state=42)
        reg.fit(X, y)

        pred = reg.predict(rng.randn(1, 11))
        assert pred.shape == (6,)

        result = InstanceRegressor.postprocess_globals(pred, mode='opt')
        assert 'opt_sat_bias' in result
        assert 'opt_sat_branching_factor' in result
        assert 'opt_sat_bias_factor' in result
        assert 'opt_bias' in result
        assert 'opt_branching_factor' in result
        assert 'opt_bias_factor' in result

        # All biases > -1, all factors >= 0
        assert result['opt_sat_bias'] > -1
        assert result['opt_bias'] > -1
        assert result['opt_sat_branching_factor'] >= 0
        assert result['opt_sat_bias_factor'] >= 0
        assert result['opt_branching_factor'] >= 0
        assert result['opt_bias_factor'] >= 0


# ---------------------------------------------------------------------------
# PhasePredictor tests
# ---------------------------------------------------------------------------

class TestPhasePredictor:

    def _make_sat_data(self, rng, n_instances=5, n_vars=8):
        """Helper to generate SAT training data."""
        var_X_list = [rng.randn(n_vars, 20) for _ in range(n_instances)]
        var_y_list = [rng.randn(n_vars, 2) for _ in range(n_instances)]
        inst_X = rng.randn(n_instances, 11)
        inst_y = rng.randn(n_instances, 3)
        return {
            'var_X_list': var_X_list,
            'var_y_list': var_y_list,
            'inst_X': inst_X,
            'inst_y': inst_y,
        }

    def _make_opt_data(self, rng, n_instances=5, n_vars=8):
        """Helper to generate OPT training data."""
        var_X_list = [rng.randn(n_vars, 20) for _ in range(n_instances)]
        var_y_list = [rng.randn(n_vars, 4) for _ in range(n_instances)]
        inst_X = rng.randn(n_instances, 11)
        inst_y = rng.randn(n_instances, 6)
        return {
            'var_X_list': var_X_list,
            'var_y_list': var_y_list,
            'inst_X': inst_X,
            'inst_y': inst_y,
        }

    def test_phase_predictor_sat_predict(self):
        """SAT predictor returns dict with weights, priorities, bias, factors."""
        rng = np.random.RandomState(42)
        data = self._make_sat_data(rng)

        pred = PhasePredictor(mode='sat', n_estimators=10, random_state=42)
        pred.fit(data['var_X_list'], data['var_y_list'],
                 data['inst_X'], data['inst_y'])

        var_features = rng.randn(6, 20)
        inst_features = rng.randn(1, 11)
        result = pred.predict(var_features, inst_features)

        assert 'weights' in result
        assert 'priorities' in result
        assert 'bias' in result
        assert 'branching_factor' in result
        assert 'bias_factor' in result

        assert result['weights'].shape == (6,)
        assert result['priorities'].shape == (6,)
        assert np.all(result['weights'] >= 0)
        assert result['bias'] > -1
        assert result['branching_factor'] >= 0
        assert result['bias_factor'] >= 0

    def test_phase_predictor_opt_predict(self):
        """OPT predictor returns dict with opt_sat_* and opt_* parameters."""
        rng = np.random.RandomState(42)
        data = self._make_opt_data(rng)

        pred = PhasePredictor(mode='opt', n_estimators=10, random_state=42)
        pred.fit(data['var_X_list'], data['var_y_list'],
                 data['inst_X'], data['inst_y'])

        var_features = rng.randn(6, 20)
        inst_features = rng.randn(1, 11)
        result = pred.predict(var_features, inst_features)

        # OPT mode should have both opt_sat and opt keys
        assert 'opt_sat_weights' in result
        assert 'opt_sat_priorities' in result
        assert 'opt_weights' in result
        assert 'opt_priorities' in result
        assert 'opt_sat_bias' in result
        assert 'opt_bias' in result
        assert 'opt_sat_branching_factor' in result
        assert 'opt_branching_factor' in result
        assert 'opt_sat_bias_factor' in result
        assert 'opt_bias_factor' in result

        n_vars = 6
        assert result['opt_sat_weights'].shape == (n_vars,)
        assert result['opt_priorities'].shape == (n_vars,)
        assert np.all(result['opt_sat_weights'] >= 0)
        assert np.all(result['opt_weights'] >= 0)
        assert result['opt_sat_bias'] > -1
        assert result['opt_bias'] > -1

    def test_phase_predictor_save_load_roundtrip(self):
        """Save and load produces identical predictions."""
        rng = np.random.RandomState(42)
        data = self._make_sat_data(rng)

        pred = PhasePredictor(mode='sat', n_estimators=10, random_state=42)
        pred.fit(data['var_X_list'], data['var_y_list'],
                 data['inst_X'], data['inst_y'])

        var_features = rng.randn(6, 20)
        inst_features = rng.randn(1, 11)
        result_before = pred.predict(var_features, inst_features)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'predictor.joblib')
            pred.save(path)

            loaded = PhasePredictor.load(path)
            result_after = loaded.predict(var_features, inst_features)

        np.testing.assert_array_equal(result_before['weights'],
                                      result_after['weights'])
        np.testing.assert_array_equal(result_before['priorities'],
                                      result_after['priorities'])
        assert result_before['bias'] == result_after['bias']

    def test_phase_predictor_warm_start(self):
        """warm_start_fit adds trees and refits."""
        rng = np.random.RandomState(42)
        data = self._make_sat_data(rng)

        pred = PhasePredictor(mode='sat', n_estimators=10, random_state=42)
        pred.fit(data['var_X_list'], data['var_y_list'],
                 data['inst_X'], data['inst_y'])

        trees_before = pred.var_regressor.model.n_estimators

        new_data = self._make_sat_data(rng, n_instances=3)
        pred.warm_start_fit(
            new_data['var_X_list'], new_data['var_y_list'],
            new_data['inst_X'], new_data['inst_y'],
            n_new_trees=50,
        )

        trees_after = pred.var_regressor.model.n_estimators
        assert trees_after == trees_before + 50

    def test_phase_predictor_initial_fit_tree_count(self):
        """Initial fit uses the configured n_estimators."""
        rng = np.random.RandomState(42)
        data = self._make_sat_data(rng)

        pred = PhasePredictor(mode='sat', n_estimators=20, random_state=42)
        pred.fit(data['var_X_list'], data['var_y_list'],
                 data['inst_X'], data['inst_y'])

        assert len(pred.var_regressor.model.estimators_) == 20
        assert len(pred.inst_regressor.model.estimators_) == 20

    def test_phase_predictor_incremental_tree_count(self):
        """Incremental warm_start grows the ensemble."""
        rng = np.random.RandomState(42)
        data = self._make_sat_data(rng)

        pred = PhasePredictor(mode='sat', n_estimators=10, random_state=42)
        pred.fit(data['var_X_list'], data['var_y_list'],
                 data['inst_X'], data['inst_y'])

        assert len(pred.var_regressor.model.estimators_) == 10

        new_data = self._make_sat_data(rng, n_instances=2)
        pred.warm_start_fit(
            new_data['var_X_list'], new_data['var_y_list'],
            new_data['inst_X'], new_data['inst_y'],
            n_new_trees=30,
        )

        assert len(pred.var_regressor.model.estimators_) == 40
        assert len(pred.inst_regressor.model.estimators_) == 40
