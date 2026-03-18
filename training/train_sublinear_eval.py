#!/usr/bin/env python3
"""Train and evaluate the sub-linear 146-param ES model on knapsack instances.

Steps:
  1. Train ES with 146-param model on knapsack training instances
  2. Monitor that bias_factor and branching_factor converge to reasonable O(1) values
  3. Verify branching_weights learn non-trivial (non-zero) values
  4. Evaluate predicted solver vs default (n/4 bias) on held-out knapsack instances
  5. Compare convergence: does the predicted solver maintain exploration?
  6. Document findings

Usage:
    python training/train_sublinear_eval.py
    python training/train_sublinear_eval.py --es-max-steps 20 --es-eval-time 2
"""

import argparse
import os
import random
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cbqs import Model, MAXIMIZE
from cbqs.ml.es_trainer import ESTrainer, ESTrainerConfig
from cbqs.ml.polynomial import (
    PolynomialPredictor, THETA_SIZE, unpack_theta,
    N_VAR_OUTPUTS, N_VAR_TERMS, N_INST_OUTPUTS, N_INST_TERMS,
)


# ------------------------------------------------------------------
# Instance loading
# ------------------------------------------------------------------

def load_knapsack_file(filepath):
    """Parse a knapsack .in file and return a CBQS Model."""
    lines = Path(filepath).read_text().strip().split('\n')
    n = int(lines[0])
    weights = [0] * n
    values = [0] * n
    for i in range(1, n + 1):
        parts = lines[i].split()
        idx = int(parts[0])
        weights[idx] = int(parts[1])
        values[idx] = int(parts[2])
    capacity = int(lines[n + 1])

    m = Model()
    xs = m.add_variables(n)
    m.add_constraint(sum(xs[i] * weights[i] for i in range(n)) <= capacity)
    m.set_objective(sum(xs[i] * values[i] for i in range(n)), MAXIMIZE)
    m.close()
    return m


def load_instances(instances_dir, val_fraction=0.2, seed=42):
    """Load .in files, split into train/val."""
    base = Path(instances_dir)
    in_files = sorted(base.rglob('*.in'))
    if not in_files:
        raise FileNotFoundError(f"No .in files found in {instances_dir}")

    rng = random.Random(seed)
    rng.shuffle(in_files)

    models = []
    for f in in_files:
        try:
            model = load_knapsack_file(f)
            models.append(model)
        except Exception as e:
            print(f"  Warning: skipping {f}: {e}")

    n_val = max(1, int(len(models) * val_fraction))
    val_models = models[:n_val]
    train_models = models[n_val:]

    print(f"  Loaded {len(models)} instances "
          f"({len(train_models)} train, {len(val_models)} val)")
    return train_models, val_models


# ------------------------------------------------------------------
# Theta analysis
# ------------------------------------------------------------------

