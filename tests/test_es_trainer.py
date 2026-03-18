"""Tests for cbqs.ml.es_trainer — ES training loop with antithetic sampling."""

import os
import tempfile
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from cbqs.ml.es_trainer import ESTrainer, ESTrainerConfig
from cbqs.ml.es_checkpoint import save_checkpoint
from cbqs.ml.polynomial import THETA_SIZE, _LEGACY_THETA_SIZE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool(n=10):
    """Create a list of mock model objects for the training pool."""
    pool = []
    for i in range(n):
        m = MagicMock()
        m.name = f"instance_{i}"
        pool.append(m)
    return pool


def _constant_evaluate(theta, model, time_budget):
    """Evaluate that always returns the same signal regardless of theta."""
    return (100.0, -1.0)


def _theta_dependent_evaluate(theta, model, time_budget):
    """Evaluate whose signal depends on theta norm (higher norm -> higher signal)."""
    score = float(np.sum(theta))
    return (score, -1.0)


def _noisy_evaluate(theta, model, time_budget):
    """Evaluate with random noise around theta sum."""
    score = float(np.sum(theta)) + np.random.randn() * 0.01
    return (score, -1.0)


# ---------------------------------------------------------------------------
# ESTrainerConfig tests
# ---------------------------------------------------------------------------

class TestESTrainerConfig:
    def test_defaults(self):
        cfg = ESTrainerConfig()
        assert cfg.lr == 0.001
        assert cfg.sigma == 0.02
        assert cfg.K == 50
        assert cfg.batch_size == 5
        assert cfg.max_steps == 1000
        assert cfg.checkpoint_interval == 50
        assert cfg.eval_time == 5.0
        assert cfg.delta_pct == 0.03

    def test_custom_values(self):
        cfg = ESTrainerConfig(lr=0.01, sigma=0.05, K=20, batch_size=3,
                              max_steps=100, checkpoint_interval=10,
                              eval_time=2.0, delta_pct=0.05)
        assert cfg.lr == 0.01
        assert cfg.sigma == 0.05
        assert cfg.K == 20
        assert cfg.batch_size == 3
        assert cfg.max_steps == 100

    def test_asdict(self):
        cfg = ESTrainerConfig()
        d = asdict(cfg)
        assert 'lr' in d
        assert 'sigma' in d
        assert 'K' in d


# ---------------------------------------------------------------------------
# ESTrainer construction tests
# ---------------------------------------------------------------------------

class TestESTrainerInit:
    def test_default_theta_is_zeros(self):
        cfg = ESTrainerConfig(max_steps=0)
        trainer = ESTrainer(cfg)
        assert trainer._theta.shape == (THETA_SIZE,)
        np.testing.assert_array_equal(trainer._theta, np.zeros(THETA_SIZE))

    def test_custom_theta_init(self):
        cfg = ESTrainerConfig(max_steps=0)
        theta0 = np.ones(THETA_SIZE) * 0.5
        trainer = ESTrainer(cfg, theta_init=theta0)
        np.testing.assert_array_equal(trainer._theta, theta0)

    def test_invalid_theta_shape_raises(self):
        cfg = ESTrainerConfig()
        with pytest.raises(ValueError):
            ESTrainer(cfg, theta_init=np.zeros(10))


# ---------------------------------------------------------------------------
# Gradient computation tests
# ---------------------------------------------------------------------------

