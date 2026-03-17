"""Tests for ES pipeline integration (M6).

End-to-end integration tests verifying:
- ES exports are accessible from cbqs.ml
- train_es() with mocked solver
- CLI arg parsing for --mode es
- Checkpoint -> predict flow
- Old trainers (sat, opt) remain accessible
"""

import argparse
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from cbqs.ml.polynomial import PolynomialPredictor, THETA_SIZE
from cbqs.ml.es_trainer import ESTrainer, ESTrainerConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_pool(n=5):
    """Create a list of mock model objects for the training pool."""
    pool = []
    for i in range(n):
        m = MagicMock()
        m.name = f"instance_{i}"
        pool.append(m)
    return pool


def _constant_evaluate(theta, model, time_budget):
    """Evaluate that always returns the same signal."""
    return (100.0, -1.0)


def _theta_dependent_evaluate(theta, model, time_budget):
    """Evaluate whose signal depends on theta norm."""
    score = float(np.sum(theta))
    return (score, -1.0)


# ---------------------------------------------------------------------------
# ES exports from cbqs.ml
# ---------------------------------------------------------------------------

class TestESExports:
    def test_polynomial_predictor_importable(self):
        """PolynomialPredictor should be importable from cbqs.ml."""
        from cbqs.ml import PolynomialPredictor as PP
        assert PP is PolynomialPredictor

    def test_es_trainer_importable(self):
        """ESTrainer should be importable from cbqs.ml."""
        from cbqs.ml import ESTrainer as ET
        assert ET is ESTrainer

    def test_es_trainer_config_importable(self):
        """ESTrainerConfig should be importable from cbqs.ml."""
        from cbqs.ml import ESTrainerConfig as ETC
        assert ETC is ESTrainerConfig

    def test_es_exports_in_all(self):
        """ES classes should be listed in cbqs.ml.__all__."""
        import cbqs.ml
        assert 'PolynomialPredictor' in cbqs.ml.__all__
        assert 'ESTrainer' in cbqs.ml.__all__
        assert 'ESTrainerConfig' in cbqs.ml.__all__

    def test_old_exports_still_present(self):
        """Old exports (FeatureExtractor, etc.) should still be accessible."""
        from cbqs.ml import FeatureExtractor
        from cbqs.ml import WeightPredictor
        from cbqs.ml import collect_training_data
        from cbqs.ml import evaluate
        from cbqs.ml import evaluate_weights
        from cbqs.ml import validate_transfer
        from cbqs.ml import adaptive_solve
        from cbqs.ml import AdaptiveResult
        assert FeatureExtractor is not None
        assert WeightPredictor is not None

    def test_es_imports_without_sklearn(self):
        """ES classes should be importable even if sklearn is missing.

        The ES pipeline uses numpy only, so it should not be blocked by
        the sklearn import guard.
        """
        # Direct imports should always work regardless of sklearn
        from cbqs.ml.polynomial import PolynomialPredictor
        from cbqs.ml.es_trainer import ESTrainer, ESTrainerConfig
        assert PolynomialPredictor is not None
        assert ESTrainer is not None
        assert ESTrainerConfig is not None


# ---------------------------------------------------------------------------
# Old trainers still accessible
# ---------------------------------------------------------------------------

class TestOldTrainersAccessible:
    def test_sat_trainer_importable(self):
        """SATTrainer should still be importable."""
        from cbqs.ml.sat_trainer import SATTrainer
        assert SATTrainer is not None

    def test_opt_trainer_importable(self):
        """OPTTrainer should still be importable."""
        from cbqs.ml.opt_trainer import OPTTrainer
        assert OPTTrainer is not None


# ---------------------------------------------------------------------------
# CLI arg parsing
# ---------------------------------------------------------------------------

class TestCLIArgParsing:
    def test_mode_es_accepted(self):
        """--mode es should be a valid CLI argument."""
        from training.train import build_parser
        parser = build_parser()
        args = parser.parse_args(['--mode', 'es'])
        assert args.mode == 'es'

    def test_es_specific_args(self):
        """ES-specific CLI args should be parseable."""
        from training.train import build_parser
        parser = build_parser()
        args = parser.parse_args([
            '--mode', 'es',
            '--es-lr', '0.01',
            '--es-sigma', '0.05',
            '--es-k', '20',
            '--es-batch-size', '3',
            '--es-max-steps', '100',
            '--es-checkpoint-interval', '10',
            '--es-eval-time', '2.0',
            '--es-delta-pct', '0.05',
        ])
        assert args.mode == 'es'
        assert args.es_lr == 0.01
        assert args.es_sigma == 0.05
        assert args.es_k == 20
        assert args.es_batch_size == 3
        assert args.es_max_steps == 100
        assert args.es_checkpoint_interval == 10
        assert args.es_eval_time == 2.0
        assert args.es_delta_pct == 0.05


