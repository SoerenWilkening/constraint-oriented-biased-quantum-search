"""ES training loop with antithetic sampling.

Implements the core evolutionary strategy (ES) trainer that replaces
SATTrainer/OPTTrainer/ExplorationTrainer. Uses antithetic perturbation
pairs for variance reduction, per-instance signal normalization, and
Adam for parameter updates.

Provides:
- ESTrainerConfig: Dataclass of training hyperparameters.
- ESTrainer: Main trainer with train() and resume() methods.
"""

import logging
import os
import random
from dataclasses import dataclass, asdict

import numpy as np

from cbqs.ml.adam import Adam
from cbqs.ml.es_checkpoint import save_checkpoint, load_checkpoint
from cbqs.ml.es_evaluator import evaluate, normalize_signals
from cbqs.ml.polynomial import (
    THETA_SIZE, _LEGACY_THETA_SIZE, migrate_theta_v1_to_v2,
)

logger = logging.getLogger(__name__)


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
        eval_time: Solver time budget per evaluation (seconds).
        delta_pct: Max bias delta as fraction of n/4.
    """
    lr: float = 0.001
    sigma: float = 0.02
    K: int = 50
    batch_size: int = 5
    max_steps: int = 1000
    checkpoint_interval: int = 50
    eval_time: float = 5.0
    delta_pct: float = 0.03

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
    """Compute scalar difference between two signal tuples.

    Signals are (best_objective, -time_to_best) tuples compared
    lexicographically. We reduce to a scalar by comparing elements:
    if the primary differs, use the primary difference; otherwise
    use the secondary difference.
    """
    d0 = signal_plus[0] - signal_minus[0]
    d1 = signal_plus[1] - signal_minus[1]
    if abs(d0) > 1e-12:
        return d0
    return d1


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
            self._theta = np.zeros(THETA_SIZE, dtype=np.float64)

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

        for step in range(start_step, cfg.max_steps):
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

            for instance in batch:
                # Compute signal diffs for all K perturbations
                diffs = np.empty(cfg.K, dtype=np.float64)
                for k, eps in enumerate(epsilons):
                    theta_plus = self._theta + cfg.sigma * eps
                    theta_minus = self._theta - cfg.sigma * eps
                    sig_plus = evaluate(theta_plus, instance, cfg.eval_time)
                    sig_minus = evaluate(theta_minus, instance, cfg.eval_time)
                    diffs[k] = _signal_diff(sig_plus, sig_minus)

                # Per-instance normalization
                norm_diffs = normalize_signals(diffs)

                # Accumulate gradient
                for k, eps in enumerate(epsilons):
                    gradient += norm_diffs[k] * eps

            # Scale gradient
            gradient /= (2.0 * cfg.sigma * cfg.K * cfg.batch_size)

            # Adam update
            self._theta = self._optimizer.step(self._theta, gradient)

            # Log step
            grad_norm = float(np.linalg.norm(gradient))
            self._step_log.append({
                'step': step,
                'grad_norm': grad_norm,
                'theta_norm': float(np.linalg.norm(self._theta)),
            })
            logger.debug("step=%d  grad_norm=%.6f  theta_norm=%.6f",
                         step, grad_norm,
                         float(np.linalg.norm(self._theta)))

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