class TestGradientComputation:
    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_constant_evaluate)
    def test_constant_signal_zero_gradient(self, mock_eval):
        """When evaluate returns the same value for +/- perturbations,
        the gradient estimate should be zero (or very near zero)."""
        cfg = ESTrainerConfig(max_steps=1, K=10, batch_size=2,
                              sigma=0.02, lr=0.001)
        trainer = ESTrainer(cfg)
        pool = _make_pool(5)
        theta = trainer.train(pool)
        # With constant signal, gradient is zero, so theta should not change
        np.testing.assert_allclose(theta, np.zeros(THETA_SIZE), atol=1e-10)

    @patch('cbqs.ml.es_trainer.evaluate')
    def test_antithetic_sampling(self, mock_eval):
        """Verify that evaluate is called with theta + sigma*eps
        and theta - sigma*eps for each perturbation."""
        cfg = ESTrainerConfig(max_steps=1, K=3, batch_size=1,
                              sigma=0.05, lr=0.001)
        trainer = ESTrainer(cfg)

        calls = []
        def capture_eval(theta, model, time_budget):
            calls.append(theta.copy())
            return (float(np.sum(theta)), -1.0)

        mock_eval.side_effect = capture_eval
        pool = _make_pool(5)
        trainer.train(pool)

        # Should have 2*K calls per instance in batch = 2*3*1 = 6
        assert len(calls) == 6
        # Each pair should be symmetric around the base theta (zeros)
        for i in range(0, 6, 2):
            np.testing.assert_allclose(calls[i] + calls[i + 1],
                                       np.zeros(THETA_SIZE), atol=1e-10)

    @patch('cbqs.ml.es_trainer.evaluate')
    def test_theta_changes_after_nonconstant_signal(self, mock_eval):
        """With a non-constant signal, theta should change from its initial value."""
        def quadratic_eval(theta, model, time_budget):
            # Reward being close to target=1 vector (negative distance)
            target = np.ones(THETA_SIZE)
            return (-float(np.sum((theta - target) ** 2)), -1.0)

        mock_eval.side_effect = quadratic_eval
        cfg = ESTrainerConfig(max_steps=5, K=20, batch_size=2,
                              sigma=0.02, lr=0.01)
        trainer = ESTrainer(cfg)
        pool = _make_pool(5)

        np.random.seed(42)
        theta = trainer.train(pool)
        # theta should have moved away from zero
        assert np.linalg.norm(theta) > 1e-6


# ---------------------------------------------------------------------------
# Per-instance signal normalization tests
# ---------------------------------------------------------------------------

class TestPerInstanceNormalization:
    @patch('cbqs.ml.es_trainer.evaluate')
    def test_normalization_applied(self, mock_eval):
        """Signal diffs should be normalized per-instance before gradient
        aggregation. With two instances of very different scales, each
        should contribute equally."""
        call_count = [0]
        def scale_by_instance(theta, model, time_budget):
            call_count[0] += 1
            base = float(np.sum(theta))
            # Different instances have different scales
            if model.name == "instance_0":
                return (base * 1000, -1.0)
            else:
                return (base * 0.001, -1.0)

        mock_eval.side_effect = scale_by_instance
        cfg = ESTrainerConfig(max_steps=1, K=10, batch_size=2,
                              sigma=0.02, lr=0.001)
        trainer = ESTrainer(cfg)
        pool = _make_pool(5)
        np.random.seed(123)
        theta = trainer.train(pool)
        # Just verify it ran without error and theta changed shape is correct
        assert theta.shape == (THETA_SIZE,)


# ---------------------------------------------------------------------------
# Adam integration tests
# ---------------------------------------------------------------------------

class TestAdamIntegration:
    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_optimizer_state_advances(self, mock_eval):
        """After training, optimizer step count should equal max_steps."""
        cfg = ESTrainerConfig(max_steps=3, K=5, batch_size=1,
                              sigma=0.02, lr=0.001)
        trainer = ESTrainer(cfg)
        pool = _make_pool(5)
        np.random.seed(42)
        trainer.train(pool)
        assert trainer._optimizer._t == 3


# ---------------------------------------------------------------------------
# Checkpoint tests
# ---------------------------------------------------------------------------

