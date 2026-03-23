#!/usr/bin/env python3
"""Training script for CBQS ML branching parameter prediction.

Generates random combinatorial problem instances, trains SAT and OPT
predictors, evaluates on held-out instances, and saves artifacts.

Usage:
    python training/train.py                          # defaults
    python training/train.py --n-train 50 --n-val 10
    python training/train.py --mode sat --vars 10 20  # SAT only, 10-20 vars
    python training/train.py --problems knapsack sat   # specific problem types
    python training/train.py --instances-dir training/knapsack_instances  # use pre-generated instances
"""

import argparse
import os
import random
import sys
import time
from pathlib import Path

import numpy as np

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cbqs import Model, MAXIMIZE, MINIMIZE
from cbqs.ml.sat_trainer import SATTrainer
from cbqs.ml.opt_trainer import OPTTrainer
from cbqs.ml.es_trainer import ESTrainer, ESTrainerConfig
from cbqs.ml.polynomial import PolynomialPredictor


# ------------------------------------------------------------------
# Instance generators
# ------------------------------------------------------------------

def make_random_sat(n_vars, n_clauses, clause_len=3, rng=None):
    """Generate a random k-SAT instance (satisfy mode, no objective)."""
    rng = rng or random.Random()
    m = Model()
    xs = m.add_variables(n_vars)

    for _ in range(n_clauses):
        clause_vars = rng.sample(range(n_vars), min(clause_len, n_vars))
        literals = []
        for v in clause_vars:
            if rng.random() < 0.5:
                literals.append(xs[v])
            else:
                literals.append(1 - 1 * xs[v])
        m.add_constraint(sum(literals) >= 1)

    m.close()
    return m


def make_random_knapsack(n_vars, rng=None):
    """Generate a random 0-1 knapsack instance (maximize)."""
    rng = rng or random.Random()
    m = Model()
    xs = m.add_variables(n_vars)

    weights = [rng.randint(1, 20) for _ in range(n_vars)]
    values = [rng.randint(1, 30) for _ in range(n_vars)]
    capacity = sum(weights) // 3

    m.add_constraint(sum(xs[i] * weights[i] for i in range(n_vars)) <= capacity)
    m.set_objective(sum(xs[i] * values[i] for i in range(n_vars)), MAXIMIZE)
    m.close()
    return m


def make_random_max_cut(n_vars, edge_prob=0.3, rng=None):
    """Generate a random Max-Cut instance (maximize cut edges)."""
    rng = rng or random.Random()
    m = Model()
    xs = m.add_variables(n_vars)

    # For each edge (i,j), the contribution to cut is x_i(1-x_j) + x_j(1-x_i)
    # = x_i + x_j - 2*x_i*x_j. Since CBQS is linear, we approximate via
    # auxiliary variables or use a penalty encoding. For simplicity, maximize
    # the number of edges where endpoints differ using constraints.
    #
    # Simpler approach: maximize sum of x_i with random subset constraints.
    obj_terms = []
    for i in range(n_vars):
        for j in range(i + 1, n_vars):
            if rng.random() < edge_prob:
                # Penalize same-assignment: add constraint encouraging difference
                w = rng.randint(1, 5)
                obj_terms.append(w * xs[i] + w * xs[j])
                m.add_constraint(xs[i] + xs[j] <= 1 + 0)  # soft via objective

    if obj_terms:
        m.set_objective(sum(obj_terms), MAXIMIZE)
    else:
        m.set_objective(sum(xs[i] for i in range(n_vars)), MAXIMIZE)

    m.close()
    return m


def make_random_set_cover(n_vars, n_sets=None, rng=None):
    """Generate a random weighted set cover instance (minimize)."""
    rng = rng or random.Random()
    n_sets = n_sets or max(n_vars, 5)
    m = Model()
    xs = m.add_variables(n_sets)

    # Each element must be covered by at least one selected set
    for elem in range(n_vars):
        # Each element appears in ~30% of sets
        covering_sets = [s for s in range(n_sets) if rng.random() < 0.3]
        if not covering_sets:
            covering_sets = [rng.randint(0, n_sets - 1)]
        m.add_constraint(sum(xs[s] for s in covering_sets) >= 1)

    # Minimize total cost
    costs = [rng.randint(1, 10) for _ in range(n_sets)]
    m.set_objective(sum(xs[s] * costs[s] for s in range(n_sets)), MINIMIZE)
    m.close()
    return m


GENERATORS = {
    'sat': make_random_sat,
    'knapsack': make_random_knapsack,
    'max_cut': make_random_max_cut,
    'set_cover': make_random_set_cover,
}


