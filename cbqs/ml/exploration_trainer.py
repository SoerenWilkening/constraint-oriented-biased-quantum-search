"""
ExplorationTrainer -- Exploration-focused training pipeline for CBQS.

Learns small refinements to default solver parameters (n/4 bias, uniform
weights) that preserve exploration strength while adding instance-specific
variable preference.

Constrained parameter space:
  - bias_factor = 1.0 (fixed)
  - delta_bias in [-n/100, n/100], applied as n/4 + delta_bias
  - weights in [-1, 1]
  - branching_factor in [-1, 1]

Training signal: final objective (primary), time-to-best (tiebreaker).
Uses PhasePredictor regressors, constrained sampling from M22.

Pipeline per model:
  1. Collect training data (N constrained strategies, pick best)
  2. Extract variable and instance features
  3. Build per-variable targets (weights, priorities) and instance
     targets (bias, branching_factor, bias_factor) from best params
  4. Accumulate data; refit predictor every refit_every models
  5. Log strategy, model, and refit events
  6. Checkpoint callback every ~30s
"""

import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from .data_collection import (
    constrained_sat_params,
    _evaluate_strategy,
)
from .features import FeatureExtractor
from .regressors import PhasePredictor
from .sat_trainer import soft_topk_target
from .signals import make_exploration_signal
from .training_log import TrainingLog


def _build_var_targets(best_params, n_vars):
    """Extract per-variable targets (weights, priorities) from best params.

    Returns ndarray of shape (n_vars, 2) with columns [weight, priority].
    """
    weights = best_params.get('sat_branching_weights', [0.0] * n_vars)
    priorities = best_params.get('sat_variable_priorities', list(range(n_vars)))
    weights = np.array(weights, dtype=np.float64)
    priorities = np.array(priorities, dtype=np.float64)

    if len(weights) < n_vars:
        weights = np.pad(weights, (0, n_vars - len(weights)),
                         constant_values=0.0)
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
    bf = best_params.get('sat_branching_factor', 0.0)
    bif = best_params.get('sat_bias_factor', 1.0)
    return np.array([bias, bf, bif], dtype=np.float64)