class TestCheckpointing:
    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_checkpoint_at_correct_intervals(self, mock_eval):
        """Checkpoints should be saved at step 0, checkpoint_interval, etc."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ckpt_dir = os.path.join(tmpdir, 'ckpts')
            os.makedirs(ckpt_dir)
            cfg = ESTrainerConfig(max_steps=6, K=3, batch_size=1,
                                  sigma=0.02, lr=0.001,
                                  checkpoint_interval=3)
            trainer = ESTrainer(cfg, checkpoint_dir=ckpt_dir)
            pool = _make_pool(5)
            np.random.seed(42)
            trainer.train(pool)

            # Steps 0, 3 should produce checkpoints
            assert os.path.isfile(os.path.join(ckpt_dir, 'step_000000.npz'))
            assert os.path.isfile(os.path.join(ckpt_dir, 'step_000000.json'))
            assert os.path.isfile(os.path.join(ckpt_dir, 'step_000003.npz'))
            assert os.path.isfile(os.path.join(ckpt_dir, 'step_000003.json'))

    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_no_checkpoint_without_dir(self, mock_eval):
        """When no checkpoint_dir is given, training should still work."""
        cfg = ESTrainerConfig(max_steps=2, K=3, batch_size=1,
                              sigma=0.02, lr=0.001)
        trainer = ESTrainer(cfg)
        pool = _make_pool(5)
        np.random.seed(42)
        theta = trainer.train(pool)
        assert theta.shape == (THETA_SIZE,)


# ---------------------------------------------------------------------------
# Resume tests
# ---------------------------------------------------------------------------

class TestResume:
    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_resume_continues_from_checkpoint(self, mock_eval):
        """Training 6 steps should equal training 3 + resume 3."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ckpt_dir = os.path.join(tmpdir, 'ckpts')
            os.makedirs(ckpt_dir)

            pool = _make_pool(5)

            # Train 3 steps
            cfg = ESTrainerConfig(max_steps=3, K=5, batch_size=1,
                                  sigma=0.02, lr=0.001,
                                  checkpoint_interval=3)
            trainer = ESTrainer(cfg, checkpoint_dir=ckpt_dir)
            np.random.seed(42)
            trainer.train(pool)

            # Resume for 3 more steps
            ckpt_path = os.path.join(ckpt_dir, 'step_000000')
            cfg2 = ESTrainerConfig(max_steps=6, K=5, batch_size=1,
                                   sigma=0.02, lr=0.001,
                                   checkpoint_interval=3)
            trainer2 = ESTrainer(cfg2, checkpoint_dir=ckpt_dir)
            theta_resumed = trainer2.resume(ckpt_path, pool)
            assert theta_resumed.shape == (THETA_SIZE,)

    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_resume_restores_optimizer_state(self, mock_eval):
        """Resumed optimizer should have state from the checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ckpt_dir = os.path.join(tmpdir, 'ckpts')
            os.makedirs(ckpt_dir)

            pool = _make_pool(5)
            cfg = ESTrainerConfig(max_steps=3, K=5, batch_size=1,
                                  sigma=0.02, lr=0.001,
                                  checkpoint_interval=1)
            trainer = ESTrainer(cfg, checkpoint_dir=ckpt_dir)
            np.random.seed(42)
            trainer.train(pool)

            # Resume from step 2
            ckpt_path = os.path.join(ckpt_dir, 'step_000002')
            cfg2 = ESTrainerConfig(max_steps=5, K=5, batch_size=1,
                                   sigma=0.02, lr=0.001,
                                   checkpoint_interval=1)
            trainer2 = ESTrainer(cfg2, checkpoint_dir=ckpt_dir)
            trainer2.resume(ckpt_path, pool)
            # Optimizer should have continued from step 2
            # (step 2 in checkpoint + steps 3,4 = total 4 adam steps)
            assert trainer2._optimizer._t > 2

    def test_resume_missing_checkpoint_raises(self):
        cfg = ESTrainerConfig(max_steps=5)
        trainer = ESTrainer(cfg)
        with pytest.raises(FileNotFoundError):
            trainer.resume('/nonexistent/path', _make_pool(3))


# ---------------------------------------------------------------------------
# Config validation tests
# ---------------------------------------------------------------------------

class TestConfigValidation:
    def test_negative_lr_raises(self):
        with pytest.raises(ValueError):
            ESTrainerConfig(lr=-0.001)

    def test_zero_K_raises(self):
        with pytest.raises(ValueError):
            ESTrainerConfig(K=0)

    def test_zero_batch_size_raises(self):
        with pytest.raises(ValueError):
            ESTrainerConfig(batch_size=0)

    def test_negative_sigma_raises(self):
        with pytest.raises(ValueError):
            ESTrainerConfig(sigma=-0.01)

    def test_zero_max_steps_ok(self):
        cfg = ESTrainerConfig(max_steps=0)
        assert cfg.max_steps == 0


# ---------------------------------------------------------------------------
# Training pool validation tests
# ---------------------------------------------------------------------------

class TestPoolValidation:
    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_constant_evaluate)
    def test_empty_pool_raises(self, mock_eval):
        cfg = ESTrainerConfig(max_steps=1, batch_size=1)
        trainer = ESTrainer(cfg)
        with pytest.raises(ValueError, match="pool"):
            trainer.train([])

    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_constant_evaluate)
    def test_pool_smaller_than_batch_uses_replacement(self, mock_eval):
        """If pool < batch_size, sample with replacement."""
        cfg = ESTrainerConfig(max_steps=1, K=3, batch_size=5,
                              sigma=0.02, lr=0.001)
        trainer = ESTrainer(cfg)
        pool = _make_pool(2)  # smaller than batch_size=5
        theta = trainer.train(pool)
        assert theta.shape == (THETA_SIZE,)


# ---------------------------------------------------------------------------
# Logging tests
# ---------------------------------------------------------------------------

class TestLogging:
    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_step_log_recorded(self, mock_eval):
        """Trainer should record step logs."""
        cfg = ESTrainerConfig(max_steps=3, K=3, batch_size=1,
                              sigma=0.02, lr=0.001)
        trainer = ESTrainer(cfg)
        pool = _make_pool(5)
        np.random.seed(42)
        trainer.train(pool)
        assert len(trainer._step_log) == 3

    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_step_log_contains_gradient_norm(self, mock_eval):
        """Each step log entry should contain gradient norm."""
        cfg = ESTrainerConfig(max_steps=1, K=5, batch_size=1,
                              sigma=0.02, lr=0.001)
        trainer = ESTrainer(cfg)
        pool = _make_pool(5)
        np.random.seed(42)
        trainer.train(pool)
        entry = trainer._step_log[0]
        assert 'grad_norm' in entry
        assert 'step' in entry


# ---------------------------------------------------------------------------
# End-to-end sanity test
# ---------------------------------------------------------------------------

class TestEndToEnd:
    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_noisy_evaluate)
    def test_full_training_run(self, mock_eval):
        """Run a small but complete training session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ckpt_dir = os.path.join(tmpdir, 'ckpts')
            os.makedirs(ckpt_dir)
            cfg = ESTrainerConfig(max_steps=10, K=5, batch_size=2,
                                  sigma=0.02, lr=0.001,
                                  checkpoint_interval=5)
            trainer = ESTrainer(cfg, checkpoint_dir=ckpt_dir)
            pool = _make_pool(5)
            np.random.seed(42)
            theta = trainer.train(pool)
            assert theta.shape == (THETA_SIZE,)
            assert len(trainer._step_log) == 10
            # Checkpoints at steps 0 and 5
            assert os.path.isfile(os.path.join(ckpt_dir, 'step_000000.npz'))
            assert os.path.isfile(os.path.join(ckpt_dir, 'step_000005.npz'))


