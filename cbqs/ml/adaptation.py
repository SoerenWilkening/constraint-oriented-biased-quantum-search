"""Online adaptive solve with EMA weight updates.

Provides the adaptive_solve() function which runs multiple solve rounds,
improving branching weights between rounds using Exponential Moving Average
(EMA) updates based on a combined reward signal of objective improvement
and constraint satisfaction.
"""
from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from cbqs.ml.training import WeightPredictor, _rank_result


@dataclass
class AdaptiveResult:
    """Result of an adaptive multi-round solve.

    Attributes
    ----------
    best_result : OptimizeResult
        The OptimizeResult from the best-performing round
        (by feasibility-first, objective-tiebreak ranking).
    best_weights : numpy.ndarray
        The branching weights that produced best_result.
    history : list of dict
        Per-round metrics. Each dict contains:
        - 'round' (int): 1-indexed round number
        - 'objective' (int/float): objective value from solve
        - 'feasible' (bool): whether solution was feasible
        - 'reward' (float): combined reward signal value
        - 'weights' (numpy.ndarray): weights used for this round
    n_rounds_completed : int
        Total number of rounds executed.
    """

    best_result: object
    best_weights: np.ndarray
    history: List[Dict]
    n_rounds_completed: int


def _resolve_initial_weights(initial_weights, model, n_vars):
    """Resolve the initial_weights parameter to a concrete weight array.

    Parameters
    ----------
    initial_weights : numpy.ndarray, WeightPredictor, or None
        User-provided initial weights. None defaults to uniform.
    model : Model
        The model being solved (needed if initial_weights is a WeightPredictor).
    n_vars : int
        Expected number of variables.

    Returns
    -------
    numpy.ndarray
        A fresh copy of the resolved weight array (never shares memory
        with user input).

    Raises
    ------
    ValueError
        If initial_weights is an array with wrong length.
    """
    if initial_weights is None:
        return np.ones(n_vars)

    if isinstance(initial_weights, WeightPredictor):
        return initial_weights.predict(model).copy()

    weights = np.array(initial_weights, dtype=np.float64).copy()
    if len(weights) != n_vars:
        raise ValueError(
            f"initial_weights length {len(weights)} != model n_vars {n_vars}"
        )
    return weights


def _compute_reward(current_result, prev_result, current_weights):
    """Compute combined reward signal for EMA weight update.

    Combines two signals:
    1. Feasibility bonus: 1.0 if feasible, 0.0 if not
    2. Objective improvement rate: normalized delta from previous round

    Parameters
    ----------
    current_result : OptimizeResult
        Result from the current round's solve.
    prev_result : OptimizeResult or None
        Result from the previous round (None for first round).
    current_weights : numpy.ndarray
        Current weight array used for this round.

    Returns
    -------
    tuple of (float, numpy.ndarray)
        (reward, reward_adjusted) where reward is the scalar combined
        signal in [0, 1] and reward_adjusted scales current weights
        by the reward value.
    """
    # Feasibility component: binary 0/1
    feasibility = 1.0 if current_result.feasible else 0.0

    # Objective improvement component: normalized to [0, 1]
    if prev_result is not None and prev_result.objective != 0:
        obj_delta = (
            (current_result.objective - prev_result.objective)
            / abs(prev_result.objective)
        )
        obj_improvement = max(0.0, min(1.0, obj_delta))
    else:
        # Neutral for first round or when prev objective is 0
        obj_improvement = 0.5

    # Combined reward: equal weighting of feasibility and improvement
    reward = 0.5 * feasibility + 0.5 * obj_improvement

    # Scale current weights by reward to create adjustment target
    reward_adjusted = reward * current_weights

    return reward, reward_adjusted


