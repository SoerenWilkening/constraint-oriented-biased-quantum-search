"""Regressor wrappers for CBQS ML pipeline.

Provides three classes:
- VariableRegressor: Per-variable multi-output regressor with warm-start.
  Maps (n_vars, 20) feature matrices to multi-output predictions
  (weights + priorities per variable).
- InstanceRegressor: Instance-level regressor for global parameters.
  Maps (11,) instance feature vectors to global parameters
  (bias, branching_factor, bias_factor).
- PhasePredictor: Composite predictor combining variable and instance
  regressors for one trainer type (SAT or OPT).

Post-processing: weights clipped to non-negative, bias clipped to > -1,
factors clipped to >= 0. Priorities converted to argsort ordering.
"""
import joblib
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor


class VariableRegressor:
    """Per-variable multi-output regressor with warm-start.

    Wraps ExtraTreesRegressor to predict per-variable outputs (weights and
    priorities) from structural features. Supports warm-start for
    incremental training.

    Parameters
    ----------
    n_outputs : int
        Number of output columns per variable. 2 for SAT mode
        (weight, priority), 4 for OPT mode (opt_sat_w, opt_sat_p,
        opt_w, opt_p).
    n_estimators : int
        Number of trees in the ensemble.
    random_state : int or None
        Random seed for reproducibility.
    """

    def __init__(self, n_outputs, n_estimators=100, random_state=None):
        self.model = ExtraTreesRegressor(
            n_estimators=n_estimators,
            warm_start=True,
            random_state=random_state,
        )
        self.n_outputs = n_outputs
        self._is_fitted = False

    def fit(self, X_list, y_list):
        """Fit on list of per-instance feature matrices and target arrays.

        Stacks all instances vertically before fitting, so instances with
        different numbers of variables can be combined.

        Parameters
        ----------
        X_list : list of numpy.ndarray
            Each array has shape (n_vars_i, 20).
        y_list : list of numpy.ndarray
            Each array has shape (n_vars_i, n_outputs).

        Returns
        -------
        self
        """
        X_combined = np.vstack(X_list)
        y_combined = np.vstack(y_list)
        self.model.fit(X_combined, y_combined)
        self._is_fitted = True
        return self

    def predict(self, X):
        """Predict for a single instance.

        Parameters
        ----------
        X : numpy.ndarray
            Feature matrix of shape (n_vars, 20).

        Returns
        -------
        numpy.ndarray
            Predictions of shape (n_vars, n_outputs).
        """
        raw = self.model.predict(X)
        if raw.ndim == 1:
            raw = raw.reshape(-1, 1)
        return raw

    def add_trees(self, n_new):
        """Increase n_estimators for next warm-start fit.

        Parameters
        ----------
        n_new : int
            Number of new trees to add.
        """
        self.model.n_estimators += n_new

    @staticmethod
    def postprocess_weights(raw):
        """Clip weights to non-negative.

        Parameters
        ----------
        raw : numpy.ndarray
            Raw predicted weight values.

        Returns
        -------
        numpy.ndarray
            Clipped weights (all >= 0).
        """
        return np.clip(raw, 0, None)

    @staticmethod
    def postprocess_priorities(raw):
        """Convert raw priority scores to variable ordering.

        Returns argsort indices in descending priority order, so the
        highest-priority variable comes first.

        Parameters
        ----------
        raw : numpy.ndarray
            Raw predicted priority scores, shape (n_vars,).

        Returns
        -------
        numpy.ndarray
            Integer array of variable indices sorted by descending priority.
        """
        return np.argsort(-raw)


