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


# ---------------------------------------------------------------------------
# Data collection and evaluation utilities
# ---------------------------------------------------------------------------

def _rank_result(result):
    """Sort key for solver results: feasibility first, then best objective.

    Parameters
    ----------
    result : OptimizeResult
        A CBQS solve result.

    Returns
    -------
    tuple
        (feasible: bool, objective: int/float) for max-sort ranking.
    """
    return (result.feasible, result.objective)


def collect_training_data(models, n_strategies=10, stopping_time=5,
                          num_workers=2, random_state=None):
    """Solve each model with diverse weight strategies, return (Model, best_weights) pairs.

    For each model, generates ``n_strategies`` random weight vectors using an
    exponential distribution, solves with each, and selects the best by
    feasibility-first / objective-tiebreak ranking.

    Parameters
    ----------
    models : list of Model
        Closed Model instances to collect training data from.
    n_strategies : int
        Number of random weight strategies to try per model.
    stopping_time : float
        Solve time budget in seconds per strategy.
    num_workers : int
        Number of solver threads per solve call.
    random_state : int or None
        Random seed for reproducibility.

    Returns
    -------
    list of (Model, numpy.ndarray)
        Training pairs where each ndarray is the best weight vector found.

    Raises
    ------
    ValueError
        If models list is empty.
    """
    if len(models) == 0:
        raise ValueError("Models list must not be empty")

    rng = np.random.RandomState(random_state)
    training_pairs = []

    for model in models:
        n_vars = len(model.variables)
        best_result = None
        best_weights = None

        for _ in range(n_strategies):
            weights = rng.exponential(1.0, size=n_vars)

            model.set_param('branching_weights', weights)
            model.set_param('stopping_time', stopping_time)
            model.set_param('num_workers', num_workers)

            result = model.solve()

            if best_result is None or _rank_result(result) > _rank_result(best_result):
                best_result = result
                best_weights = weights.copy()

        # Reset branching_weights after done with this model
        model.set_param('branching_weights', None)

        if best_weights is not None:
            training_pairs.append((model, best_weights))

    return training_pairs


def _print_comparison_table(results):
    """Print a human-readable comparison table of evaluation results.

    Parameters
    ----------
    results : dict
        Strategy results: {name: {'mean_objective': float, 'feasibility_rate': float}}.
    """
    # Determine column widths
    name_width = max(len(name) for name in results)
    name_width = max(name_width, len("Strategy"))

    header = f"{'Strategy':<{name_width}}  {'Mean Objective':>15}  {'Feasibility Rate':>17}"
    separator = "-" * len(header)

    print(separator)
    print(header)
    print(separator)

    for name, metrics in results.items():
        obj_str = f"{metrics['mean_objective']:.4f}"
        feas_str = f"{metrics['feasibility_rate']:.4f}"
        print(f"{name:<{name_width}}  {obj_str:>15}  {feas_str:>17}")

    print(separator)


def evaluate(predictor, test_models, stopping_time=5, num_workers=2,
             baselines=None):
    """Compare predicted weights against uniform and optional baselines.

    Solves each test model with predicted weights and uniform weights (plus any
    additional baselines), then reports mean objective and feasibility rate.

    Parameters
    ----------
    predictor : WeightPredictor
        A fitted weight predictor.
    test_models : list of Model
        Closed Model instances to evaluate on.
    stopping_time : float
        Solve time budget in seconds per evaluation solve.
    num_workers : int
        Number of solver threads per solve call.
    baselines : dict or None
        Additional weight strategies: ``{name: callable(model) -> weights_array}``.

    Returns
    -------
    dict
        Strategy results: ``{name: {'mean_objective': float, 'feasibility_rate': float}}``.
    """
    strategies = {
        'predicted': lambda m: predictor.predict(m),
        'uniform': lambda m: np.ones(len(m.variables)),
    }

    if baselines is not None:
        strategies.update(baselines)

    results = {}

    for strategy_name, weight_fn in strategies.items():
        objectives = []
        feasible_count = 0

        for model in test_models:
            weights = weight_fn(model)

            model.set_param('branching_weights', np.asarray(weights, dtype=np.float64))
            model.set_param('stopping_time', stopping_time)
            model.set_param('num_workers', num_workers)

            result = model.solve()

            objectives.append(result.objective)
            if result.feasible:
                feasible_count += 1

            # Reset weights to avoid polluting next strategy
            model.set_param('branching_weights', None)

        n_models = len(test_models)
        results[strategy_name] = {
            'mean_objective': float(np.mean(objectives)) if objectives else 0.0,
            'feasibility_rate': feasible_count / n_models if n_models > 0 else 0.0,
        }

    _print_comparison_table(results)

    return results


# ---------------------------------------------------------------------------
# Generalized weight evaluation with convergence speed metrics
# ---------------------------------------------------------------------------

def _compute_time_to_best(history, stopping_time):
    """Compute time-to-best from solve history.

    Scans history for the entry with the best (maximum) objective value and
    returns the elapsed_seconds when it was first achieved. If history is
    empty, returns ``stopping_time`` as a ceiling penalty.

    Parameters
    ----------
    history : list of tuple
        Each entry is ``(value, elapsed_seconds)`` from OptimizeResult.history.
    stopping_time : float
        Ceiling penalty returned when history is empty.

    Returns
    -------
    float
        Elapsed seconds at which the best objective value was first found.
    """
    if not history:
        return stopping_time

    best_value = max(entry[0] for entry in history)
    for value, elapsed in history:
        if value == best_value:
            return elapsed

    return stopping_time  # Should not reach here


