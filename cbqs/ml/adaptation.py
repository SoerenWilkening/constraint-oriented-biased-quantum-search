"""Online adaptive solve with EMA weight updates.

Provides the adaptive_solve() function which runs multiple solve rounds,
improving branching weights between rounds using Exponential Moving Average
(EMA) updates based on a combined reward signal of objective improvement
and constraint satisfaction.

Supports phase-specific parameters: SAT, OPT_SAT, and OPT phases each
have their own weight arrays, and EMA updates are applied per-phase.

Supports phase-switch: starts with Set A (greedy) parameters and switches
one-time to Set B (exploration) parameters when objective improvement stalls.
"""
from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from cbqs.ml.training import WeightPredictor, _rank_result
from cbqs.ml.phase_params import PHASES


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
        - 'phase' (str): active phase ('sat' or 'opt')
        - 'phase_weights' (dict): per-phase weight arrays
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


def _determine_phase(model):
    """Determine the active solver phase from the model's mode.

    Returns 'sat' for SATISFY mode, 'opt' for OPTIMIZE mode.
    """
    if len(model.obj_expr) > 0:
        return 'opt'
    return 'sat'


def _resolve_phase_weights(initial_phase_params, n_vars):
    """Extract per-phase weight arrays from initial_phase_params dict.

    Parameters
    ----------
    initial_phase_params : dict or None
        Dict with phase-prefixed keys like 'sat_branching_weights',
        'opt_sat_branching_weights', 'opt_branching_weights'.
    n_vars : int
        Expected number of variables.

    Returns
    -------
    dict
        Mapping phase name -> numpy.ndarray of weights.
    """
    phase_weights = {}
    for phase in PHASES:
        key = f'{phase}_branching_weights'
        if initial_phase_params and key in initial_phase_params:
            w = np.array(initial_phase_params[key], dtype=np.float64).copy()
            if len(w) != n_vars:
                raise ValueError(
                    f"{key} length {len(w)} != n_vars {n_vars}"
                )
            phase_weights[phase] = w
        else:
            phase_weights[phase] = np.ones(n_vars)
    return phase_weights


def _active_phases(phase):
    """Return the list of phases to update based on the active solver phase.

    For 'sat', only 'sat' weights are updated.
    For 'opt', both 'opt_sat' and 'opt' weights are updated.
    """
    if phase == 'sat':
        return ['sat']
    return ['opt_sat', 'opt']


def _set_phase_params_on_model(model, phase_weights, phase, initial_phase_params):
    """Set the phase-appropriate branching weights and scalar params on model."""
    active = _active_phases(phase)
    for p in active:
        model.set_param(f'{p}_branching_weights', phase_weights[p].copy())

    # Set scalar phase params if provided
    if initial_phase_params:
        scalar_suffixes = (
            'branching_bias', 'branching_factor', 'bias_factor',
        )
        for p in active:
            for suffix in scalar_suffixes:
                key = f'{p}_{suffix}'
                if key in initial_phase_params:
                    model.set_param(key, initial_phase_params[key])


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
    cur_obj = current_result.objective
    prev_obj = prev_result.objective if prev_result is not None else None
    if (prev_obj is not None and cur_obj is not None
            and prev_obj != 0):
        obj_delta = (cur_obj - prev_obj) / abs(prev_obj)
        obj_improvement = max(0.0, min(1.0, obj_delta))
    else:
        # Neutral for first round, None objectives, or when prev objective is 0
        obj_improvement = 0.5

    # Combined reward: equal weighting of feasibility and improvement
    reward = 0.5 * feasibility + 0.5 * obj_improvement

    # Scale current weights by reward to create adjustment target
    reward_adjusted = reward * current_weights

    return reward, reward_adjusted


def _ema_update_phase_weights(phase_weights, reward, ema_alpha, active_phases):
    """Apply EMA update to the weight arrays for active phases.

    Parameters
    ----------
    phase_weights : dict
        Mapping phase -> numpy.ndarray of current weights.
    reward : float
        Reward signal in [0, 1].
    ema_alpha : float
        EMA smoothing factor.
    active_phases : list of str
        Phases to update.

    Returns
    -------
    dict
        Updated phase_weights (new dict, original not modified).
    """
    updated = {}
    for phase in PHASES:
        if phase in active_phases:
            w = phase_weights[phase]
            reward_adjusted = reward * w
            new_w = ema_alpha * reward_adjusted + (1 - ema_alpha) * w
            updated[phase] = np.clip(new_w, 0, None)
        else:
            updated[phase] = phase_weights[phase].copy()
    return updated


