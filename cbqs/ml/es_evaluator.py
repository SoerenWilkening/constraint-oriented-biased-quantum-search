"""ES evaluation functions: wire PolynomialPredictor to the CBQS solver.

Provides evaluate() which creates a PolynomialPredictor from a theta vector,
sets predicted parameters on a Model, runs solve(), and returns a training
signal tuple (best_objective, -time_to_best). Also provides normalize_signals()
for per-instance zero-mean unit-variance normalization of signal differences
before gradient aggregation.
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

    The signal is a 2-tuple for lexicographic comparison:
    - First element: best objective value (higher is better).
    - Second element: negative time-to-best (faster is better as tiebreaker).

    Parameters
    ----------
    result : OptimizeResult
        Solver result from model.solve().

    Returns
    -------
    tuple of (float, float)
        (best_objective, -time_to_best).
    """
    best_objective = float(result.objective)
    if result.history:
        time_to_best = float(result.history[-1][1])
    else:
        time_to_best = 0.0
    return (best_objective, -time_to_best)


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


def evaluate(theta, model, time_budget):
    """Evaluate a theta vector on a model instance.

    Creates a PolynomialPredictor from theta, predicts solver parameters,
    sets them on the model, runs solve(), and returns the training signal.

    Parameters
    ----------
    theta : numpy.ndarray
        Flat coefficient vector of shape (THETA_SIZE,).
    model : Model
        A closed CBQS Model instance (or FakeModel for testing).
    time_budget : int or float
        Solve time budget in seconds, set as stopping_time.

    Returns
    -------
    tuple of (float, float)
        Training signal: (best_objective, -time_to_best).
    """
    # Create predictor and get parameters
    predictor = PolynomialPredictor(theta)
    params = predictor.predict(model)

    # Set time budget
    model.set_param('stopping_time', int(time_budget))

    # Set predicted parameters on model
    model.set_param('branching_weights', params['branching_weights'])
    model.set_param('branching_bias', params['branching_bias'])
    model.set_param('branching_factor', params['branching_factor'])
    model.set_param('bias_factor', params['bias_factor'])

    # variable_priorities: set if the solver supports it (phase-specific param,
    # may not be wired yet). Skip silently if not available.
    priorities = params['variable_priorities']
    for name in ('variable_priorities',
                 'sat_variable_priorities', 'opt_sat_variable_priorities',
                 'opt_variable_priorities'):
        try:
            model.set_param(name, priorities)
        except ValueError:
            pass

    # Install a manual callback to track best objective and time-to-best,
    # bypassing the broken built-in history callback.
    cb, state = _make_history_callback(model)
    model.set_param('callback', cb)

    # Solve
    result = model.solve()

    # Build signal from callback state (falls back to result.objective_value)
    best_obj = state['best_objective']
    if best_obj is None:
        best_obj = float(model.objective_value or 0)
    time_to_best = state['time_to_best']
    return (float(best_obj), -float(time_to_best))
