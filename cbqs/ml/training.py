"""Offline training pipeline for branching weight prediction.

Provides the WeightPredictor class which wraps ExtraTreesRegressor
to train on (Model, best_weights) pairs and predict branching weights
for new Model instances. Uses Phase 25's FeatureExtractor for building
feature matrices from model structure.
"""
from datetime import datetime

import joblib
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor

import cbqs
from cbqs.ml.features import (
    FeatureExtractor,
    VARIABLE_FEATURE_NAMES,
    INSTANCE_FEATURE_NAMES,
)


class WeightPredictor:
    """Train and predict branching weights for CBQS models.

    Wraps sklearn's ExtraTreesRegressor to learn a mapping from structural
    model features (per-variable + instance-level) to branching weights.
    Each variable's weight is predicted independently using 20 features
    (9 per-variable + 11 instance features tiled per row).

    Parameters
    ----------
    n_estimators : int, optional
        Number of trees in the ensemble. Default is 100.
    random_state : int or None, optional
        Random seed for reproducibility. Default is None.

    Examples
    --------
    >>> from cbqs.Model import Model
    >>> from cbqs.ml.training import WeightPredictor
    >>> predictor = WeightPredictor(random_state=42)
    >>> predictor.fit([(model, best_weights)])
    >>> new_weights = predictor.predict(new_model)
    """

    def __init__(self, n_estimators=100, random_state=None):
        self._regressor = ExtraTreesRegressor(
            n_estimators=n_estimators, random_state=random_state
        )
        self._feature_extractor = FeatureExtractor()
        self._feature_names = list(VARIABLE_FEATURE_NAMES) + list(INSTANCE_FEATURE_NAMES)
        self._is_fitted = False
        self._n_training_instances = 0

    def _build_feature_matrix(self, model):
        """Build the combined feature matrix for a model.

        Extracts per-variable features (n_vars, 9) and instance features (11,),
        tiles instance features to match variable count, and horizontally stacks
        to produce a (n_vars, 20) feature matrix.

        Parameters
        ----------
        model : Model
            A closed CBQS Model instance.

        Returns
        -------
        numpy.ndarray
            Feature matrix of shape (n_vars, 20) with dtype float64.
        """
        var_features = self._feature_extractor.extract_variable_features(model)
        inst_features = self._feature_extractor.extract_instance_features(model)
        inst_tiled = np.tile(inst_features, (var_features.shape[0], 1))
        return np.hstack([var_features, inst_tiled])

    def fit(self, training_pairs):
        """Train the predictor on (Model, weights) pairs.

        Parameters
        ----------
        training_pairs : list of (Model, array-like)
            Each pair contains a closed Model and its best branching weight
            vector (length must match number of variables in the model).

        Returns
        -------
        self
            The fitted predictor (for method chaining).

        Raises
        ------
        ValueError
            If training_pairs is empty.
        """
        if len(training_pairs) == 0:
            raise ValueError("Training data must not be empty")

        X_parts = []
        y_parts = []

        for model, weights in training_pairs:
            X = self._build_feature_matrix(model)
            y = np.asarray(weights, dtype=np.float64)
            X_parts.append(X)
            y_parts.append(y)

        X_combined = np.vstack(X_parts)
        y_combined = np.concatenate(y_parts)

        self._regressor.fit(X_combined, y_combined)
        self._is_fitted = True
        self._n_training_instances = len(training_pairs)

        return self

    def predict(self, model):
        """Predict branching weights for a model.

        Parameters
        ----------
        model : Model
            A closed CBQS Model instance.

        Returns
        -------
        numpy.ndarray
            Non-negative float64 array of length n_vars.

        Raises
        ------
        RuntimeError
            If the predictor has not been fitted.
        """
        if not self._is_fitted:
            raise RuntimeError(
                "WeightPredictor has not been fitted. Call fit() first."
            )

        X = self._build_feature_matrix(model)
        raw = self._regressor.predict(X)
        clipped = np.clip(raw, 0, None)
        return clipped.astype(np.float64)

    def save(self, path):
        """Save the fitted predictor to disk.

        The saved artifact includes the trained model and metadata for
        compatibility checking on load.

        Parameters
        ----------
        path : str
            File path to save to (typically with .joblib extension).

        Raises
        ------
        RuntimeError
            If the predictor has not been fitted.
        """
        if not self._is_fitted:
            raise RuntimeError("Cannot save unfitted predictor")

        artifact = {
            'model': self._regressor,
            'feature_names': self._feature_names,
            'training_date': datetime.now().isoformat(),
            'n_training_instances': self._n_training_instances,
            'cbqs_version': cbqs.__version__,
        }
        joblib.dump(artifact, path)

    @classmethod
    def load(cls, path):
        """Load a fitted predictor from disk.

        Validates that the saved feature names match the current feature set
        to prevent silent wrong predictions from incompatible models.

        Parameters
        ----------
        path : str
            File path to load from.

        Returns
        -------
        WeightPredictor
            A fitted predictor instance.

        Raises
        ------
        ValueError
            If the saved feature names don't match current feature names.
        """
        artifact = joblib.load(path)

        expected = list(VARIABLE_FEATURE_NAMES) + list(INSTANCE_FEATURE_NAMES)
        saved = artifact['feature_names']

        if saved != expected:
            raise ValueError(
                f"Feature name mismatch: saved predictor has {saved}, "
                f"but current code expects {expected}"
            )

        predictor = cls.__new__(cls)
        predictor._regressor = artifact['model']
        predictor._feature_extractor = FeatureExtractor()
        predictor._feature_names = expected
        predictor._is_fitted = True
        predictor._n_training_instances = artifact['n_training_instances']

        return predictor