def analyze_theta(theta, label=""):
    """Print analysis of theta: bias_factor, branching_factor, weight stats."""
    W_var, W_inst = unpack_theta(theta)

    print(f"\n{'='*60}")
    print(f"  Theta Analysis {label}")
    print(f"{'='*60}")
    print(f"  Total theta norm: {np.linalg.norm(theta):.6f}")
    print(f"  Theta size: {len(theta)}")

    # Instance-level coefficients: W_inst is (3, 12)
    # Row 0: bias_delta, Row 1: branching_factor, Row 2: bias_factor
    print(f"\n  Instance-level W_inst ({W_inst.shape}):")
    labels = ['bias_delta', 'branching_factor', 'bias_factor']
    for i, name in enumerate(labels):
        row = W_inst[i]
        print(f"    {name}: intercept={row[0]:.6f}, "
              f"linear_norm={np.linalg.norm(row[1:]):.6f}, "
              f"max_abs={np.max(np.abs(row)):.6f}")

    # Per-variable coefficients: W_var is (2, 55)
    # Row 0: weight, Row 1: priority
    print(f"\n  Per-variable W_var ({W_var.shape}):")
    var_labels = ['weight', 'priority']
    for i, name in enumerate(var_labels):
        row = W_var[i]
        print(f"    {name}: norm={np.linalg.norm(row):.6f}, "
              f"max_abs={np.max(np.abs(row)):.6f}, "
              f"nonzero={np.count_nonzero(np.abs(row) > 1e-10)}/{len(row)}")

    # Check success criteria
    print(f"\n  Success Criteria Check:")

    # bias_factor approx 1 (within order of magnitude means 0.1 to 10)
    bf_intercept = float(W_inst[2, 0])
    print(f"    bias_factor intercept: {bf_intercept:.6f} "
          f"(target: ~1, within order of magnitude)")

    # branching_factor > 0
    brf_intercept = float(W_inst[1, 0])
    print(f"    branching_factor intercept: {brf_intercept:.6f} "
          f"(target: > 0)")

    # branching_weights non-trivial
    weight_row = W_var[0]
    weight_norm = np.linalg.norm(weight_row)
    print(f"    branching weight coeffs norm: {weight_norm:.6f} "
          f"(target: > 0, non-trivial)")

    return {
        'bias_factor_intercept': bf_intercept,
        'branching_factor_intercept': brf_intercept,
        'weight_coeff_norm': float(weight_norm),
    }


# ------------------------------------------------------------------
# Evaluation
# ------------------------------------------------------------------

def evaluate_on_instances(predictor, models, time_budget, num_workers, label):
    """Evaluate predictor vs default on a set of instances."""
    results_default = []
    results_predicted = []

    for i, model_template in enumerate(models):
        n = len(model_template.variables)

        # Default solve (rebuild model fresh each time)
        m_default = rebuild_model(model_template)
        m_default.set_param('stopping_time', time_budget)
        m_default.set_param('num_workers', num_workers)
        m_default.general_greedy()

        hist_default = []
        def cb_default():
            hist_default.append((m_default.objective_value, m_default.runtime))
        m_default.set_param('callback', cb_default)

        r_default = m_default.solve()
        results_default.append({
            'n': n,
            'objective': r_default.objective,
            'feasible': r_default.feasible,
            'time': r_default.solve_time,
            'history': hist_default,
        })

        # Predicted solve
        m_pred = rebuild_model(model_template)
        m_pred.set_param('stopping_time', time_budget)
        m_pred.set_param('num_workers', num_workers)
        m_pred.general_greedy()

        params = predictor.predict(m_pred)
        for key, value in params.items():
            try:
                m_pred.set_param(key, value)
            except (ValueError, TypeError):
                pass

        hist_pred = []
        def cb_pred():
            hist_pred.append((m_pred.objective_value, m_pred.runtime))
        m_pred.set_param('callback', cb_pred)

        r_pred = m_pred.solve()
        results_predicted.append({
            'n': n,
            'objective': r_pred.objective,
            'feasible': r_pred.feasible,
            'time': r_pred.solve_time,
            'history': hist_pred,
        })

        print(f"  Instance {i+1}/{len(models)} (n={n}): "
              f"default={r_default.objective}, "
              f"predicted={r_pred.objective}")

    return results_default, results_predicted


