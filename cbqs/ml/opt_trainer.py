"""
OPTTrainer -- End-to-end OPT training pipeline for CBQS.

Orchestrates Option C data collection, feature extraction, regressor
training, and prediction of OPT-phase branching parameters. Jointly
trains opt_sat and opt parameters, with trivially-feasible exclusion,
screening budget, and configurable training signals.

Pipeline per model:
  1. Check trivially feasible
  2. Option C data collection (screen opt_sat, pair with opt)
  3. Extract variable and instance features
  4. Build per-variable targets (opt_sat weights, opt_sat priorities,
     opt weights, opt priorities) and instance targets (6 global params)
  5. Accumulate data; refit predictor every refit_every models
  6. Log strategy, model, and refit events
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from .data_collection import OPTDataCollector
from .sat_trainer import soft_topk_target
from .features import FeatureExtractor
from .regressors import PhasePredictor, VariableRegressor, InstanceRegressor
from .signals import (
    make_signal,
    compute_normalized_auc,
    compute_composite_signal,
    compute_annealing_a,
)
from .training_log import TrainingLog


def _build_var_targets(best_opt_sat_params, best_opt_params, n_vars,
                       trivially_feasible):
    """Extract per-variable targets from best opt_sat and opt params.

    Returns ndarray of shape (n_vars, 4) with columns
    [opt_sat_weight, opt_sat_priority, opt_weight, opt_priority].
    For trivially feasible models, opt_sat columns use defaults.
    """
    if trivially_feasible or best_opt_sat_params is None:
        opt_sat_weights = np.ones(n_vars, dtype=np.float64)
        opt_sat_priorities = np.zeros(n_vars, dtype=np.float64)
    else:
        opt_sat_weights = np.array(
            best_opt_sat_params.get('opt_sat_branching_weights',
                                   [1.0] * n_vars),
            dtype=np.float64,
        )
        opt_sat_priorities = np.array(
            best_opt_sat_params.get('opt_sat_variable_priorities',
                                   list(range(n_vars))),
            dtype=np.float64,
        )

    if best_opt_params is None:
        opt_weights = np.ones(n_vars, dtype=np.float64)
        opt_priorities = np.zeros(n_vars, dtype=np.float64)
    else:
        opt_weights = np.array(
            best_opt_params.get('opt_branching_weights', [1.0] * n_vars),
            dtype=np.float64,
        )
        opt_priorities = np.array(
            best_opt_params.get('opt_variable_priorities',
                                list(range(n_vars))),
            dtype=np.float64,
        )

    # Ensure correct length
    if len(opt_sat_weights) < n_vars:
        opt_sat_weights = np.pad(opt_sat_weights,
                                 (0, n_vars - len(opt_sat_weights)),
                                 constant_values=1.0)
    if len(opt_sat_priorities) < n_vars:
        opt_sat_priorities = np.pad(opt_sat_priorities,
                                    (0, n_vars - len(opt_sat_priorities)),
                                    constant_values=0.0)
    if len(opt_weights) < n_vars:
        opt_weights = np.pad(opt_weights,
                             (0, n_vars - len(opt_weights)),
                             constant_values=1.0)
    if len(opt_priorities) < n_vars:
        opt_priorities = np.pad(opt_priorities,
                                (0, n_vars - len(opt_priorities)),
                                constant_values=0.0)

    targets = np.column_stack([
        opt_sat_weights[:n_vars],
        opt_sat_priorities[:n_vars],
        opt_weights[:n_vars],
        opt_priorities[:n_vars],
    ])
    return targets


def _build_inst_targets(best_opt_sat_params, best_opt_params,
                        trivially_feasible):
    """Extract instance-level targets from best params.

    Returns ndarray of shape (6,) with
    [opt_sat_bias, opt_sat_bf, opt_sat_bif, opt_bias, opt_bf, opt_bif].
    For trivially feasible models, opt_sat values use defaults.
    """
    if trivially_feasible or best_opt_sat_params is None:
        opt_sat_bias = 5.0
        opt_sat_bf = 1.0
        opt_sat_bif = 1.0
    else:
        opt_sat_bias = best_opt_sat_params.get('opt_sat_branching_bias', 5.0)
        opt_sat_bf = best_opt_sat_params.get('opt_sat_branching_factor', 1.0)
        opt_sat_bif = best_opt_sat_params.get('opt_sat_bias_factor', 1.0)

    if best_opt_params is None:
        opt_bias = 5.0
        opt_bf = 1.0
        opt_bif = 1.0
    else:
        opt_bias = best_opt_params.get('opt_branching_bias', 5.0)
        opt_bf = best_opt_params.get('opt_branching_factor', 1.0)
        opt_bif = best_opt_params.get('opt_bias_factor', 1.0)

    return np.array([opt_sat_bias, opt_sat_bf, opt_sat_bif,
                     opt_bias, opt_bf, opt_bif], dtype=np.float64)


class OPTTrainer:
    """Train OPT-phase branching parameters using Option C data collection.

    End-to-end pipeline: for each training model, uses Option C strategy
    to collect paired (opt_sat, opt) parameter data, extracts features,
    and periodically refits the joint predictor.

    Parameters
    ----------
    n_estimators : int
        Number of trees in each regressor ensemble.
    n_opt_sat_strategies : int
        Number of opt_sat candidates to screen per model.
    top_k : int
        Number of top opt_sat candidates to keep from screening.
    n_opt_per_candidate : int
        Number of opt parameter vectors per opt_sat candidate.
    screening_budget : float or None
        Time budget in seconds for each screening solve.
    full_budget : float or None
        Time budget in seconds for each full solve.
    signal : str
        Training signal name: 'auc' (default) or 'weighted'.
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

    def __init__(self, n_estimators=100, n_opt_sat_strategies=10,
                 top_k=3, n_opt_per_candidate=5,
                 screening_budget=None, full_budget=None,
                 signal='auc', signal_kwargs=None,
                 refit_every=5, log_path=None, random_state=None,
                 target_k=3, checkpoint_callback=None,
                 checkpoint_interval=30.0):
        self._signal_name = signal
        self._signal_kwargs = signal_kwargs or {}
        signal_fn = make_signal(signal, **self._signal_kwargs)

        self.predictor = PhasePredictor(
            mode='opt', n_estimators=n_estimators,
            random_state=random_state,
        )
        self.collector = OPTDataCollector(
            n_opt_sat=n_opt_sat_strategies,
            top_k=top_k,
            n_opt_per_candidate=n_opt_per_candidate,
            screening_budget=screening_budget,
            full_budget=full_budget,
            signal_fn=signal_fn,
            random_state=random_state,
            single_thread=False,
        )
        self.extractor = FeatureExtractor()
        self.log = TrainingLog(path=log_path)
        self.refit_every = refit_every
        self._collected = []  # list of (var_X, var_y, inst_X, inst_y, triv_feas)
        self._instance_obj_variances = []  # per-instance variance of objectives
        self._current_a = 0.5  # current annealing parameter
        self._target_k = target_k
        self._n_estimators = n_estimators
        self._random_state = random_state
        self._n_opt_sat_strategies = n_opt_sat_strategies
        self._top_k = top_k
        self._n_opt_per_candidate = n_opt_per_candidate
        self._screening_budget = screening_budget
        self._full_budget = full_budget
        self._checkpoint_callback = checkpoint_callback
        self._checkpoint_interval = checkpoint_interval

    def fit(self, models, validation_models=None):
        """Train on a list of Model instances.

        For each model:
          1. Collect Option C data (screen opt_sat, pair with opt).
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
            # Step 1: Collect data via Option C
            data = self.collector.collect(model)
            trivially_feasible = data['trivially_feasible']

            # Step 2: Log strategies
            for strat_idx, entry in enumerate(data['all_results']):
                phase = 'opt'
                if not trivially_feasible and entry.get('opt_sat_params'):
                    phase = 'opt_sat+opt' if entry.get('opt_params') else 'opt_sat'
                self.log.log_strategy(
                    model_idx=model_idx,
                    phase=phase,
                    strategy_idx=strat_idx,
                    parameters=entry.get('params', {}),
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
            best_opt_sat_params, best_opt_params, best_signal = \
                self._select_best_composite(data['all_results'])

            # Step 3: Log model summary
            self.log.log_model(
                model_idx=model_idx,
                n_strategies_tried=len(data['all_results']),
                best_signal=best_signal,
                best_parameters={
                    'opt_sat': best_opt_sat_params or {},
                    'opt': best_opt_params or {},
                },
                trivially_feasible=trivially_feasible,
            )

            # Step 4: Extract features and build targets
            n_vars = model.n
            var_features = self.extractor.extract_variable_features(model)
            inst_features = self.extractor.extract_instance_features(model)
            var_targets = _build_var_targets(
                best_opt_sat_params,
                best_opt_params,
                n_vars,
                trivially_feasible,
            )
            inst_targets = _build_inst_targets(
                best_opt_sat_params,
                best_opt_params,
                trivially_feasible,
            )

            self._collected.append(
                (var_features, var_targets, inst_features, inst_targets,
                 trivially_feasible)
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
        """Predict OPT parameters for a new model.

        Parameters
        ----------
        model : Model
            A closed Model instance.

        Returns
        -------
        dict
            Keys: opt_sat_branching_weights, opt_sat_variable_priorities,
            opt_sat_branching_bias, opt_sat_branching_factor,
            opt_sat_bias_factor, opt_branching_weights,
            opt_variable_priorities, opt_branching_bias,
            opt_branching_factor, opt_bias_factor.
        """
        var_features = self.extractor.extract_variable_features(model)
        inst_features = self.extractor.extract_instance_features(model)
        inst_features_2d = inst_features.reshape(1, -1)

        raw = self.predictor.predict(var_features, inst_features_2d)

        opt_sat_w = raw['opt_sat_weights']
        opt_sat_p = raw['opt_sat_priorities']
        opt_w = raw['opt_weights']
        opt_p = raw['opt_priorities']
        opt_sat_bias = raw['opt_sat_bias']
        opt_sat_bf = raw['opt_sat_branching_factor']
        opt_sat_bif = raw['opt_sat_bias_factor']
        opt_bias = raw['opt_bias']
        opt_bf = raw['opt_branching_factor']
        opt_bif = raw['opt_bias_factor']

        def _to_list(arr):
            return arr.tolist() if hasattr(arr, 'tolist') else list(arr)

        return {
            'opt_sat_branching_weights': _to_list(opt_sat_w),
            'opt_sat_variable_priorities': _to_list(opt_sat_p),
            'opt_sat_branching_bias': float(opt_sat_bias),
            'opt_sat_branching_factor': float(opt_sat_bf),
            'opt_sat_bias_factor': float(opt_sat_bif),
            'opt_branching_weights': _to_list(opt_w),
            'opt_variable_priorities': _to_list(opt_p),
            'opt_branching_bias': float(opt_bias),
            'opt_branching_factor': float(opt_bf),
            'opt_bias_factor': float(opt_bif),
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

        for model in new_models:
            data = self.collector.collect(model)
            trivially_feasible = data['trivially_feasible']
            n_vars = model.n
            var_features = self.extractor.extract_variable_features(model)
            inst_features = self.extractor.extract_instance_features(model)
            var_targets = _build_var_targets(
                data['best_opt_sat_params'],
                data['best_opt_params'],
                n_vars,
                trivially_feasible,
            )
            inst_targets = _build_inst_targets(
                data['best_opt_sat_params'],
                data['best_opt_params'],
                trivially_feasible,
            )
            self._collected.append(
                (var_features, var_targets, inst_features, inst_targets,
                 trivially_feasible)
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

        signal_fn = make_signal(self._signal_name, **self._signal_kwargs)
        scores = []
        for model in models:
            params = self.predict(model)
            for key, value in params.items():
                model.set_param(key, value)
            result = model.solve()
            scores.append(signal_fn(result))
        return float(np.mean(scores))

    def save(self, dir_path):
        """Save predictor, training log, and config to a directory.

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
            'n_opt_sat_strategies': self._n_opt_sat_strategies,
            'top_k': self._top_k,
            'n_opt_per_candidate': self._n_opt_per_candidate,
            'screening_budget': self._screening_budget,
            'full_budget': self._full_budget,
            'n_estimators': self._n_estimators,
            'random_state': self._random_state,
            'target_k': self._target_k,
        }
        with open(str(dir_path / 'config.json'), 'w') as f:
            json.dump(config, f, indent=2)

    @classmethod
    def load(cls, dir_path):
        """Load a saved OPTTrainer from a directory.

        Parameters
        ----------
        dir_path : str
            Directory containing predictor.joblib, training_log.json,
            and config.json.

        Returns
        -------
        OPTTrainer
            A restored trainer instance.
        """
        dir_path = Path(dir_path)

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
        trainer._signal_name = config.get('signal_name', 'auc')
        trainer._signal_kwargs = config.get('signal_kwargs', {})
        trainer.refit_every = config.get('refit_every', 5)
        trainer._n_opt_sat_strategies = config.get('n_opt_sat_strategies', 10)
        trainer._top_k = config.get('top_k', 3)
        trainer._n_opt_per_candidate = config.get('n_opt_per_candidate', 5)
        trainer._screening_budget = config.get('screening_budget', None)
        trainer._full_budget = config.get('full_budget', None)
        trainer._n_estimators = config.get('n_estimators', 100)
        trainer._random_state = config.get('random_state', None)
        trainer._target_k = config.get('target_k', 3)
        trainer._collected = []
        trainer._checkpoint_callback = None
        trainer._checkpoint_interval = config.get('checkpoint_interval', 30.0)

        signal_fn = make_signal(
            trainer._signal_name, **trainer._signal_kwargs
        )
        trainer.collector = OPTDataCollector(
            n_opt_sat=trainer._n_opt_sat_strategies,
            top_k=trainer._top_k,
            n_opt_per_candidate=trainer._n_opt_per_candidate,
            screening_budget=trainer._screening_budget,
            full_budget=trainer._full_budget,
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
        and returns the best opt_sat params, opt params, and score.

        Parameters
        ----------
        all_results : list of dict
            Each dict has 'result', and optionally 'opt_sat_params'
            and 'opt_params' keys.

        Returns
        -------
        tuple of (dict or None, dict or None, float)
            Best opt_sat params, best opt params, and composite score.
        """
        if not all_results:
            return None, None, 0.0

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

        best_score = max(composite_scores)

        # Blend opt_sat params via soft top-k
        opt_sat_configs = [entry.get('opt_sat_params') or {}
                           for entry in all_results]
        has_opt_sat = any(c for c in opt_sat_configs)
        if has_opt_sat:
            blended_opt_sat = soft_topk_target(
                opt_sat_configs, composite_scores, self._target_k)
        else:
            blended_opt_sat = None

        # Blend opt params via soft top-k
        opt_configs = [entry.get('opt_params') or {}
                       for entry in all_results]
        has_opt = any(c for c in opt_configs)
        if has_opt:
            blended_opt = soft_topk_target(
                opt_configs, composite_scores, self._target_k)
        else:
            blended_opt = None

        return (blended_opt_sat or None,
                blended_opt or None,
                best_score)

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