# ------------------------------------------------------------------
# Loading pre-generated instances from .in files
# ------------------------------------------------------------------

def load_knapsack_file(filepath):
    """Parse a knapsack .in file and return a CBQS Model.

    Format:
        Line 1: n (number of items)
        Lines 2..n+1: index weight value
        Last line: capacity
    """
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


def load_instances_from_dir(instances_dir, val_fraction=0.2, seed=42,
                            dir_filter=None):
    """Load all .in files from a directory tree and split into train/val.

    Finds all .in files recursively, shuffles them, and splits by val_fraction.
    Returns (train_data, val_data) where each is a list of (problem_type, model).

    Parameters
    ----------
    dir_filter : str or None
        If set, only load from subdirectories whose name contains this
        substring (e.g. ``"g_14"`` to skip g_6 instances).
    """
    base = Path(instances_dir)
    if dir_filter:
        in_files = sorted(
            f for d in base.iterdir()
            if d.is_dir() and dir_filter in d.name
            for f in d.glob('*.in')
        )
    else:
        in_files = sorted(base.rglob('*.in'))
    if not in_files:
        raise FileNotFoundError(f"No .in files found in {instances_dir}"
                                f" (filter={dir_filter!r})")

    rng = random.Random(seed)
    rng.shuffle(in_files)

    models = []
    for f in in_files:
        try:
            model = load_knapsack_file(f)
            models.append(('knapsack', model))
            print(f"  Loaded {f.relative_to(base)} ({model.n} vars)")
        except Exception as e:
            print(f"  Warning: skipping {f}: {e}")

    n_val = max(1, int(len(models) * val_fraction))
    val_data = models[:n_val]
    train_data = models[n_val:]

    print(f"  Total: {len(models)} instances "
          f"({len(train_data)} train, {len(val_data)} val)")
    return train_data, val_data


def generate_instances(n_instances, var_range, problem_types, seed=42):
    """Generate a list of random problem instances.

    Cycles through problem types, sampling variable counts uniformly
    from var_range.
    """
    rng = random.Random(seed)
    models = []

    for i in range(n_instances):
        n_vars = rng.randint(var_range[0], var_range[1])
        prob_type = problem_types[i % len(problem_types)]

        if prob_type == 'sat':
            n_clauses = int(n_vars * 4.2)  # near phase transition
            model = make_random_sat(n_vars, n_clauses, rng=rng)
        elif prob_type == 'knapsack':
            model = make_random_knapsack(n_vars, rng=rng)
        elif prob_type == 'max_cut':
            model = make_random_max_cut(n_vars, rng=rng)
        elif prob_type == 'set_cover':
            model = make_random_set_cover(n_vars, rng=rng)
        else:
            raise ValueError(f"Unknown problem type: {prob_type}")

        models.append((prob_type, model))
        print(f"  [{i+1}/{n_instances}] {prob_type} with {n_vars} vars")

    return models


# ------------------------------------------------------------------
# Training
# ------------------------------------------------------------------

def _make_checkpoint_callback(out_dir, trainer_name):
    """Create a checkpoint callback that saves trainer state periodically."""
    checkpoint_dir = out_dir / trainer_name
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def callback(trainer, elapsed_seconds):
        trainer.save(str(checkpoint_dir))
        print(f"  [checkpoint] {trainer_name} saved at {elapsed_seconds:.0f}s")

    return callback


def train_sat(models, val_models, args, out_dir):
    """Run SAT trainer on the given instances."""
    print(f"\n{'='*60}")
    print(f"  SAT Training: {len(models)} instances, "
          f"{args.n_strategies} strategies/instance")
    print(f"{'='*60}")

    trainer = SATTrainer(
        n_estimators=args.n_estimators,
        n_strategies=args.n_strategies,
        time_budget=args.time_budget,
        signal='constraint_count',
        refit_every=args.refit_every,
        random_state=args.seed,
        target_k=args.target_k,
        checkpoint_callback=_make_checkpoint_callback(out_dir, 'sat'),
        checkpoint_interval=args.checkpoint_interval,
    )

    t0 = time.time()
    trainer.fit(models, validation_models=val_models or None)
    elapsed = time.time() - t0

    print(f"\n  Training complete in {elapsed:.1f}s")
    print(f"  Models processed: {len(models)}")
    print(f"  Refits performed: {len([e for e in trainer.log._events if hasattr(e, 'n_training_models')])}")

    if val_models:
        val_score = trainer.validate(val_models)
        print(f"  Validation score: {val_score:.4f}")

    return trainer