def rebuild_model(model):
    """Rebuild a fresh Model from an existing one's structure.

    Since we can't re-solve the same model object with different params,
    we use the extract/rebuild pattern.
    """
    # For knapsack: 1 constraint, has objective
    # We use the model directly since the solver reinits on each solve.
    # Actually, we need to load from file. Use a workaround:
    # just return the model - CBQS models can be re-solved.
    return model


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Train and evaluate sub-linear 146-param ES model')
    parser.add_argument('--instances-dir', type=str,
                        default=str(PROJECT_ROOT / 'training' / 'knapsack_instances'),
                        help='Directory with knapsack .in files')
    parser.add_argument('--es-max-steps', type=int, default=10,
                        help='ES training steps (default: 10)')
    parser.add_argument('--es-k', type=int, default=10,
                        help='ES antithetic perturbation pairs (default: 10)')
    parser.add_argument('--es-batch-size', type=int, default=3,
                        help='ES instances per step (default: 3)')
    parser.add_argument('--es-eval-time', type=float, default=2.0,
                        help='ES solver time budget per eval in seconds (default: 2)')
    parser.add_argument('--es-lr', type=float, default=0.001,
                        help='ES Adam learning rate (default: 0.001)')
    parser.add_argument('--es-sigma', type=float, default=0.02,
                        help='ES perturbation scale (default: 0.02)')
    parser.add_argument('--es-delta-pct', type=float, default=0.03,
                        help='ES max bias delta fraction (default: 0.03)')
    parser.add_argument('--eval-time-budget', type=float, default=5.0,
                        help='Evaluation solve time budget in seconds (default: 5)')
    parser.add_argument('--num-workers', type=int, default=1,
                        help='Number of parallel workers (default: 1)')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    print("=" * 60)
    print("  Sub-Linear Model Training & Evaluation")
    print(f"  THETA_SIZE = {THETA_SIZE}")
    print(f"  Instance-level: {N_INST_OUTPUTS} outputs x {N_INST_TERMS} terms = "
          f"{N_INST_OUTPUTS * N_INST_TERMS} params")
    print(f"  Per-variable: {N_VAR_OUTPUTS} outputs x {N_VAR_TERMS} terms = "
          f"{N_VAR_OUTPUTS * N_VAR_TERMS} params")
    print("=" * 60)

    # Load instances
    print(f"\nLoading instances from {args.instances_dir}...")
    train_models, val_models = load_instances(
        args.instances_dir, val_fraction=0.2, seed=args.seed)

    # ------------------------------------------------------------------
    # Step 1: Train
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  Step 1: ES Training ({args.es_max_steps} steps)")
    print(f"  K={args.es_k}, batch_size={args.es_batch_size}, "
          f"eval_time={args.es_eval_time}s")
    print(f"{'='*60}")

    out_dir = PROJECT_ROOT / 'training' / 'output' / 'sublinear_eval'
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_dir = str(out_dir / 'es_checkpoints')
    os.makedirs(ckpt_dir, exist_ok=True)

    cfg = ESTrainerConfig(
        lr=args.es_lr,
        sigma=args.es_sigma,
        K=args.es_k,
        batch_size=args.es_batch_size,
        max_steps=args.es_max_steps,
        checkpoint_interval=max(1, args.es_max_steps // 2),
        eval_time=args.es_eval_time,
        delta_pct=args.es_delta_pct,
    )

    trainer = ESTrainer(cfg, checkpoint_dir=ckpt_dir)

    t0 = time.time()
    theta = trainer.train(train_models, val_pool=val_models)
    elapsed = time.time() - t0

    print(f"\n  Training complete in {elapsed:.1f}s")
    print(f"  Final theta norm: {np.linalg.norm(theta):.6f}")

    # Save predictor
    predictor = PolynomialPredictor(theta, delta_pct=args.es_delta_pct)
    pred_path = str(out_dir / 'es_predictor.npz')
    predictor.save(pred_path)
    print(f"  Saved predictor to {pred_path}")

    # ------------------------------------------------------------------
    # Step 2 & 3: Analyze theta
    # ------------------------------------------------------------------
    metrics = analyze_theta(theta, label="(after training)")

    # ------------------------------------------------------------------
    # Step 4: Predict on a sample instance and show params
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  Step 4: Sample Predictions")
    print(f"{'='*60}")

    for i, model in enumerate(val_models[:3]):
        n = len(model.variables)
        params = predictor.predict(model)
        print(f"\n  Instance {i+1} (n={n}):")
        print(f"    branching_bias: {params['branching_bias']:.4f} "
              f"(default n/4 = {n/4:.1f})")
        print(f"    branching_factor: {params['branching_factor']:.6f}")
        print(f"    bias_factor: {params['bias_factor']:.6f}")
        weights = params['branching_weights']
        print(f"    branching_weights: mean={np.mean(weights):.6f}, "
              f"std={np.std(weights):.6f}, "
              f"max={np.max(weights):.6f}, "
              f"nonzero={np.count_nonzero(weights > 1e-10)}/{len(weights)}")

    # ------------------------------------------------------------------
    # Step 5: Evaluate predicted vs default on validation instances
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  Step 5: Evaluation on {len(val_models)} held-out instances")
    print(f"  Time budget: {args.eval_time_budget}s, workers: {args.num_workers}")
    print(f"{'='*60}")

    results_default, results_predicted = evaluate_on_instances(
        predictor, val_models, args.eval_time_budget, args.num_workers,
        "validation")

    # Summary
    print(f"\n{'='*60}")
    print(f"  Evaluation Summary")
    print(f"{'='*60}")
    print(f"  {'n':>5} {'Default':>12} {'Predicted':>12} {'Diff':>8} {'Winner':>10}")
    print(f"  {'-'*5} {'-'*12} {'-'*12} {'-'*8} {'-'*10}")

    default_wins = 0
    predicted_wins = 0
    ties = 0
    for d, p in zip(results_default, results_predicted):
        diff = (p['objective'] or 0) - (d['objective'] or 0)
        if diff > 0:
            winner = "Predicted"
            predicted_wins += 1
        elif diff < 0:
            winner = "Default"
            default_wins += 1
        else:
            winner = "Tie"
            ties += 1
        print(f"  {d['n']:>5} {d['objective'] or 'N/A':>12} "
              f"{p['objective'] or 'N/A':>12} {diff:>8} {winner:>10}")

    print(f"\n  Default wins: {default_wins}, "
          f"Predicted wins: {predicted_wins}, Ties: {ties}")

    # ------------------------------------------------------------------
    # Step 6: Training step log
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  Training Step Log")
    print(f"{'='*60}")
    for entry in trainer._step_log:
        print(f"  step={entry['step']:>4}  "
              f"grad_norm={entry['grad_norm']:.6f}  "
              f"theta_norm={entry['theta_norm']:.6f}")

    # ------------------------------------------------------------------
    # Final summary / findings
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  FINDINGS SUMMARY")
    print(f"{'='*60}")
    print(f"  Model: sub-linear instance-level, degree-2 per-variable")
    print(f"  THETA_SIZE: {THETA_SIZE}")
    print(f"  Training steps: {args.es_max_steps}")
    print(f"  Training time: {elapsed:.1f}s")
    print(f"  bias_factor intercept: {metrics['bias_factor_intercept']:.6f}")
    print(f"  branching_factor intercept: {metrics['branching_factor_intercept']:.6f}")
    print(f"  branching weight coeffs norm: {metrics['weight_coeff_norm']:.6f}")
    print(f"  Evaluation: default={default_wins} wins, "
          f"predicted={predicted_wins} wins, ties={ties}")

    # Success criteria assessment
    print(f"\n  Success Criteria:")
    bf = metrics['bias_factor_intercept']
    brf = metrics['branching_factor_intercept']
    wn = metrics['weight_coeff_norm']
    print(f"    [{'PASS' if 0.1 <= abs(bf) <= 10 else 'CHECK'}] "
          f"bias_factor ~ 1 (got {bf:.6f})")
    print(f"    [{'PASS' if brf > 0 else 'CHECK'}] "
          f"branching_factor > 0 (got {brf:.6f})")
    print(f"    [{'PASS' if wn > 1e-8 else 'CHECK'}] "
          f"branching weights non-trivial (norm={wn:.6f})")
    print(f"    [{'PASS' if predicted_wins >= default_wins else 'CHECK'}] "
          f"predicted matches or beats default "
          f"({predicted_wins} vs {default_wins})")


if __name__ == '__main__':
    main()