# ---------------------------------------------------------------------------
# train_es() function
# ---------------------------------------------------------------------------

class TestTrainES:
    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_train_es_runs(self, mock_eval):
        """train_es() should run and return a trained theta."""
        from training.train import train_es
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, 'output')
            os.makedirs(out_dir)

            args = argparse.Namespace(
                es_lr=0.001,
                es_sigma=0.02,
                es_k=5,
                es_batch_size=2,
                es_max_steps=3,
                es_checkpoint_interval=10,
                es_eval_time=1.0,
                es_delta_pct=0.03,
            )
            pool = _make_mock_pool(5)
            val_pool = _make_mock_pool(2)

            np.random.seed(42)
            train_es(pool, val_pool, args, out_dir)

            # Predictor file should be saved
            predictor_path = os.path.join(out_dir, 'es_predictor.npz')
            assert os.path.isfile(predictor_path)

    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_train_es_saves_valid_predictor(self, mock_eval):
        """Saved predictor from train_es() should be loadable."""
        from training.train import train_es
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, 'output')
            os.makedirs(out_dir)

            args = argparse.Namespace(
                es_lr=0.001,
                es_sigma=0.02,
                es_k=5,
                es_batch_size=2,
                es_max_steps=3,
                es_checkpoint_interval=10,
                es_eval_time=1.0,
                es_delta_pct=0.03,
            )
            pool = _make_mock_pool(5)

            np.random.seed(42)
            train_es(pool, None, args, out_dir)

            predictor_path = os.path.join(out_dir, 'es_predictor.npz')
            predictor = PolynomialPredictor.load(predictor_path)
            assert predictor.W_var.shape[0] > 0
            assert predictor.W_inst.shape[0] > 0

    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_constant_evaluate)
    def test_train_es_zero_steps(self, mock_eval):
        """train_es() with zero steps should save a zero-theta predictor."""
        from training.train import train_es
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, 'output')
            os.makedirs(out_dir)

            args = argparse.Namespace(
                es_lr=0.001,
                es_sigma=0.02,
                es_k=5,
                es_batch_size=2,
                es_max_steps=0,
                es_checkpoint_interval=10,
                es_eval_time=1.0,
                es_delta_pct=0.03,
            )
            pool = _make_mock_pool(3)

            train_es(pool, None, args, out_dir)

            predictor_path = os.path.join(out_dir, 'es_predictor.npz')
            assert os.path.isfile(predictor_path)


# ---------------------------------------------------------------------------
# Checkpoint -> predict flow
# ---------------------------------------------------------------------------

class TestCheckpointPredictFlow:
    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_checkpoint_to_predictor(self, mock_eval):
        """Train, save checkpoint, load theta, create predictor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ckpt_dir = os.path.join(tmpdir, 'ckpts')
            os.makedirs(ckpt_dir)

            cfg = ESTrainerConfig(
                max_steps=3, K=5, batch_size=2,
                sigma=0.02, lr=0.001, checkpoint_interval=1)
            trainer = ESTrainer(cfg, checkpoint_dir=ckpt_dir)
            pool = _make_mock_pool(5)
            np.random.seed(42)
            theta = trainer.train(pool)

            # Save predictor from trained theta
            predictor = PolynomialPredictor(theta)
            pred_path = os.path.join(tmpdir, 'predictor.npz')
            predictor.save(pred_path)

            # Load and verify
            loaded = PolynomialPredictor.load(pred_path)
            np.testing.assert_array_equal(
                loaded.W_var, predictor.W_var)
            np.testing.assert_array_equal(
                loaded.W_inst, predictor.W_inst)

    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_train_checkpoint_resume_predict(self, mock_eval):
        """Full flow: train -> checkpoint -> resume -> predict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ckpt_dir = os.path.join(tmpdir, 'ckpts')
            os.makedirs(ckpt_dir)

            pool = _make_mock_pool(5)

            # Train 3 steps with checkpoint at step 0
            cfg = ESTrainerConfig(
                max_steps=3, K=5, batch_size=1,
                sigma=0.02, lr=0.001, checkpoint_interval=1)
            trainer = ESTrainer(cfg, checkpoint_dir=ckpt_dir)
            np.random.seed(42)
            trainer.train(pool)

            # Resume from step 0 for 5 total steps
            cfg2 = ESTrainerConfig(
                max_steps=5, K=5, batch_size=1,
                sigma=0.02, lr=0.001, checkpoint_interval=1)
            trainer2 = ESTrainer(cfg2, checkpoint_dir=ckpt_dir)
            ckpt_path = os.path.join(ckpt_dir, 'step_000000')
            theta = trainer2.resume(ckpt_path, pool)

            # Create predictor from resumed theta
            predictor = PolynomialPredictor(theta)
            assert predictor.W_var.shape[1] > 0
            assert predictor.W_inst.shape[1] > 0