def train_opt(models, val_models, args, out_dir):
    """Run OPT trainer on the given instances (optimization problems only)."""
    print(f"\n{'='*60}")
    print(f"  OPT Training: {len(models)} instances")
    print(f"{'='*60}")

    trainer = OPTTrainer(
        n_estimators=args.n_estimators,
        n_opt_sat_strategies=args.n_strategies,
        top_k=3,
        n_opt_per_candidate=args.n_strategies // 2 or 1,
        screening_budget=args.time_budget,
        full_budget=args.time_budget,
        signal='auc',
        refit_every=args.refit_every,
        random_state=args.seed,
        target_k=args.target_k,
        checkpoint_callback=_make_checkpoint_callback(out_dir, 'opt'),
        checkpoint_interval=args.checkpoint_interval,
    )

    t0 = time.time()
    trainer.fit(models, validation_models=val_models or None)
    elapsed = time.time() - t0

    print(f"\n  Training complete in {elapsed:.1f}s")
    print(f"  Models processed: {len(models)}")

    if val_models:
        val_score = trainer.validate(val_models)
        print(f"  Validation score: {val_score:.4f}")

    return trainer


def train_es(models, val_models, args, out_dir):
    """Run ES trainer on the given instances.

    Parameters
    ----------
    models : list
        Training pool of Model instances.
    val_models : list or None
        Validation pool (passed to ESTrainer.train).
    args : argparse.Namespace
        CLI arguments with es_* fields.
    out_dir : str or Path
        Output directory for saving the predictor.
    """
    out_dir = Path(out_dir)
    print(f"\n{'='*60}")
    print(f"  ES Training: {len(models)} instances, "
          f"{args.es_max_steps} steps")
    print(f"{'='*60}")

    cfg = ESTrainerConfig(
        lr=args.es_lr,
        sigma=args.es_sigma,
        K=args.es_k,
        batch_size=args.es_batch_size,
        max_steps=args.es_max_steps,
        checkpoint_interval=args.es_checkpoint_interval,
        eval_time=args.es_eval_time,
        eval_repeats=args.es_eval_repeats,
        delta_pct=args.es_delta_pct,
        greedy_init=not args.es_no_greedy,
        signal_mode=args.es_signal_mode,
    )

    ckpt_dir = str(out_dir / 'es_checkpoints')
    os.makedirs(ckpt_dir, exist_ok=True)

    log_path = str(out_dir / 'training_log.jsonl')
    trainer = ESTrainer(cfg, checkpoint_dir=ckpt_dir, log_path=log_path)

    t0 = time.time()
    theta = trainer.train(models, val_pool=val_models)
    elapsed = time.time() - t0

    print(f"\n  Training complete in {elapsed:.1f}s")
    print(f"  Steps: {args.es_max_steps}")
    print(f"  Final theta norm: {np.linalg.norm(theta):.6f}")

    # Save predictor
    predictor = PolynomialPredictor(theta, delta_pct=args.es_delta_pct)
    pred_path = str(out_dir / 'es_predictor.npz')
    predictor.save(pred_path)
    print(f"  Saved predictor to {pred_path}")

    return trainer


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def build_parser():
    """Create the argument parser for the training CLI."""
    parser = argparse.ArgumentParser(
        description='Train CBQS ML branching parameter predictors')

    parser.add_argument('--instances-dir', type=str, default=None,
                        help='Directory with pre-generated .in instance files '
                             '(e.g. training/knapsack_instances). '
                             'When set, ignores --n-train, --n-val, --vars, --problems.')
    parser.add_argument('--dir-filter', type=str, default=None,
                        help='Only load subdirectories containing this string '
                             '(e.g. "g_14" to skip easy g_6 instances)')
    parser.add_argument('--val-fraction', type=float, default=0.2,
                        help='Fraction of loaded instances for validation (default: 0.2)')
    parser.add_argument('--n-train', type=int, default=40,
                        help='Number of training instances (default: 40)')
    parser.add_argument('--n-val', type=int, default=5,
                        help='Number of validation instances (default: 5)')
    parser.add_argument('--vars', type=int, nargs=2, default=[5, 65],
                        metavar=('MIN', 'MAX'),
                        help='Variable count range (default: 5 65)')
    parser.add_argument('--problems', nargs='+',
                        default=['knapsack', 'max_cut', 'set_cover'],
                        choices=list(GENERATORS.keys()),
                        help='Problem types to generate')
    parser.add_argument('--mode', choices=['sat', 'opt', 'both', 'es'],
                        default='opt',
                        help='Which trainer to run (default: opt)')
    parser.add_argument('--n-strategies', type=int, default=10,
                        help='Random strategies per instance (default: 10)')
    parser.add_argument('--n-estimators', type=int, default=400,
                        help='Trees per ensemble (default: 200)')
    parser.add_argument('--time-budget', type=float, default=5.0,
                        help='Per-solve time budget in seconds (default: 15)')
    parser.add_argument('--refit-every', type=int, default=5,
                        help='Refit predictor every N models (default: 5)')
    parser.add_argument('--target-k', type=int, default=3,
                        help='Top-k for soft target selection (default: 3)')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed (default: 42)')
    parser.add_argument('--checkpoint-interval', type=float, default=30.0,
                        help='Seconds between checkpoint saves (default: 30)')
    parser.add_argument('--output', type=str, default=None,
                        help='Output directory (default: training/output/<timestamp>)')

    # ES-specific arguments
    parser.add_argument('--es-lr', type=float, default=0.001,
                        help='ES Adam learning rate (default: 0.001)')
    parser.add_argument('--es-sigma', type=float, default=0.02,
                        help='ES perturbation scale (default: 0.02)')
    parser.add_argument('--es-k', type=int, default=20,
                        help='ES antithetic perturbation pairs (default: 20)')
    parser.add_argument('--es-batch-size', type=int, default=3,
                        help='ES instances per step (default: 3)')
    parser.add_argument('--es-max-steps', type=int, default=200,
                        help='ES training steps (default: 200)')
    parser.add_argument('--es-checkpoint-interval', type=int, default=10,
                        help='ES steps between checkpoints (default: 10)')
    parser.add_argument('--es-eval-time', type=float, default=10.0,
                        help='ES solver time budget per eval (default: 10.0)')
    parser.add_argument('--es-eval-repeats', type=int, default=1,
                        help='ES independent solves per evaluation (default: 1)')
    parser.add_argument('--es-delta-pct', type=float, default=0.03,
                        help='ES max bias delta as fraction of n/4 (default: 0.03)')
    parser.add_argument('--es-no-greedy', action='store_true',
                        help='Start from zero solution instead of greedy init')
    parser.add_argument('--es-signal-mode', type=str, default='mean',
                        choices=['mean', 'best_of_k'],
                        help='ES training signal: mean (default) or best_of_k')

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Output directory
    if args.output:
        out_dir = Path(args.output)
    else:
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        out_dir = Path(__file__).parent / 'output' / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"CBQS ML Training")
    print(f"  Output: {out_dir}")
    print(f"  Time budget: {args.time_budget}s per solve")

    # Load or generate instances
    if args.instances_dir:
        print(f"\nLoading instances from {args.instances_dir}...")
        if args.dir_filter:
            print(f"  Filtering directories by: {args.dir_filter!r}")
        train_data, val_data = load_instances_from_dir(
            args.instances_dir, val_fraction=args.val_fraction, seed=args.seed,
            dir_filter=args.dir_filter)
    else:
        print(f"  Problems: {', '.join(args.problems)}")
        print(f"  Variables: {args.vars[0]}-{args.vars[1]}")

        print(f"\nGenerating {args.n_train} training instances...")
        train_data = generate_instances(
            args.n_train, args.vars, args.problems, seed=args.seed)

        print(f"\nGenerating {args.n_val} validation instances...")
        val_data = generate_instances(
            args.n_val, args.vars, args.problems, seed=args.seed + 1000)

    train_models = [m for _, m in train_data]
    val_models = [m for _, m in val_data]

    # Split into SAT-only (no objective) and OPT (has objective)
    sat_train = [m for t, m in train_data]  # SAT trainer works on all
    sat_val = [m for t, m in val_data]

    # OPT trainer needs models with objectives
    opt_train = [m for t, m in train_data if t != 'sat']
    opt_val = [m for t, m in val_data if t != 'sat']

    # Train
    if args.mode in ('sat', 'both'):
        sat_trainer = train_sat(sat_train, sat_val, args, out_dir)
        sat_trainer.save(str(out_dir / 'sat'))
        print(f"  Saved to {out_dir / 'sat'}")

    if args.mode in ('opt', 'both') and opt_train:
        opt_trainer = train_opt(opt_train, opt_val, args, out_dir)
        opt_trainer.save(str(out_dir / 'opt'))
        print(f"  Saved to {out_dir / 'opt'}")
    elif args.mode in ('opt', 'both') and not opt_train:
        print("\n  Skipping OPT training: no optimization instances generated.")
        print("  (Use --problems with knapsack, max_cut, or set_cover)")

    if args.mode == 'es':
        train_es(train_models, val_models, args, out_dir)

    print(f"\nDone. Artifacts saved to {out_dir}")


if __name__ == '__main__':
    main()
