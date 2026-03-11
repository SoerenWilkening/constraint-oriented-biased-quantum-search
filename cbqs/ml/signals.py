"""
Training signal computation for CBQS ML pipeline.

Provides two training signal options:
- AUC (Area Under Incumbent Curve): trapezoidal integration of objective
  value over time from the incumbent history.
- Weighted Combination: score = objective - lambda * time_to_best, with
  a configurable penalty for infeasible solutions.

A signal factory (make_signal) returns a callable that scores an
OptimizeResult, used by the training pipeline to evaluate parameter
configurations.
"""


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