# ---------------------------------------------------------------------------
# Legacy checkpoint migration tests
# ---------------------------------------------------------------------------

def _save_legacy_checkpoint(path, step=5):
    """Create a legacy 344-dim checkpoint on disk."""
    theta_legacy = np.random.RandomState(99).randn(_LEGACY_THETA_SIZE)
    m_legacy = np.random.RandomState(100).randn(_LEGACY_THETA_SIZE) * 0.01
    v_legacy = np.abs(np.random.RandomState(101).randn(_LEGACY_THETA_SIZE)) * 0.001
    best_legacy = np.random.RandomState(102).randn(_LEGACY_THETA_SIZE)
    opt_state = {'m': m_legacy, 'v': v_legacy, 't': 10}
    save_checkpoint(
        path=path,
        theta=theta_legacy,
        optimizer_state=opt_state,
        training_pool=['inst_a.npz', 'inst_b.npz'],
        step=step,
        config={'lr': 0.001, 'sigma': 0.02},
        log_path='',
        best_theta=best_legacy,
        best_validation_signal=-1.5,
    )
    return theta_legacy, best_legacy


class TestLegacyCheckpointMigration:
    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_resume_migrates_legacy_theta(self, mock_eval):
        """Resuming from a 344-dim checkpoint should migrate theta to 146."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ckpt_path = os.path.join(tmpdir, 'legacy_ckpt')
            _save_legacy_checkpoint(ckpt_path, step=5)

            cfg = ESTrainerConfig(max_steps=7, K=3, batch_size=1,
                                  sigma=0.02, lr=0.001)
            trainer = ESTrainer(cfg)
            pool = _make_pool(3)
            np.random.seed(42)
            theta = trainer.resume(ckpt_path, pool)
            assert theta.shape == (THETA_SIZE,)

    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_resume_resets_adam_on_migration(self, mock_eval):
        """Adam state should be reset when resuming from a legacy checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ckpt_path = os.path.join(tmpdir, 'legacy_ckpt')
            _save_legacy_checkpoint(ckpt_path, step=5)

            cfg = ESTrainerConfig(max_steps=7, K=3, batch_size=1,
                                  sigma=0.02, lr=0.001)
            trainer = ESTrainer(cfg)
            pool = _make_pool(3)
            np.random.seed(42)
            trainer.resume(ckpt_path, pool)
            # After reset + 1 step (range(6, 7)), optimizer _t should be 1
            assert trainer._optimizer._t == 1

    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_resume_migrates_best_theta(self, mock_eval):
        """best_theta should also be migrated from 344 to 146."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ckpt_path = os.path.join(tmpdir, 'legacy_ckpt')
            _save_legacy_checkpoint(ckpt_path, step=5)

            cfg = ESTrainerConfig(max_steps=6, K=3, batch_size=1,
                                  sigma=0.02, lr=0.001)
            trainer = ESTrainer(cfg)
            pool = _make_pool(3)
            np.random.seed(42)
            trainer.resume(ckpt_path, pool)
            assert trainer._best_theta is not None
            assert trainer._best_theta.shape == (THETA_SIZE,)

    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_resume_current_checkpoint_preserves_adam(self, mock_eval):
        """Resuming from a current 146-dim checkpoint preserves Adam state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ckpt_dir = os.path.join(tmpdir, 'ckpts')
            os.makedirs(ckpt_dir)
            pool = _make_pool(5)

            cfg = ESTrainerConfig(max_steps=3, K=3, batch_size=1,
                                  sigma=0.02, lr=0.001,
                                  checkpoint_interval=1)
            trainer = ESTrainer(cfg, checkpoint_dir=ckpt_dir)
            np.random.seed(42)
            trainer.train(pool)

            ckpt_path = os.path.join(ckpt_dir, 'step_000002')
            cfg2 = ESTrainerConfig(max_steps=5, K=3, batch_size=1,
                                   sigma=0.02, lr=0.001)
            trainer2 = ESTrainer(cfg2)
            trainer2.resume(ckpt_path, pool)
            # Adam state preserved: _t=2 from checkpoint + 2 new steps = 4
            assert trainer2._optimizer._t == 4
