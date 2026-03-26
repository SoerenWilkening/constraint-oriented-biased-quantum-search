"""ES training loop with antithetic sampling.

Implements the core evolutionary strategy (ES) trainer that replaces
SATTrainer/OPTTrainer/ExplorationTrainer. Uses antithetic perturbation
pairs for variance reduction, per-instance signal normalization, and
Adam for parameter updates.

Provides:
- ESTrainerConfig: Dataclass of training hyperparameters.
- ESTrainer: Main trainer with train() and resume() methods.
"""

import json
import logging
import os
import random
import time as time_mod
from dataclasses import dataclass, asdict

import numpy as np

from cbqs.ml.adam import Adam
from cbqs.ml.es_checkpoint import save_checkpoint, load_checkpoint
from cbqs.ml.es_evaluator import evaluate, normalize_signals  # noqa: F401
from cbqs.ml.polynomial import (
    THETA_SIZE, _LEGACY_THETA_SIZE, default_theta, migrate_theta_v1_to_v2,
    PolynomialPredictor,
)

logger = logging.getLogger(__name__)


def _fmt_time(seconds):
    """Format seconds as HH:MM:SS or MM:SS."""
    s = int(seconds)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ESTrainerConfig:
    """Training hyperparameters for the ES trainer.

    Attributes:
        lr: Adam learning rate.
        sigma: Perturbation scale (std dev of epsilon vectors).
        K: Number of antithetic perturbation pairs per step.
        batch_size: Number of training instances sampled per step.
        max_steps: Total number of training steps.
        checkpoint_interval: Steps between checkpoint saves.
        eval_time: Total solver time budget per evaluation (seconds),
            split across repeats.
        eval_repeats: Number of independent solves per evaluation.
            Each solve gets eval_time / eval_repeats seconds.
        delta_pct: Max bias delta as fraction of n/4.
        greedy_init: Whether to initialise from greedy before solving.
    """
    lr: float = 0.001
    sigma: float = 0.02
    K: int = 50
    batch_size: int = 5
    max_steps: int = 1000
    checkpoint_interval: int = 50
    eval_time: float = 5.0
    eval_repeats: int = 10
    delta_pct: float = 0.03
    greedy_init: bool = True

    def __post_init__(self):
        if self.lr <= 0:
            raise ValueError(f"lr must be positive, got {self.lr}")
        if self.sigma <= 0:
            raise ValueError(f"sigma must be positive, got {self.sigma}")
        if self.K <= 0:
            raise ValueError(f"K must be positive, got {self.K}")
        if self.batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {self.batch_size}")
        if self.max_steps < 0:
            raise ValueError(f"max_steps must be non-negative, got {self.max_steps}")


# ---------------------------------------------------------------------------
# Signal difference helper
# ---------------------------------------------------------------------------

def _signal_diff(signal_plus, signal_minus):
    """Compute scalar difference between two signals."""
    return signal_plus - signal_minus


# ---------------------------------------------------------------------------
# ESTrainer
# ---------------------------------------------------------------------------