# ---------------------------------------------------------------------------
# Bias near n/4 for various sizes (with real Model objects)
# ---------------------------------------------------------------------------

class TestBiasNearNOver4:
    def test_zero_theta_bias_approx_n_over_4(self):
        """Zero-theta predictor produces bias ~ n/4 for various model sizes."""
        from cbqs.Model import Model
        theta = np.zeros(THETA_SIZE)
        predictor = PolynomialPredictor(theta)

        for n in [10, 50, 100]:
            m = Model()
            xs = m.add_variables(n)
            m.add_constraint(xs[0] + xs[1] + xs[2] <= 2)
            m.set_objective(sum(xs[i] for i in range(n)))
            m.close()

            result = predictor.predict(m)
            assert result['branching_bias'] == pytest.approx(n / 4.0), (
                f"Expected bias ~ {n / 4.0} for n={n}, "
                f"got {result['branching_bias']}"
            )


# ---------------------------------------------------------------------------
# End-to-end test with real model
# ---------------------------------------------------------------------------

class TestEndToEndRealModel:
    @patch('cbqs.ml.es_trainer.evaluate', side_effect=_theta_dependent_evaluate)
    def test_knapsack_train_predict(self, mock_eval):
        """Train ES on real knapsack models and verify predictor output."""
        from training.train import make_random_knapsack

        # Generate small knapsack instances
        models = [make_random_knapsack(15, rng=__import__('random').Random(i))
                  for i in range(5)]

        with tempfile.TemporaryDirectory() as tmpdir:
            ckpt_dir = os.path.join(tmpdir, 'ckpts')
            os.makedirs(ckpt_dir)

            cfg = ESTrainerConfig(
                max_steps=3, K=3, batch_size=2,
                sigma=0.02, lr=0.001, checkpoint_interval=10)
            trainer = ESTrainer(cfg, checkpoint_dir=ckpt_dir)

            np.random.seed(42)
            theta = trainer.train(models)

            # Load theta into predictor
            predictor = PolynomialPredictor(theta)

            # Verify predictions on each training model
            for m in models:
                result = predictor.predict(m)
                n = len(m.variables)

                # Bias must be near n/4 (within delta_pct bound)
                base = n / 4.0
                bound = 0.03 * base
                assert base - bound - 1e-10 <= result['branching_bias'] <= base + bound + 1e-10

                # Weights shape
                assert result['branching_weights'].shape == (n,)

                # Priorities is a permutation
                assert set(result['variable_priorities']) == set(range(n))

                # Factors are non-negative
                assert result['branching_factor'] >= 0.0
                assert result['bias_factor'] >= 0.0


# ---------------------------------------------------------------------------
# ESTrainerConfig from CLI args
# ---------------------------------------------------------------------------

class TestConfigFromArgs:
    def test_config_from_namespace(self):
        """ESTrainerConfig should be constructable from CLI arg values."""
        args = argparse.Namespace(
            es_lr=0.01,
            es_sigma=0.05,
            es_k=20,
            es_batch_size=3,
            es_max_steps=100,
            es_checkpoint_interval=10,
            es_eval_time=2.0,
            es_delta_pct=0.05,
        )
        cfg = ESTrainerConfig(
            lr=args.es_lr,
            sigma=args.es_sigma,
            K=args.es_k,
            batch_size=args.es_batch_size,
            max_steps=args.es_max_steps,
            checkpoint_interval=args.es_checkpoint_interval,
            eval_time=args.es_eval_time,
            delta_pct=args.es_delta_pct,
        )
        assert cfg.lr == 0.01
        assert cfg.K == 20
        assert cfg.max_steps == 100
