"""
Training signal computation for CBQS ML pipeline.

Provides training signal options:
- AUC (Area Under Incumbent Curve): trapezoidal integration of objective
  value over time from the incumbent history.
- Weighted Combination: score = objective - lambda * time_to_best, with
  a configurable penalty for infeasible solutions.
- Normalized AUC: AUC on per-instance normalized incumbent curve, as
  fraction of ideal (finding best at t=0).
- Composite Signal: normalized_AUC + a * best_normalized_objective,
  where a is derived from within-instance variance (annealing).

A signal factory (make_signal) returns a callable that scores an
OptimizeResult, used by the training pipeline to evaluate parameter
configurations.
"""

import math


def compute_auc(history, total_time):
    """Area under incumbent curve via step-function integration.

    The incumbent curve holds each objective value constant until the next
    improvement arrives. The area is computed as the sum of rectangles:
    value_i * (t_{i+1} - t_i), where the last rectangle extends to
    total_time.

    Args:
        history: list of (objective_value, elapsed_seconds) tuples,
            sorted by time. Each entry represents an improvement.
        total_time: total solve time in seconds, used as the right
            boundary of integration.

    Returns:
        Integrated area (float). Higher is better for maximization.
        Returns 0.0 if history is empty.
    """
    if not history:
        return 0.0

    n = len(history)
    area = 0.0

    for i in range(n):
        value, t_start = history[i]
        if i + 1 < n:
            t_end = history[i + 1][1]
        else:
            t_end = total_time
        area += value * (t_end - t_start)

    return area


def compute_weighted(objective, time_to_best, lam, feasible,
                     infeasible_penalty=-1e6):
    """Weighted combination: objective - lambda * time_to_best.

    Args:
        objective: objective value of the solution.
        time_to_best: time in seconds when the best solution was found.
        lam: lambda weight for the time penalty.
        feasible: whether the solution satisfies all constraints.
        infeasible_penalty: score returned for infeasible solutions.
            Defaults to -1e6.

    Returns:
        Score (float). Higher is better.
    """
    if not feasible:
        return infeasible_penalty

    return objective - lam * time_to_best


def make_signal(name, **kwargs):
    """Factory returning a scoring function from result objects.

    Args:
        name: 'auc' or 'weighted'.
        kwargs: signal-specific parameters. For 'weighted': lam (float),
            optionally infeasible_penalty (float).

    Returns:
        Callable(result) -> float, where result is an OptimizeResult.

    Raises:
        ValueError: if name is not a recognized signal type.
    """
    if name == 'auc':
        return _make_auc_signal(**kwargs)
    elif name == 'weighted':
        return _make_weighted_signal(**kwargs)
    else:
        raise ValueError(f"Unknown signal type: {name!r}. "
                         f"Expected 'auc' or 'weighted'.")


def compute_normalized_auc(history, total_time, best, worst):
    """AUC on normalized incumbent curve, as fraction of ideal.

    Each raw objective value in the history is normalized to [0, 1] via
    (val - worst) / (best - worst), then AUC is computed on the normalized
    curve. The result is divided by (1.0 * total_time) so that a perfect
    run (finding best at t=0) returns 1.0.

    Args:
        history: list of (objective_value, elapsed_seconds) tuples,
            sorted by time.
        total_time: total solve time in seconds.
        best: best known objective value for this instance.
        worst: worst known objective value for this instance.

    Returns:
        Normalized AUC in [0, 1]. Returns 0.0 if history is empty or
        best == worst.
    """
    if not history or total_time <= 0 or best == worst:
        return 0.0

    span = best - worst
    normalized_history = [
        ((val - worst) / span, t) for val, t in history
    ]

    norm_auc = compute_auc(normalized_history, total_time)
    ideal = 1.0 * total_time
    return norm_auc / ideal


def compute_composite_signal(normalized_auc, best_normalized_obj, a):
    """Composite training signal: normalized_AUC + a * best_normalized_objective.

    Args:
        normalized_auc: AUC as fraction of ideal, in [0, 1].
        best_normalized_obj: best objective normalized to [0, 1].
        a: annealing weight for objective quality.

    Returns:
        Composite score (float). Higher is better.
    """
    return normalized_auc + a * best_normalized_obj


def compute_annealing_a(instance_variances, a_min=0.1, a_max=0.9):
    """Derive annealing parameter a from within-instance variance.

    For each instance, variance is the within-instance variance of
    best_objective across sampled parameter configurations. High median
    variance means the training is still discovering what is achievable
    (high a favoring objective quality). Low median variance means
    objectives have converged and focus shifts to speed (low a).

    The mapping uses a sigmoid on log-variance: a = a_min + (a_max - a_min)
    * sigmoid(log(median_variance + eps)).

    Args:
        instance_variances: list of per-instance variance values.
        a_min: minimum a value (default 0.1).
        a_max: maximum a value (default 0.9).

    Returns:
        float in [a_min, a_max]. Returns midpoint if list is empty.
    """
    if not instance_variances:
        return (a_min + a_max) / 2.0

    sorted_vars = sorted(instance_variances)
    n = len(sorted_vars)
    if n % 2 == 1:
        median_var = sorted_vars[n // 2]
    else:
        median_var = (sorted_vars[n // 2 - 1] + sorted_vars[n // 2]) / 2.0

    eps = 1e-12
    log_var = math.log(median_var + eps)
    sigmoid = 1.0 / (1.0 + math.exp(-log_var))

    a = a_min + (a_max - a_min) * sigmoid
    return max(a_min, min(a_max, a))


def _make_auc_signal():
    """Create an AUC scoring function."""

    def score(result):
        total_time = result.solve_time / 1000.0  # ms to seconds
        return compute_auc(result.history, total_time)

    return score


def _make_weighted_signal(lam=1.0, infeasible_penalty=-1e6):
    """Create a weighted combination scoring function.

    Args:
        lam: lambda weight for time penalty.
        infeasible_penalty: score for infeasible solutions.
    """

    def score(result):
        # time_to_best is the time of the last history entry
        if result.history:
            time_to_best = result.history[-1][1]
        else:
            time_to_best = 0.0

        return compute_weighted(
            objective=result.objective,
            time_to_best=time_to_best,
            lam=lam,
            feasible=result.feasible,
            infeasible_penalty=infeasible_penalty,
        )

    return score
