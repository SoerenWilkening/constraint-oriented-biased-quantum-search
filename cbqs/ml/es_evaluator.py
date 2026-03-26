"""ES evaluation functions: wire PolynomialPredictor to the CBQS solver.

Provides evaluate() which creates a PolynomialPredictor from a theta vector,
sets predicted parameters on a Model, runs solve(), and returns a scalar
training signal (best objective value, higher is better).

Also provides normalize_signals() for per-instance zero-mean unit-variance
normalization of signal differences before gradient aggregation.
"""
import numpy as np

from cbqs.ml.polynomial import PolynomialPredictor

def _make_history_callback(model):
    """Create a callback that tracks the best objective and time-to-best.

    Uses model.objective_value and model.runtime to read the current
    incumbent and elapsed time during solve. Bypasses the built-in
    history tracking which has a known bug in SearchLib.pyx.

    The callback takes no arguments (solver convention) and captures
    the model via closure.

    Returns
    -------
    tuple of (callable, dict)
        The callback function and a state dict with 'best_objective'
        and 'time_to_best' keys, updated in-place by the callback.
    """
    state = {'best_objective': None, 'time_to_best': 0.0}

    def callback():
        obj = model.objective_value
        if obj is None:
            return
        if state['best_objective'] is None or obj > state['best_objective']:
            state['best_objective'] = obj
            state['time_to_best'] = model.runtime

    return callback, state


def extract_signal(result):
    """Extract the ES training signal from a solver result.

    Parameters
    ----------
    result : OptimizeResult
        Solver result from model.solve().

    Returns
    -------
    float
        Best objective value (higher is better).
    """
    return float(result.objective)


def normalize_signals(diffs):
    """Normalize signal differences to zero mean and unit variance.

    Used per-instance to normalize the signal differences across K
    perturbation pairs before gradient aggregation. This ensures that
    instances with different objective scales contribute equally.

    Parameters
    ----------
    diffs : array-like
        Signal differences, shape (K,). Can be a list or numpy array.

    Returns
    -------
    numpy.ndarray
        Normalized differences with zero mean and unit variance.
        If the standard deviation is zero (constant input), returns
        an array of zeros.
    """
    diffs = np.asarray(diffs, dtype=np.float64)
    mean = np.mean(diffs)
    std = np.std(diffs)
    return (diffs - mean) / (std + 1e-8)


def _single_solve(model, theta, time_budget, seed=None, greedy_init=True):
    """Run a single solve and return (best_objective, time_to_best).

    Resets the model, optionally runs greedy init, sets predicted
    parameters, and solves once.
    """
    model.reset()

    if greedy_init:
        model.general_greedy()

    if seed is not None:
        model.seed = seed

    predictor = PolynomialPredictor(theta)
    params = predictor.predict(model)

    model.set_param('stopping_time', float(time_budget))

    from cbqs.SearchLib import set_predicted_params
    n = len(model.variables)
    set_predicted_params(
        model,
        params['branching_bias'],
        params['branching_factor'],
        params['bias_factor'],
        params['branching_weights'],
        params['variable_priorities'],
        n,
    )

    cb, state = _make_history_callback(model)
    model.set_param('callback', cb)

    model.solve()

    best_obj = state['best_objective']
    if best_obj is None:
        best_obj = float(model.objective_value or 0)
    time_to_best = state['time_to_best']
    return (float(best_obj), float(time_to_best))


def evaluate(theta, model, time_budget, seed=None, repeats=10,
             greedy_init=True, **kwargs):
    """Evaluate a theta vector on a model instance.

    Runs the solver ``repeats`` times, each with ``time_budget / repeats``
    seconds, and returns the mean objective value.

    Parameters
    ----------
    theta : numpy.ndarray
        Flat coefficient vector of shape (THETA_SIZE,).
    model : Model
        A closed CBQS Model instance (or FakeModel for testing).
    time_budget : int or float
        Total solve time budget in seconds, split across repeats.
    seed : int or None
        Base random seed. When provided, each repeat uses a
        deterministic derived seed (seed + i). When the same base
        seed is used for antithetic pairs (theta_plus / theta_minus),
        each repeat pair shares the same solver randomness.
    repeats : int
        Number of independent solves to average over (default: 10).
    greedy_init : bool
        Whether to initialise from greedy before solving (default: True).

    Returns
    -------
    float
        Mean objective value across repeats (higher is better).
    """
    per_solve_budget = time_budget / repeats
    objectives = []

    for i in range(repeats):
        rep_seed = (seed + i) if seed is not None else None
        obj, _ttb = _single_solve(model, theta, per_solve_budget,
                                  seed=rep_seed, greedy_init=greedy_init)
        objectives.append(obj)

    return float(np.mean(objectives))