class InstanceRegressor:
    """Instance-level regressor for global parameters.

    Wraps ExtraTreesRegressor to predict instance-level parameters
    (bias, branching_factor, bias_factor) from instance features.
    Supports warm-start for incremental training.

    Parameters
    ----------
    n_outputs : int
        Number of output values. 3 for SAT mode
        (bias, branching_factor, bias_factor), 6 for OPT mode
        (opt_sat_bias, opt_sat_bf, opt_sat_bif, opt_bias, opt_bf, opt_bif).
    n_estimators : int
        Number of trees in the ensemble.
    random_state : int or None
        Random seed for reproducibility.
    """

    def __init__(self, n_outputs, n_estimators=100, random_state=None):
        self.model = ExtraTreesRegressor(
            n_estimators=n_estimators,
            warm_start=True,
            random_state=random_state,
        )
        self.n_outputs = n_outputs
        self._is_fitted = False

    def fit(self, X, y):
        """Fit on instance feature matrix.

        Parameters
        ----------
        X : numpy.ndarray
            Feature matrix of shape (n_instances, 11).
        y : numpy.ndarray
            Target matrix of shape (n_instances, n_outputs).

        Returns
        -------
        self
        """
        self.model.fit(X, y)
        self._is_fitted = True
        return self

    def predict(self, X):
        """Predict for a single instance.

        Parameters
        ----------
        X : numpy.ndarray
            Feature matrix of shape (1, 11).

        Returns
        -------
        numpy.ndarray
            Predictions of shape (n_outputs,).
        """
        raw = self.model.predict(X)
        return raw.ravel()

    def add_trees(self, n_new):
        """Increase n_estimators for next warm-start fit.

        Parameters
        ----------
        n_new : int
            Number of new trees to add.
        """
        self.model.n_estimators += n_new

    @staticmethod
    def postprocess_globals(raw, mode):
        """Clip and unpack raw predictions into a named dict.

        Bias is clipped to > -1 (using -0.99 as minimum), factors are
        clipped to >= 0.

        Parameters
        ----------
        raw : numpy.ndarray
            Raw predicted values.
        mode : str
            'sat' for 3 outputs (bias, branching_factor, bias_factor),
            'opt' for 6 outputs (opt_sat_bias, opt_sat_bf, opt_sat_bif,
            opt_bias, opt_bf, opt_bif).

        Returns
        -------
        dict
            Named parameter dict with clipped values.
        """
        def clip_bias(v):
            return max(v, -0.99)

        def clip_factor(v):
            return max(v, 0.0)

        if mode == 'sat':
            return {
                'bias': clip_bias(float(raw[0])),
                'branching_factor': clip_factor(float(raw[1])),
                'bias_factor': clip_factor(float(raw[2])),
            }
        elif mode == 'opt':
            return {
                'opt_sat_bias': clip_bias(float(raw[0])),
                'opt_sat_branching_factor': clip_factor(float(raw[1])),
                'opt_sat_bias_factor': clip_factor(float(raw[2])),
                'opt_bias': clip_bias(float(raw[3])),
                'opt_branching_factor': clip_factor(float(raw[4])),
                'opt_bias_factor': clip_factor(float(raw[5])),
            }
        else:
            raise ValueError(f"Unknown mode: {mode!r}. Expected 'sat' or 'opt'.")