class ESTrainer:
    """ES trainer with antithetic sampling and per-instance normalization.

    Parameters
    ----------
    config : ESTrainerConfig
        Training hyperparameters.
    theta_init : numpy.ndarray or None
        Initial coefficient vector of shape (THETA_SIZE,).
        If None, starts from zeros.
    checkpoint_dir : str or None
        Directory for saving periodic checkpoints. If None, no
        checkpoints are saved.
    log_path : str or None
        Path for a training log file (not used currently; reserved
        for future TrainingLog integration).
    """

    def __init__(self, config, theta_init=None, checkpoint_dir=None,
                 log_path=None):
        self._config = config
        self._checkpoint_dir = checkpoint_dir
        self._log_path = log_path
        self._step_log = []

        # Initialize theta
        if theta_init is not None:
            theta_init = np.asarray(theta_init, dtype=np.float64)
            if theta_init.shape != (THETA_SIZE,):
                raise ValueError(
                    f"theta_init must have shape ({THETA_SIZE},), "
                    f"got {theta_init.shape}"
                )
            self._theta = theta_init.copy()
        else:
            self._theta = default_theta()

        # Initialize optimizer
        self._optimizer = Adam(lr=config.lr)

        # Best theta tracking
        self._best_theta = None
        self._best_validation_signal = float('-inf')

    def train(self, pool, val_pool=None):
        """Run the ES training loop.

        Parameters
        ----------
        pool : list
            Training pool of Model instances (or mock objects).
        val_pool : list or None
            Optional validation pool (reserved for future use).

        Returns
        -------
        numpy.ndarray
            Trained coefficient vector of shape (THETA_SIZE,).
        """
        if not pool:
            raise ValueError("Training pool must be non-empty")

        return self._run_training_loop(pool, val_pool, start_step=0)

    def resume(self, checkpoint_path, pool=None):
        """Resume training from a checkpoint.

        Parameters
        ----------
        checkpoint_path : str
            Base path of the checkpoint (without extension).
        pool : list or None
            Training pool. If None, uses the pool from the checkpoint
            metadata (which stores paths, not model objects — so in
            practice the caller should supply the pool).

        Returns
        -------
        numpy.ndarray
            Trained coefficient vector of shape (THETA_SIZE,).
        """
        ckpt = load_checkpoint(checkpoint_path)

        # Detect legacy 344-dim checkpoint and migrate
        theta = np.asarray(ckpt['theta'], dtype=np.float64)
        migrated = False
        if theta.shape == (_LEGACY_THETA_SIZE,):
            logger.info(
                "Migrating legacy %d-dim checkpoint to %d-dim",
                _LEGACY_THETA_SIZE, THETA_SIZE,
            )
            theta = migrate_theta_v1_to_v2(theta)
            migrated = True
        self._theta = theta

        # Restore optimizer state (reset if dimensions changed)
        self._optimizer = Adam(lr=self._config.lr)
        opt_state = ckpt['optimizer_state']
        if migrated or (opt_state['m'] is not None
                        and opt_state['m'].shape != (THETA_SIZE,)):
            logger.info(
                "Resetting Adam state (parameter dimensions changed)"
            )
            # Leave optimizer in fresh state; moments will initialize on
            # the first call to step().
        else:
            self._optimizer.load_state_dict(opt_state)

        # Restore best theta (migrate if legacy)
        best = ckpt.get('best_theta')
        if best is not None:
            best = np.asarray(best, dtype=np.float64)
            if best.shape == (_LEGACY_THETA_SIZE,):
                best = migrate_theta_v1_to_v2(best)
        self._best_theta = best
        self._best_validation_signal = ckpt.get('best_validation_signal',
                                                  float('-inf'))

        start_step = ckpt['step'] + 1

        if pool is None:
            raise ValueError(
                "Training pool must be provided for resume "
                "(checkpoint stores paths, not model objects)"
            )

        return self._run_training_loop(pool, val_pool=None,
                                        start_step=start_step)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_training_loop(self, pool, val_pool, start_step):
        """Core training loop shared by train() and resume().

        Parameters
        ----------
        pool : list
            Training pool.
        val_pool : list or None
            Validation pool.
        start_step : int
            Step number to start from.

        Returns
        -------
        numpy.ndarray
            Final theta vector.
        """
        cfg = self._config
        train_start_time = time_mod.monotonic()
        total_steps = cfg.max_steps - start_step

        for step in range(start_step, cfg.max_steps):
            step_start_time = time_mod.monotonic()

            # Checkpoint at the start of checkpoint intervals
            if step % cfg.checkpoint_interval == 0:
                self._save_checkpoint(step, pool)

            # Sample batch
            if len(pool) >= cfg.batch_size:
                batch = random.sample(pool, cfg.batch_size)
            else:
                batch = random.choices(pool, k=cfg.batch_size)

            # Generate K perturbation vectors
            epsilons = [np.random.randn(THETA_SIZE)
                        for _ in range(cfg.K)]

            # Compute gradient estimate with per-instance normalization
            gradient = np.zeros(THETA_SIZE, dtype=np.float64)

            # Collect signals from perturbations for monitoring
            all_objectives = []

            for instance in batch:
                # Compute signal diffs for all K perturbations
                diffs = np.empty(cfg.K, dtype=np.float64)
                for k, eps in enumerate(epsilons):
                    theta_plus = self._theta + cfg.sigma * eps
                    theta_minus = self._theta - cfg.sigma * eps
                    # Use the same seed for the antithetic pair so that
                    # signal differences reflect only the theta change,
                    # not solver randomness.
                    pair_seed = random.randint(0, 2**31 - 1)
                    sig_plus = evaluate(theta_plus, instance, cfg.eval_time, seed=pair_seed, repeats=cfg.eval_repeats, greedy_init=cfg.greedy_init)
                    sig_minus = evaluate(theta_minus, instance, cfg.eval_time, seed=pair_seed, repeats=cfg.eval_repeats, greedy_init=cfg.greedy_init)
                    diffs[k] = _signal_diff(sig_plus, sig_minus)

                    all_objectives.append(sig_plus)
                    all_objectives.append(sig_minus)

                # Per-instance normalization
                norm_diffs = normalize_signals(diffs)

                # Accumulate gradient
                for k, eps in enumerate(epsilons):
                    gradient += norm_diffs[k] * eps

            # Derive monitoring signal from perturbation data
            mean_obj = float(np.mean(all_objectives))

            # Scale gradient
            gradient /= (2.0 * cfg.sigma * cfg.K * cfg.batch_size)

            # Adam update
            self._theta = self._optimizer.step(self._theta, gradient)

            # Extract current instance-level params for monitoring
            from cbqs.ml.polynomial import (
                unpack_theta, N_INST_TERMS,
            )
            _, W_inst = unpack_theta(self._theta)
            # Intercept-only approximation (feature-independent baseline)
            bias_delta_intercept = float(W_inst[0, 0])
            branching_factor_intercept = float(max(0.0, W_inst[1, 0]))
            bias_factor_intercept = float(max(0.0, W_inst[2, 0]))

            # Timing
            step_end_time = time_mod.monotonic()
            step_duration = step_end_time - step_start_time
            elapsed = step_end_time - train_start_time
            steps_done = step - start_step + 1
            steps_remaining = total_steps - steps_done
            avg_step_time = elapsed / steps_done
            eta = avg_step_time * steps_remaining
            pct = 100.0 * steps_done / total_steps

            # Log step
            grad_norm = float(np.linalg.norm(gradient))
            self._step_log.append({
                'step': step,
                'grad_norm': grad_norm,
                'theta_norm': float(np.linalg.norm(self._theta)),
                'mean_objective': mean_obj,
                'bias_factor': bias_factor_intercept,
                'branching_factor': branching_factor_intercept,
                'bias_delta': bias_delta_intercept,
                'step_time': round(step_duration, 2),
                'elapsed': round(elapsed, 2),
                'eta': round(eta, 2),
            })
            logger.info(
                "step=%d  obj=%.4f  bias_f=%.4f  branch_f=%.4f  "
                "bias_d=%.4f  grad=%.6f",
                step, mean_obj, bias_factor_intercept,
                branching_factor_intercept, bias_delta_intercept, grad_norm,
            )

            # Progress bar
            bar_width = 30
            filled = int(bar_width * pct / 100.0)
            bar = '=' * filled + '>' + '.' * (bar_width - filled - 1)
            elapsed_str = _fmt_time(elapsed)
            eta_str = _fmt_time(eta)
            print(
                f"\r[{bar}] {pct:5.1f}% | "
                f"step {step}/{cfg.max_steps} | "
                f"{elapsed_str} elapsed, {eta_str} remaining | "
                f"obj={mean_obj:.0f}",
                end='', flush=True,
            )

            # Save intermediate predictor after each step
            if self._checkpoint_dir is not None:
                pred = PolynomialPredictor(self._theta,
                                           delta_pct=cfg.delta_pct)
                pred.save(os.path.join(self._checkpoint_dir,
                                       f"predictor_step_{step:06d}.npz"))

            # Append to log file for live monitoring (tail -f)
            if self._log_path:
                with open(self._log_path, 'a') as f:
                    f.write(json.dumps(self._step_log[-1]) + '\n')

        print()  # newline after progress bar
        return self._theta

    def _save_checkpoint(self, step, pool):
        """Save a checkpoint if checkpoint_dir is set."""
        if self._checkpoint_dir is None:
            return

        path = os.path.join(self._checkpoint_dir,
                            f"step_{step:06d}")

        # Build pool paths list (use name attribute or str representation)
        pool_paths = []
        for m in pool:
            if hasattr(m, 'path'):
                pool_paths.append(str(m.path))
            elif hasattr(m, 'name'):
                pool_paths.append(str(m.name))
            else:
                pool_paths.append(str(m))

        save_checkpoint(
            path=path,
            theta=self._theta,
            optimizer_state=self._optimizer.state_dict(),
            training_pool=pool_paths,
            step=step,
            config=asdict(self._config),
            log_path=self._log_path or '',
            best_theta=self._best_theta,
            best_validation_signal=self._best_validation_signal,
        )
        logger.info("Saved checkpoint at step %d to %s", step, path)
