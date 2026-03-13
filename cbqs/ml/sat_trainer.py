"""
SATTrainer -- End-to-end SAT training pipeline for CBQS.

Orchestrates data collection, feature extraction, regressor training,
and prediction of SAT-phase branching parameters. Supports incremental
training via warm_start, structured logging, and save/load of trained
artifacts.

Pipeline per model:
  1. Collect training data (N random strategies, pick best)
  2. Extract variable and instance features
  3. Build per-variable targets (weights, priorities) and instance
     targets (bias, branching_factor, bias_factor) from best params
  4. Accumulate data; refit predictor every refit_every models
  5. Log strategy, model, and refit events
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from .data_collection import SATDataCollector
from .features import FeatureExtractor
from .regressors import PhasePredictor, VariableRegressor, InstanceRegressor
from .signals import (
    make_signal,
    compute_normalized_auc,
    compute_composite_signal,
    compute_annealing_a,
)
from .training_log import TrainingLog


def soft_topk_target(configs, scores, k):
    """Compute weighted-average target from top-k configs by score.

    Selects the top-k parameter configurations ranked by score, then
    returns a weighted average of their parameters, with weights
    proportional to the scores.

    Args:
        configs: list of parameter dicts. Values may be scalars or lists.
        scores: list of float scores (higher = better), one per config.
        k: number of top configs to use. If k > len(configs), all are used.

    Returns:
        dict: weighted average of top-k parameter configs,
              weights proportional to scores.
    """
    n = len(configs)
    if n == 0:
        return {}

    k = min(k, n)

    # Find top-k indices by score
    indexed = sorted(range(n), key=lambda i: scores[i], reverse=True)
    topk_idx = indexed[:k]

    # Compute weights proportional to scores
    topk_scores = [scores[i] for i in topk_idx]
    total = sum(topk_scores)
    if total == 0:
        weights = [1.0 / k] * k
    else:
        weights = [s / total for s in topk_scores]

    # Weighted average of parameters
    result = {}
    keys = configs[topk_idx[0]].keys()
    for key in keys:
        vals = [configs[topk_idx[j]][key] for j in range(k)]
        if isinstance(vals[0], (list, np.ndarray)):
            arr = np.array(vals, dtype=np.float64)
            wavg = np.zeros(arr.shape[1], dtype=np.float64)
            for j in range(k):
                wavg += weights[j] * arr[j]
            result[key] = wavg.tolist()
        else:
            wavg = sum(weights[j] * float(vals[j]) for j in range(k))
            result[key] = wavg

    return result


def _constraint_count_signal(result):
    """Default SAT signal: use objective value as proxy for constraint count."""
    return result.objective


def _make_signal_fn(name, **kwargs):
    """Create a signal function by name, with 'constraint_count' as special case."""
    if name == 'constraint_count':
        return _constraint_count_signal
    return make_signal(name, **kwargs)


def _build_var_targets(best_params, n_vars):
    """Extract per-variable targets (weights, priorities) from best params.

    Returns ndarray of shape (n_vars, 2) with columns [weight, priority].
    """
    weights = best_params.get('sat_branching_weights', [1.0] * n_vars)
    priorities = best_params.get('sat_variable_priorities', list(range(n_vars)))
    weights = np.array(weights, dtype=np.float64)
    priorities = np.array(priorities, dtype=np.float64)

    # Ensure correct length
    if len(weights) < n_vars:
        weights = np.pad(weights, (0, n_vars - len(weights)),
                         constant_values=1.0)
    if len(priorities) < n_vars:
        priorities = np.pad(priorities, (0, n_vars - len(priorities)),
                            constant_values=0.0)

    targets = np.column_stack([weights[:n_vars], priorities[:n_vars]])
    return targets


def _build_inst_targets(best_params):
    """Extract instance-level targets from best params.

    Returns ndarray of shape (3,) with [bias, branching_factor, bias_factor].
    """
    bias = best_params.get('sat_branching_bias', 5.0)
    bf = best_params.get('sat_branching_factor', 1.0)
    bif = best_params.get('sat_bias_factor', 1.0)
    return np.array([bias, bf, bif], dtype=np.float64)


class SATTrainer:
    """Train SAT-phase branching parameters from problem instances.

    End-to-end pipeline: for each training model, samples random SAT
    parameter configurations, picks the best by training signal, extracts
    features, and periodically refits the predictor.

    Parameters
    ----------
    n_estimators : int
        Number of trees in each regressor ensemble.
    n_strategies : int
        Number of random parameter configurations to try per model.
    time_budget : float or None
        Per-solve time budget in seconds.
    signal : str
        Training signal name: 'constraint_count' (default) or 'auc'.
    signal_kwargs : dict or None
        Extra arguments for the signal factory.
    refit_every : int
        Refit the predictor every this many models.
    log_path : str or None
        Path for the training log file.
    random_state : int or None
        Random seed for reproducibility.
    target_k : int
        Number of top configs for soft target selection (default 3).
    """

    def __init__(self, n_estimators=100, n_strategies=10,
                 time_budget=None, signal='constraint_count',
                 signal_kwargs=None, refit_every=5,
                 log_path=None, random_state=None, target_k=3,
                 checkpoint_callback=None, checkpoint_interval=30.0):
        self._signal_name = signal
        self._signal_kwargs = signal_kwargs or {}
        signal_fn = _make_signal_fn(signal, **self._signal_kwargs)

        self.predictor = PhasePredictor(
            mode='sat', n_estimators=n_estimators,
            random_state=random_state,
        )
        self.collector = SATDataCollector(
            n_strategies=n_strategies,
            time_budget=time_budget,
            signal_fn=signal_fn,
            random_state=random_state,
            single_thread=False,
        )
        self.extractor = FeatureExtractor()
        self.log = TrainingLog(path=log_path)
        self.refit_every = refit_every
        self._collected = []  # list of (var_X, var_y, inst_X, inst_y)
        self._instance_obj_variances = []  # per-instance variance of objectives
        self._current_a = 0.5  # current annealing parameter
        self._n_estimators = n_estimators
        self._random_state = random_state
        self._target_k = target_k
        self._n_strategies = n_strategies
        self._time_budget = time_budget
        self._checkpoint_callback = checkpoint_callback
        self._checkpoint_interval = checkpoint_interval

    def fit(self, models, validation_models=None):
        """Train on a list of Model instances.

        For each model:
          1. Collect training data (N random strategies, pick best).
          2. Extract variable and instance features.
          3. Log strategy and model events.
          4. Every refit_every models: refit predictor, log refit event.

        Parameters
        ----------
        models : list
            List of closed Model instances to train on.
        validation_models : list or None
            Optional validation models for scoring at refit time.
        """
        fit_start = time.monotonic()
        last_checkpoint = fit_start

        for model_idx, model in enumerate(models):
            # Step 1: Collect data
            data = self.collector.collect(model)

            # Step 2: Log strategies
            for strat_idx, entry in enumerate(data['all_results']):
                self.log.log_strategy(
                    model_idx=model_idx,
                    phase='sat',
                    strategy_idx=strat_idx,
                    parameters=entry['params'],
                    result={
                        'objective': entry['result'].objective,
                        'feasible': entry['result'].feasible,
                        'time': entry['result'].solve_time,
                    },
                )

            # Track per-instance objective variance for annealing
            objectives = [entry['result'].objective
                          for entry in data['all_results']]
            if len(objectives) > 1:
                obj_var = float(np.var(objectives))
            else:
                obj_var = 0.0
            self._instance_obj_variances.append(obj_var)

            # Re-score strategies using composite signal
            best_params, best_signal = self._select_best_composite(
                data['all_results'])

            # Step 3: Log model summary
            self.log.log_model(
                model_idx=model_idx,
                n_strategies_tried=len(data['all_results']),
                best_signal=best_signal,
                best_parameters=best_params,
                trivially_feasible=False,
            )

            # Step 4: Extract features and build targets
            n_vars = model.n
            var_features = self.extractor.extract_variable_features(model)
            inst_features = self.extractor.extract_instance_features(model)
            var_targets = _build_var_targets(best_params, n_vars)
            inst_targets = _build_inst_targets(best_params)

            self._collected.append(
                (var_features, var_targets, inst_features, inst_targets)
            )

            # Step 5: Periodic refit
            n_collected = len(self._collected)
            if n_collected > 0 and n_collected % self.refit_every == 0:
                self._refit(validation_models)

            # Step 6: Checkpoint callback
            if self._checkpoint_callback is not None:
                now = time.monotonic()
                if now - last_checkpoint >= self._checkpoint_interval:
                    elapsed_total = now - fit_start
                    self._checkpoint_callback(self, elapsed_total)
                    last_checkpoint = now

        # Final refit if not yet fitted or not aligned with refit_every
        if not self.predictor._is_fitted and self._collected:
            self._refit(validation_models)

    def predict(self, model):
        """Predict SAT parameters for a new model.

        Parameters
        ----------
        model : Model
            A closed Model instance.

        Returns
        -------
        dict
            Keys: sat_branching_weights, sat_variable_priorities,
            sat_branching_bias, sat_branching_factor, sat_bias_factor.
        """
        var_features = self.extractor.extract_variable_features(model)
        inst_features = self.extractor.extract_instance_features(model)
        inst_features_2d = inst_features.reshape(1, -1)

        raw = self.predictor.predict(var_features, inst_features_2d)

        weights = raw['weights']
        priorities = raw['priorities']
        bias = raw['bias']
        bf = raw['branching_factor']
        bif = raw['bias_factor']

        return {
            'sat_branching_weights': weights.tolist() if hasattr(weights, 'tolist') else list(weights),
            'sat_variable_priorities': priorities.tolist() if hasattr(priorities, 'tolist') else list(priorities),
            'sat_branching_bias': float(bias),
            'sat_branching_factor': float(bf),
            'sat_bias_factor': float(bif),
        }

    def warm_start(self, new_models, n_new_trees=50):
        """Incrementally train on new models without full refit.

        Collects data from new models, adds trees, and refits the
        predictor on all accumulated data.

        Parameters
        ----------
        new_models : list
            New Model instances to add to training.
        n_new_trees : int
            Number of new trees to add to each ensemble.
        """
        trees_before = self.predictor.var_regressor.model.n_estimators

        # Collect data from new models
        for model in new_models:
            data = self.collector.collect(model)
            n_vars = model.n
            var_features = self.extractor.extract_variable_features(model)
            inst_features = self.extractor.extract_instance_features(model)
            var_targets = _build_var_targets(data['best_params'], n_vars)
            inst_targets = _build_inst_targets(data['best_params'])
            self._collected.append(
                (var_features, var_targets, inst_features, inst_targets)
            )

        # Warm-start refit
        var_X_list = [c[0] for c in self._collected]
        var_y_list = [c[1] for c in self._collected]
        inst_X = np.vstack([c[2].reshape(1, -1) for c in self._collected])
        inst_y = np.vstack([c[3].reshape(1, -1) for c in self._collected])

        self.predictor.warm_start_fit(
            var_X_list, var_y_list, inst_X, inst_y,
            n_new_trees=n_new_trees,
        )

        trees_after = self.predictor.var_regressor.model.n_estimators

        # Log retrain event
        self.log.log_retrain(
            episode=len([e for e in self.log._events
                         if hasattr(e, 'episode')]) + 1,
            new_instances=[str(i) for i in range(len(new_models))],
            total_instances=len(self._collected),
            trees_before=trees_before,
            trees_after=trees_after,
            score_before=0.0,
            score_after=0.0,
            timestamp=datetime.now().isoformat(),
        )

    def validate(self, models):
        """Evaluate predictor quality on a validation set.

        For each validation model, predicts parameters and scores
        the result. Returns mean signal across models.

        Parameters
        ----------
        models : list
            Validation Model instances.

        Returns
        -------
        float
            Mean validation score.
        """
        if not models:
            return 0.0

        signal_fn = _make_signal_fn(self._signal_name, **self._signal_kwargs)
        scores = []
        for model in models:
            params = self.predict(model)
            for key, value in params.items():
                model.set_param(key, value)
            result = model.solve()
            scores.append(signal_fn(result))
        return float(np.mean(scores))

    def save(self, dir_path):
        """Save predictor and training log to a directory.

        Creates predictor.joblib and training_log.json in dir_path.

        Parameters
        ----------
        dir_path : str
            Directory path to save artifacts.
        """
        dir_path = Path(dir_path)
        dir_path.mkdir(parents=True, exist_ok=True)

        self.predictor.save(str(dir_path / 'predictor.joblib'))
        self.log.save(str(dir_path / 'training_log.json'))

        config = {
            'signal_name': self._signal_name,
            'signal_kwargs': self._signal_kwargs,
            'refit_every': self.refit_every,
            'n_strategies': self._n_strategies,
            'n_estimators': self._n_estimators,
            'time_budget': self._time_budget,
            'random_state': self._random_state,
            'target_k': self._target_k,
        }
        with open(str(dir_path / 'config.json'), 'w') as f:
            json.dump(config, f, indent=2)

    @classmethod
    def load(cls, dir_path):
        """Load a saved SATTrainer from a directory.

        Parameters
        ----------
        dir_path : str
            Directory containing predictor.joblib and training_log.json.

        Returns
        -------
        SATTrainer
            A restored trainer instance.
        """
        dir_path = Path(dir_path)

        # Load config metadata
        config_path = dir_path / 'config.json'
        if config_path.exists():
            with open(str(config_path), 'r') as f:
                config = json.load(f)
        else:
            config = {}

        trainer = cls.__new__(cls)
        trainer.predictor = PhasePredictor.load(
            str(dir_path / 'predictor.joblib')
        )
        trainer.log = TrainingLog()
        trainer.log.load(str(dir_path / 'training_log.json'))
        trainer.extractor = FeatureExtractor()
        trainer._signal_name = config.get('signal_name', 'constraint_count')
        trainer._signal_kwargs = config.get('signal_kwargs', {})
        trainer.refit_every = config.get('refit_every', 5)
        trainer._n_strategies = config.get('n_strategies', 10)
        trainer._n_estimators = config.get('n_estimators', 100)
        trainer._time_budget = config.get('time_budget', None)
        trainer._random_state = config.get('random_state', None)
        trainer._target_k = config.get('target_k', 3)
        trainer._collected = []
        trainer._checkpoint_callback = None
        trainer._checkpoint_interval = config.get('checkpoint_interval', 30.0)

        signal_fn = _make_signal_fn(
            trainer._signal_name, **trainer._signal_kwargs
        )
        trainer.collector = SATDataCollector(
            n_strategies=trainer._n_strategies,
            time_budget=trainer._time_budget,
            signal_fn=signal_fn,
            random_state=trainer._random_state,
            single_thread=False,
        )

        return trainer

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _select_best_composite(self, all_results):
        """Re-score all strategy results using composite signal.

        Computes normalized AUC and composite signal for each result,
        and returns the best params and score.

        Parameters
        ----------
        all_results : list of dict
            Each dict has 'params' and 'result' keys.

        Returns
        -------
        tuple of (dict, float)
            Best params and best composite signal score.
        """
        if not all_results:
            return {}, 0.0

        # Gather objectives and determine normalization range
        objectives = [entry['result'].objective for entry in all_results]
        best_obj = max(objectives)
        worst_obj = min(objectives)

        composite_scores = []
        for entry in all_results:
            result = entry['result']
            total_time = result.solve_time / 1000.0  # ms to seconds

            norm_auc = compute_normalized_auc(
                result.history, total_time, best_obj, worst_obj)

            if best_obj != worst_obj:
                best_norm_obj = (result.objective - worst_obj) / (best_obj - worst_obj)
            else:
                best_norm_obj = 0.0

            score = compute_composite_signal(
                norm_auc, best_norm_obj, self._current_a)
            composite_scores.append(score)

        configs = [entry['params'] for entry in all_results]
        best_score = max(composite_scores)
        blended = soft_topk_target(configs, composite_scores, self._target_k)
        return blended, best_score

    def _refit(self, validation_models=None):
        """Refit the predictor on all accumulated data."""
        # Compute annealing a from instance objective variances
        if self._instance_obj_variances:
            self._current_a = compute_annealing_a(
                self._instance_obj_variances)

        var_X_list = [c[0] for c in self._collected]
        var_y_list = [c[1] for c in self._collected]
        inst_X = np.vstack([c[2].reshape(1, -1) for c in self._collected])
        inst_y = np.vstack([c[3].reshape(1, -1) for c in self._collected])

        self.predictor.fit(var_X_list, var_y_list, inst_X, inst_y)

        val_score = 0.0
        if validation_models:
            val_score = self.validate(validation_models)

        self.log.log_refit(
            n_training_models=len(self._collected),
            validation_score=val_score,
            timestamp=datetime.now().isoformat(),
            annealing_a=self._current_a,
        )