def _print_evaluation_table(results):
    """Print a human-readable evaluation table with convergence speed columns.

    Extends the comparison table pattern with Time-to-Best and
    Speedup vs Uniform columns.

    Parameters
    ----------
    results : dict
        Strategy results with keys: mean_objective, feasibility_rate,
        mean_time_to_best, speedup_vs_uniform.
    """
    name_width = max(len(name) for name in results)
    name_width = max(name_width, len("Strategy"))

    header = (f"{'Strategy':<{name_width}}  {'Mean Objective':>15}  "
              f"{'Feasibility Rate':>17}  {'Time-to-Best':>13}  "
              f"{'Speedup vs Uniform':>19}")
    separator = "-" * len(header)

    print(separator)
    print(header)
    print(separator)

    for name, m in results.items():
        print(f"{name:<{name_width}}  {m['mean_objective']:>15.4f}  "
              f"{m['feasibility_rate']:>17.4f}  "
              f"{m['mean_time_to_best']:>13.4f}  "
              f"{m['speedup_vs_uniform']:>19.2f}x")

    print(separator)


def evaluate_weights(test_models, strategies, stopping_time=5, num_workers=2):
    """Compare weight strategies with convergence speed metrics.

    Evaluates each strategy on every test model and reports mean objective,
    feasibility rate, time-to-best, and speedup relative to a uniform baseline.
    A 'uniform' baseline is automatically added when not present in the
    strategies dict.

    Parameters
    ----------
    test_models : list of Model
        Closed Model instances to evaluate on.
    strategies : dict
        Named weight-producing callables: ``{name: callable(model) -> weights_array}``.
    stopping_time : float
        Solve time budget in seconds per evaluation solve.
    num_workers : int
        Number of solver threads per solve call.

    Returns
    -------
    dict
        Strategy results: ``{name: {'mean_objective': float, 'feasibility_rate': float,
        'mean_time_to_best': float, 'speedup_vs_uniform': float}}``.
    """
    # Build strategy dict with uniform baseline first, then user overrides
    all_strategies = {'uniform': lambda m: np.ones(len(m.variables))}
    all_strategies.update(strategies)

    results = {}

    for strategy_name, weight_fn in all_strategies.items():
        objectives = []
        feasible_count = 0
        times_to_best = []

        for model in test_models:
            weights = weight_fn(model)

            model.set_param('branching_weights', np.asarray(weights, dtype=np.float64))
            model.set_param('stopping_time', stopping_time)
            model.set_param('num_workers', num_workers)

            result = model.solve()

            objectives.append(result.objective)
            if result.feasible:
                feasible_count += 1

            ttb = _compute_time_to_best(result.history, stopping_time)
            times_to_best.append(ttb)

            # Reset weights to avoid polluting next strategy
            model.set_param('branching_weights', None)

        n_models = len(test_models)
        results[strategy_name] = {
            'mean_objective': float(np.mean(objectives)) if objectives else 0.0,
            'feasibility_rate': feasible_count / n_models if n_models > 0 else 0.0,
            'mean_time_to_best': float(np.mean(times_to_best)) if times_to_best else 0.0,
        }

    # Compute speedup ratios relative to uniform
    uniform_ttb = results['uniform']['mean_time_to_best']
    for name, metrics in results.items():
        if uniform_ttb > 0:
            if metrics['mean_time_to_best'] > 0:
                metrics['speedup_vs_uniform'] = uniform_ttb / metrics['mean_time_to_best']
            else:
                metrics['speedup_vs_uniform'] = float('inf')
        else:
            metrics['speedup_vs_uniform'] = 1.0

    _print_evaluation_table(results)

    return results


def validate_transfer(train_models, test_models, n_strategies=10,
                      stopping_time=5, num_workers=2, random_state=None):
    """Train on small models and evaluate on larger models in one call.

    Orchestrates the full transfer learning validation pipeline: collects
    training data from small instances, fits a WeightPredictor, and evaluates
    the learned weights on larger instances via evaluate_weights().

    Parameters
    ----------
    train_models : list of Model
        Small problem instances for training data collection.
    test_models : list of Model
        Larger problem instances for evaluation.
    n_strategies : int
        Number of random weight strategies per model for data collection.
    stopping_time : float
        Solve time budget in seconds (used for both collection and evaluation).
    num_workers : int
        Number of solver threads per solve call.
    random_state : int or None
        Random seed for reproducibility.

    Returns
    -------
    tuple of (dict, WeightPredictor)
        A 2-tuple where the first element is the evaluation results dict
        (same format as evaluate_weights output) and the second element is
        the fitted WeightPredictor that can be saved and reused.

    Examples
    --------
    >>> results, predictor = validate_transfer(small_models, large_models)
    >>> print(results['learned']['speedup_vs_uniform'])
    >>> predictor.save('my_predictor.joblib')
    """
    # Step 1: Collect training data from small models
    training_pairs = collect_training_data(
        train_models, n_strategies=n_strategies,
        stopping_time=stopping_time, num_workers=num_workers,
        random_state=random_state,
    )

    # Step 2: Train predictor
    predictor = WeightPredictor(random_state=random_state)
    predictor.fit(training_pairs)

    # Step 3: Evaluate on test models via evaluate_weights
    strategies = {'learned': lambda m: predictor.predict(m)}
    results = evaluate_weights(
        test_models, strategies,
        stopping_time=stopping_time, num_workers=num_workers,
    )

    return results, predictor