class PhasePredictor:
    """Composite predictor: variable + instance regressors for one trainer type.

    Combines a VariableRegressor (per-variable weights and priorities) with
    an InstanceRegressor (global parameters) into a single prediction
    interface.

    Parameters
    ----------
    mode : str
        'sat' for SAT trainer (var: 2 outputs, inst: 3 outputs),
        'opt' for OPT trainer (var: 4 outputs, inst: 6 outputs).
    n_estimators : int
        Number of trees in each ensemble.
    random_state : int or None
        Random seed for reproducibility.
    """

    def __init__(self, mode='sat', n_estimators=100, random_state=None):
        self.mode = mode

        if mode == 'sat':
            var_outputs = 2
            inst_outputs = 3
        elif mode == 'opt':
            var_outputs = 4
            inst_outputs = 6
        else:
            raise ValueError(f"Unknown mode: {mode!r}. Expected 'sat' or 'opt'.")

        self.var_regressor = VariableRegressor(
            n_outputs=var_outputs,
            n_estimators=n_estimators,
            random_state=random_state,
        )
        self.inst_regressor = InstanceRegressor(
            n_outputs=inst_outputs,
            n_estimators=n_estimators,
            random_state=random_state,
        )
        self._is_fitted = False

    def fit(self, var_X_list, var_y_list, inst_X, inst_y):
        """Fit both regressors.

        Parameters
        ----------
        var_X_list : list of numpy.ndarray
            Per-instance variable feature matrices, each (n_vars_i, 20).
        var_y_list : list of numpy.ndarray
            Per-instance variable targets, each (n_vars_i, n_var_outputs).
        inst_X : numpy.ndarray
            Instance feature matrix, shape (n_instances, 11).
        inst_y : numpy.ndarray
            Instance target matrix, shape (n_instances, n_inst_outputs).

        Returns
        -------
        self
        """
        self.var_regressor.fit(var_X_list, var_y_list)
        self.inst_regressor.fit(inst_X, inst_y)
        self._is_fitted = True
        return self

    def predict(self, var_features, inst_features):
        """Predict parameters for a single instance.

        Parameters
        ----------
        var_features : numpy.ndarray
            Variable feature matrix, shape (n_vars, 20).
        inst_features : numpy.ndarray
            Instance feature vector, shape (1, 11).

        Returns
        -------
        dict
            Parameter dict ready for solver configuration.
        """
        var_raw = self.var_regressor.predict(var_features)
        inst_raw = self.inst_regressor.predict(inst_features)
        inst_params = InstanceRegressor.postprocess_globals(inst_raw, self.mode)

        if self.mode == 'sat':
            weights = VariableRegressor.postprocess_weights(var_raw[:, 0])
            priorities = VariableRegressor.postprocess_priorities(var_raw[:, 1])
            result = {
                'weights': weights,
                'priorities': priorities,
            }
            result.update(inst_params)
            return result

        elif self.mode == 'opt':
            opt_sat_weights = VariableRegressor.postprocess_weights(var_raw[:, 0])
            opt_sat_priorities = VariableRegressor.postprocess_priorities(var_raw[:, 1])
            opt_weights = VariableRegressor.postprocess_weights(var_raw[:, 2])
            opt_priorities = VariableRegressor.postprocess_priorities(var_raw[:, 3])
            result = {
                'opt_sat_weights': opt_sat_weights,
                'opt_sat_priorities': opt_sat_priorities,
                'opt_weights': opt_weights,
                'opt_priorities': opt_priorities,
            }
            result.update(inst_params)
            return result

    def warm_start_fit(self, var_X_list, var_y_list, inst_X, inst_y,
                       n_new_trees=50):
        """Incrementally train by adding trees and refitting.

        Parameters
        ----------
        var_X_list : list of numpy.ndarray
            New per-instance variable feature matrices.
        var_y_list : list of numpy.ndarray
            New per-instance variable targets.
        inst_X : numpy.ndarray
            New instance feature matrix.
        inst_y : numpy.ndarray
            New instance target matrix.
        n_new_trees : int
            Number of new trees to add to each ensemble.

        Returns
        -------
        self
        """
        self.var_regressor.add_trees(n_new_trees)
        self.inst_regressor.add_trees(n_new_trees)
        self.var_regressor.fit(var_X_list, var_y_list)
        self.inst_regressor.fit(inst_X, inst_y)
        return self

    def save(self, path):
        """Save the fitted predictor to disk.

        Parameters
        ----------
        path : str
            File path to save to (typically with .joblib extension).
        """
        artifact = {
            'mode': self.mode,
            'var_regressor': self.var_regressor,
            'inst_regressor': self.inst_regressor,
        }
        joblib.dump(artifact, path)

    @classmethod
    def load(cls, path):
        """Load a fitted predictor from disk.

        Parameters
        ----------
        path : str
            File path to load from.

        Returns
        -------
        PhasePredictor
            A fitted predictor instance.
        """
        artifact = joblib.load(path)
        predictor = cls.__new__(cls)
        predictor.mode = artifact['mode']
        predictor.var_regressor = artifact['var_regressor']
        predictor.inst_regressor = artifact['inst_regressor']
        predictor._is_fitted = True
        return predictor