def adaptive_solve(model, n_rounds=5, stopping_time=5, num_workers=2,
                   ema_alpha=0.3, seed=None, initial_weights=None,
                   verbose=True):
    """Run a multi-round adaptive solve with EMA weight updates.

    Executes ``n_rounds`` solve rounds, updating branching weights between
    rounds using Exponential Moving Average. The reward signal combines
    objective improvement rate and constraint satisfaction rate.

    Parameters
    ----------
    model : Model
        A closed CBQS Model instance.
    n_rounds : int
        Number of solve rounds to run. Default is 5.
    stopping_time : float
        Solve time budget in seconds per round. Default is 5.
    num_workers : int
        Number of solver threads per round. Default is 2.
    ema_alpha : float
        EMA smoothing factor. Higher values give more weight to reward
        signal. Formula: new = alpha * reward_adjusted + (1 - alpha) * old.
        Default is 0.3.
    seed : int or None
        Random seed for reproducibility. Controls per-round seed derivation.
        Default is None.
    initial_weights : numpy.ndarray, WeightPredictor, or None
        Starting weights. If None, uses uniform weights (np.ones).
        If WeightPredictor, calls predict(model) automatically.
        If ndarray, must have length == n_vars. Always copied.
        Default is None.
    verbose : bool
        If True, prints per-round summary. Default is True.

    Returns
    -------
    AdaptiveResult
        Result containing best_result, best_weights, history, and
        n_rounds_completed.

    Raises
    ------
    ValueError
        If initial_weights has wrong length.

    Examples
    --------
    >>> from cbqs.Model import Model
    >>> from cbqs.ml.adaptation import adaptive_solve
    >>> m = Model()
    >>> xs = m.add_variables(5)
    >>> m.set_objective(sum(xs[i] for i in xs))
    >>> m.add_constraint(sum(xs[i] for i in xs) <= 3)
    >>> m.close()
    >>> result = adaptive_solve(m, n_rounds=3, stopping_time=2, seed=42)
    >>> print(result.best_result.objective)
    """
    n_vars = len(model.variables)

    # Resolve initial weights (always returns a fresh copy)
    current_weights = _resolve_initial_weights(initial_weights, model, n_vars)

    # Save original state for restoration
    original_weights = model.get_param('branching_weights')

    # Deterministic RNG for per-round seed derivation
    rng = np.random.RandomState(seed)

    history = []
    best_result = None
    best_weights = None
    prev_result = None

    try:
        for round_idx in range(n_rounds):
            # Derive per-round seed for solver determinism
            round_seed = int(rng.randint(0, 2**31))
            model.seed = round_seed  # Property, NOT set_param

            # Set solver parameters for this round
            model.set_param('branching_weights', current_weights.copy())
            model.set_param('stopping_time', stopping_time)
            model.set_param('num_workers', num_workers)

            result = model.solve()

            # Compute combined reward signal
            reward, reward_adjusted = _compute_reward(
                result, prev_result, current_weights
            )

            # Track best round (feasibility-first ranking)
            if (best_result is None
                    or _rank_result(result) > _rank_result(best_result)):
                best_result = result
                best_weights = current_weights.copy()

            # Record history entry (copy weights to prevent aliasing)
            history.append({
                'round': round_idx + 1,
                'objective': result.objective,
                'feasible': result.feasible,
                'reward': reward,
                'weights': current_weights.copy(),
            })

            # Verbose per-round summary
            if verbose:
                print(
                    f"Round {round_idx + 1}/{n_rounds}: "
                    f"obj={result.objective}, "
                    f"feasible={result.feasible}, "
                    f"reward={reward:.4f}"
                )

            # EMA weight update (skip after last round)
            if round_idx < n_rounds - 1:
                new_weights = (
                    ema_alpha * reward_adjusted
                    + (1 - ema_alpha) * current_weights
                )
                current_weights = np.clip(new_weights, 0, None)

            prev_result = result

        return AdaptiveResult(
            best_result=best_result,
            best_weights=best_weights,
            history=history,
            n_rounds_completed=n_rounds,
        )

    finally:
        # Restore model's original branching_weights (no side effects)
        model.set_param('branching_weights', original_weights)