def adaptive_solve(model, n_rounds=5, stopping_time=5, num_workers=2,
                   ema_alpha=0.3, seed=None, initial_weights=None,
                   initial_phase_params=None, verbose=True,
                   exploration_phase_params=None, switch_epsilon=1e-6):
    """Run a multi-round adaptive solve with EMA weight updates.

    Executes ``n_rounds`` solve rounds, updating branching weights between
    rounds using Exponential Moving Average. The reward signal combines
    objective improvement rate and constraint satisfaction rate.

    Supports phase-specific parameters via ``initial_phase_params``.

    Supports phase-switch: when ``exploration_phase_params`` (Set B) is
    provided, the solver starts in a greedy phase using Set A parameters
    (``initial_phase_params``). When objective improvement stalls (relative
    improvement < ``switch_epsilon``), it switches one-time to Set B
    exploration parameters for the remaining rounds.

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
        Starting weights (unprefixed, backwards-compatible). If None, uses
        uniform weights (np.ones). If WeightPredictor, calls predict(model)
        automatically. If ndarray, must have length == n_vars. Always copied.
        Default is None.
    initial_phase_params : dict or None
        Phase-specific initial parameters from SATTrainer.predict() or
        OPTTrainer.predict(). Keys like 'sat_branching_weights',
        'opt_sat_branching_weights', 'opt_branching_weights', etc.
        Overrides initial_weights for the respective phases.
        Default is None.
    verbose : bool
        If True, prints per-round summary. Default is True.
    exploration_phase_params : dict or None
        Set B exploration parameters from ExplorationTrainer.predict().
        When provided, enables phase-switch logic. The solver starts with
        Set A (initial_phase_params) and switches to Set B when stalled.
        Default is None.
    switch_epsilon : float
        Stall detection threshold. A switch is triggered when
        ``(new_best - prev_best) / |prev_best| < switch_epsilon``.
        Default is 1e-6.

    Returns
    -------
    AdaptiveResult
        Result containing best_result, best_weights, history, and
        n_rounds_completed. History entries include 'adaptive_phase'
        ('greedy' or 'exploration') and 'switch_round' (int or None).

    Raises
    ------
    ValueError
        If initial_weights has wrong length.
    """
    n_vars = len(model.variables)

    # Determine active phase from model mode
    phase = _determine_phase(model)
    active = _active_phases(phase)

    # Resolve initial weights (backwards-compatible path)
    current_weights = _resolve_initial_weights(initial_weights, model, n_vars)

    # Resolve per-phase weights
    phase_weights = _resolve_phase_weights(initial_phase_params, n_vars)

    # If no phase params given, use the unprefixed initial_weights for all
    # active phases
    if initial_phase_params is None:
        for p in active:
            phase_weights[p] = current_weights.copy()

    # Save original state for restoration
    original_params = {}
    original_params['branching_weights'] = model.get_param('branching_weights')
    for p in PHASES:
        key = f'{p}_branching_weights'
        try:
            original_params[key] = model.get_param(key)
        except Exception:
            original_params[key] = None

    # Deterministic RNG for per-round seed derivation
    rng = np.random.RandomState(seed)

    # Phase-switch state
    adaptive_phase = 'greedy'  # 'greedy' (Set A) or 'exploration' (Set B)
    switch_round = None  # 1-indexed round when switch occurred, or None
    prev_best_obj = None  # best objective seen so far (for stall detection)

    # Resolve Set B phase weights if provided
    exploration_weights = None
    if exploration_phase_params is not None:
        exploration_weights = _resolve_phase_weights(
            exploration_phase_params, n_vars
        )

    # Track which phase_params dict is active for scalar params
    active_phase_params = initial_phase_params

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
            # Backwards compat: always set unprefixed weights too
            # Use the first active phase's weights as the unprefixed ones
            current_weights = phase_weights[active[0]].copy()
            model.set_param('branching_weights', current_weights.copy())
            model.set_param('stopping_time', stopping_time)
            model.set_param('num_workers', num_workers)

            # Set phase-specific weights on model
            _set_phase_params_on_model(
                model, phase_weights, phase, active_phase_params
            )

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

            # Phase-switch stall detection (after first round)
            cur_obj = result.objective
            if (adaptive_phase == 'greedy'
                    and exploration_weights is not None
                    and prev_best_obj is not None
                    and cur_obj is not None):
                if prev_best_obj == 0:
                    # Avoid division by zero
                    if cur_obj == 0:
                        rel_improvement = 0.0
                    elif cur_obj < prev_best_obj:
                        rel_improvement = float('-inf')
                    else:
                        rel_improvement = float('inf')
                else:
                    rel_improvement = (
                        (cur_obj - prev_best_obj) / abs(prev_best_obj)
                    )
                if rel_improvement < switch_epsilon:
                    adaptive_phase = 'exploration'
                    switch_round = round_idx + 1  # 1-indexed
                    # Switch to Set B weights and params
                    phase_weights = exploration_weights
                    active_phase_params = exploration_phase_params

            # Update prev_best_obj (track best objective for stall detection)
            if cur_obj is not None:
                if prev_best_obj is None or cur_obj > prev_best_obj:
                    prev_best_obj = cur_obj

            # Record history entry (copy weights to prevent aliasing)
            history.append({
                'round': round_idx + 1,
                'objective': result.objective,
                'feasible': result.feasible,
                'reward': reward,
                'weights': current_weights.copy(),
                'phase': phase,
                'phase_weights': {
                    p: phase_weights[p].copy() for p in PHASES
                },
                'adaptive_phase': adaptive_phase,
                'switch_round': switch_round,
            })

            # Verbose per-round summary
            if verbose:
                print(
                    f"Round {round_idx + 1}/{n_rounds}: "
                    f"obj={result.objective}, "
                    f"feasible={result.feasible}, "
                    f"reward={reward:.4f}, "
                    f"phase={phase}, "
                    f"adaptive_phase={adaptive_phase}"
                )

            # EMA weight update per-phase (skip after last round)
            if round_idx < n_rounds - 1:
                phase_weights = _ema_update_phase_weights(
                    phase_weights, reward, ema_alpha, active
                )

            prev_result = result

        return AdaptiveResult(
            best_result=best_result,
            best_weights=best_weights,
            history=history,
            n_rounds_completed=n_rounds,
        )

    finally:
        # Restore model's original branching_weights (no side effects)
        model.set_param('branching_weights', original_params['branching_weights'])
        for p in PHASES:
            key = f'{p}_branching_weights'
            try:
                model.set_param(key, original_params[key])
            except Exception:
                pass