class ExplorationTrainer:
    """Train exploration-focused parameters (Set B).

    Learns small refinements to the default solver parameters
    (n/4 bias, uniform weights) that preserve exploration strength
    while adding instance-specific variable preference.

    Constrained parameter space:
    - bias_factor = 1.0 (fixed)
    - delta_bias in [-n/100, n/100], applied as n/4 + delta_bias
    - weights in [-1, 1]
    - branching_factor in [-1, 1]

    Training signal: final objective (primary), time-to-best (tiebreaker).
    """

    def __init__(self, n_estimators=100, n_strategies=10,
                 time_budget=None, refit_every=5,
                 log_path=None, random_state=None,
                 target_k=3, delta_bias_range=None,
                 checkpoint_callback=None,
                 checkpoint_interval=30.0):
        """
        Args:
            n_estimators: Number of trees in each regressor ensemble.
            n_strategies: Number of constrained parameter configs to try.
            time_budget: Per-solve time budget in seconds.
            refit_every: Refit the predictor every this many models.
            log_path: Path for the training log file.
            random_state: Random seed for reproducibility.
            target_k: Number of top configs for soft target selection.
            delta_bias_range: tuple (lo, hi) as fraction of n.
                Default: (-1/100, 1/100), meaning n/4 +/- n/100.
            checkpoint_callback: callable(trainer, elapsed_seconds) or None.
                Called every checkpoint_interval seconds during fit().
            checkpoint_interval: seconds between checkpoint calls (default 30).
        """
        self._signal_fn = make_exploration_signal()
        self._delta_bias_range = delta_bias_range or (-1.0 / 100, 1.0 / 100)

        self.predictor = PhasePredictor(
            mode='sat', n_estimators=n_estimators,
            random_state=random_state,
        )
        self._rng = np.random.default_rng(random_state)
        self.extractor = FeatureExtractor()
        self.log = TrainingLog(path=log_path)
        self.refit_every = refit_every
        self._collected = []  # list of (var_X, var_y, inst_X, inst_y)
        self._n_estimators = n_estimators
        self._random_state = random_state
        self._target_k = target_k
        self._n_strategies = n_strategies
        self._time_budget = time_budget
        self._checkpoint_callback = checkpoint_callback
        self._checkpoint_interval = checkpoint_interval

    def fit(self, models, validation_models=None):
        """Train on models. Calls checkpoint_callback every ~30s.

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
            n_vars = model.n

            # Step 1: Collect constrained strategies
            all_results = []
            for strat_idx in range(self._n_strategies):
                params = constrained_sat_params(n_vars, self._rng)
                entry = _evaluate_strategy(
                    model, params, self._signal_fn, self._time_budget,
                )
                all_results.append(entry)

            # Step 2: Log strategies
            for strat_idx, entry in enumerate(all_results):
                self.log.log_strategy(
                    model_idx=model_idx,
                    phase='exploration',
                    strategy_idx=strat_idx,
                    parameters=entry['params'],
                    result={
                        'objective': entry['result'].objective,
                        'feasible': entry['result'].feasible,
                        'time': entry['result'].solve_time,
                    },
                )

            # Step 3: Select best via soft top-k
            scores = [entry['signal'] for entry in all_results]
            configs = [entry['params'] for entry in all_results]
            best_score = max(scores)
            best_params = soft_topk_target(configs, scores, self._target_k)

            # Step 4: Log model summary
            self.log.log_model(
                model_idx=model_idx,
                n_strategies_tried=len(all_results),
                best_signal=best_score,
                best_parameters=best_params,
                trivially_feasible=False,
            )

            # Step 5: Extract features and build targets
            var_features = self.extractor.extract_variable_features(model)
            inst_features = self.extractor.extract_instance_features(model)
            var_targets = _build_var_targets(best_params, n_vars)
            inst_targets = _build_inst_targets(best_params)

            self._collected.append(
                (var_features, var_targets, inst_features, inst_targets)
            )

            # Step 6: Periodic refit
            n_collected = len(self._collected)
            if n_collected > 0 and n_collected % self.refit_every == 0:
                self._refit(validation_models)

            # Step 7: Checkpoint callback
            if self._checkpoint_callback is not None:
                now = time.monotonic()
                elapsed_since_checkpoint = now - last_checkpoint
                if elapsed_since_checkpoint >= self._checkpoint_interval:
                    elapsed_total = now - fit_start
                    self._checkpoint_callback(self, elapsed_total)
                    last_checkpoint = now

        # Final refit if not yet fitted or not aligned with refit_every
        if not self.predictor._is_fitted and self._collected:
            self._refit(validation_models)

    def predict(self, model):
        """Predict exploration parameters. Clips to constrained bounds.

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
        n_vars = model.n
        var_features = self.extractor.extract_variable_features(model)
        inst_features = self.extractor.extract_instance_features(model)
        inst_features_2d = inst_features.reshape(1, -1)

        raw = self.predictor.predict(var_features, inst_features_2d)

        weights = raw['weights']
        priorities = raw['priorities']
        bias = raw['bias']
        bf = raw['branching_factor']

        # Clip to constrained bounds
        weights = np.clip(weights, -1.0, 1.0)
        bf = float(np.clip(bf, -1.0, 1.0))

        # Clip bias to n/4 +/- delta_bias_range
        delta_lo = self._delta_bias_range[0] * n_vars
        delta_hi = self._delta_bias_range[1] * n_vars
        bias = float(np.clip(bias, n_vars / 4.0 + delta_lo,
                             n_vars / 4.0 + delta_hi))

        return {
            'sat_branching_weights': weights.tolist() if hasattr(weights, 'tolist') else list(weights),
            'sat_variable_priorities': priorities.tolist() if hasattr(priorities, 'tolist') else list(priorities),
            'sat_branching_bias': bias,
            'sat_branching_factor': bf,
            'sat_bias_factor': 1.0,
        }

    def save(self, dir_path):
        """Save predictor, log, config, and collected data.

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
            'refit_every': self.refit_every,
            'n_strategies': self._n_strategies,
            'n_estimators': self._n_estimators,
            'time_budget': self._time_budget,
            'random_state': self._random_state,
            'target_k': self._target_k,
            'delta_bias_range': list(self._delta_bias_range),
            'checkpoint_interval': self._checkpoint_interval,
        }
        with open(str(dir_path / 'config.json'), 'w') as f:
            json.dump(config, f, indent=2)

        # Save collected data
        self._save_collected(str(dir_path / 'collected_data.npz'))

    @classmethod
    def load(cls, dir_path):
        """Load a saved ExplorationTrainer from a directory.

        Parameters
        ----------
        dir_path : str
            Directory containing predictor.joblib, training_log.json,
            config.json, and collected_data.npz.

        Returns
        -------
        ExplorationTrainer
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
        trainer._signal_fn = make_exploration_signal()
        trainer.refit_every = config.get('refit_every', 5)
        trainer._n_strategies = config.get('n_strategies', 10)
        trainer._n_estimators = config.get('n_estimators', 100)
        trainer._time_budget = config.get('time_budget', None)
        trainer._random_state = config.get('random_state', None)
        trainer._target_k = config.get('target_k', 3)
        delta_range = config.get('delta_bias_range', [-1.0 / 100, 1.0 / 100])
        trainer._delta_bias_range = tuple(delta_range)
        trainer._checkpoint_interval = config.get('checkpoint_interval', 30.0)
        trainer._checkpoint_callback = None
        trainer._rng = np.random.default_rng(trainer._random_state)
        trainer._collected = []

        # Restore collected data
        data_path = dir_path / 'collected_data.npz'
        if data_path.exists():
            trainer._load_collected(str(data_path))

        return trainer

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refit(self, validation_models=None):
        """Refit the predictor on all accumulated data."""
        var_X_list = [c[0] for c in self._collected]
        var_y_list = [c[1] for c in self._collected]
        inst_X = np.vstack([c[2].reshape(1, -1) for c in self._collected])
        inst_y = np.vstack([c[3].reshape(1, -1) for c in self._collected])

        self.predictor.fit(var_X_list, var_y_list, inst_X, inst_y)

        val_score = 0.0
        if validation_models:
            val_score = self._validate(validation_models)

        self.log.log_refit(
            n_training_models=len(self._collected),
            validation_score=val_score,
            timestamp=datetime.now().isoformat(),
        )

    def _validate(self, models):
        """Evaluate predictor quality on a validation set."""
        if not models:
            return 0.0

        scores = []
        for model in models:
            params = self.predict(model)
            entry = _evaluate_strategy(model, params, self._signal_fn)
            scores.append(entry['signal'])
        return float(np.mean(scores))

    def _save_collected(self, path):
        """Save collected training data to a .npz file."""
        n = len(self._collected)
        arrays = {'n_collected': np.array(n)}

        for i, (var_X, var_y, inst_X, inst_y) in enumerate(self._collected):
            arrays[f'var_X_{i}'] = var_X
            arrays[f'var_y_{i}'] = var_y
            arrays[f'inst_X_{i}'] = inst_X
            arrays[f'inst_y_{i}'] = inst_y

        np.savez(path, **arrays)

    def _load_collected(self, path):
        """Load collected training data from a .npz file."""
        data = np.load(path, allow_pickle=True)
        n = int(data['n_collected'])
        self._collected = []

        for i in range(n):
            var_X = data[f'var_X_{i}']
            var_y = data[f'var_y_{i}']
            inst_X = data[f'inst_X_{i}']
            inst_y = data[f'inst_y_{i}']
            self._collected.append((var_X, var_y, inst_X, inst_y))
