"""
CMA-ES iterative parameter optimization for CBQS ML pipeline.

Replaces random sampling + regression with CMA-ES search. A regressor
can provide initial distribution mean; CMA-ES refines per instance
using repeated single-thread evaluation (M16).

Provides:
- params_to_vector / vector_to_params: Convert between parameter dicts
  and flat numpy vectors for CMA-ES optimization.
- CMAESOptimizer: Iterative search loop with per-generation logging.
"""

import numpy as np

from cbqs.ml.data_collection import _evaluate_strategy_repeated


# ------------------------------------------------------------------
# Parameter key definitions
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# Vector conversion helpers
# ------------------------------------------------------------------

def _phase_keys(prefix, n_vars):
    """Return ordered list of (key, length) for one phase prefix.

    Layout: weights (n_vars), priorities (n_vars), bias (1),
    branching_factor (1), bias_factor (1).
    """
    return [
        (f'{prefix}_branching_weights', n_vars),
        (f'{prefix}_variable_priorities', n_vars),
        (f'{prefix}_branching_bias', 1),
        (f'{prefix}_branching_factor', 1),
        (f'{prefix}_bias_factor', 1),
    ]


def params_to_vector(params, phase, n_vars):
    """Convert a parameter dict to a flat numpy vector.

    Args:
        params: Parameter dict with phase-prefixed keys.
        phase: 'sat' or 'opt'. For 'opt', includes both opt_sat and opt.
        n_vars: Number of variables in the model.

    Returns:
        numpy.ndarray: Flat vector of all parameter values.
    """
    if phase == 'sat':
        prefixes = ['sat']
    elif phase == 'opt':
        prefixes = ['opt_sat', 'opt']
    else:
        raise ValueError(f"Unknown phase: {phase!r}")

    parts = []
    for prefix in prefixes:
        for key, length in _phase_keys(prefix, n_vars):
            val = params[key]
            if length == 1:
                parts.append([float(val)])
            else:
                parts.append(list(val))

    return np.array([x for sublist in parts for x in sublist], dtype=np.float64)


def vector_to_params(vec, phase, n_vars):
    """Convert a flat numpy vector back to a parameter dict.

    Values are clipped to valid ranges: weights >= 0, bias > -1,
    factors >= 0.

    Args:
        vec: Flat numpy vector.
        phase: 'sat' or 'opt'.
        n_vars: Number of variables in the model.

    Returns:
        dict: Parameter dict with phase-prefixed keys.
    """
    if phase == 'sat':
        prefixes = ['sat']
    elif phase == 'opt':
        prefixes = ['opt_sat', 'opt']
    else:
        raise ValueError(f"Unknown phase: {phase!r}")

    params = {}
    offset = 0
    for prefix in prefixes:
        for key, length in _phase_keys(prefix, n_vars):
            chunk = vec[offset:offset + length]
            offset += length

            if 'branching_weights' in key:
                params[key] = np.clip(chunk, 0.0, None).tolist()
            elif 'variable_priorities' in key:
                params[key] = chunk.tolist()
            elif 'branching_bias' in key:
                params[key] = float(max(chunk[0], -0.99))
            elif 'branching_factor' in key:
                params[key] = float(max(chunk[0], 0.0))
            elif 'bias_factor' in key:
                params[key] = float(max(chunk[0], 0.0))

    return params


def _default_vector(phase, n_vars):
    """Generate a default starting vector for CMA-ES.

    Args:
        phase: 'sat' or 'opt'.
        n_vars: Number of variables.

    Returns:
        numpy.ndarray: Default parameter vector.
    """
    if phase == 'sat':
        prefixes = ['sat']
    else:
        prefixes = ['opt_sat', 'opt']

    parts = []
    for _ in prefixes:
        parts.extend([1.0] * n_vars)       # weights
        parts.extend([0.0] * n_vars)       # priorities
        parts.extend([5.0, 1.0, 1.0])     # bias, branching_factor, bias_factor

    return np.array(parts, dtype=np.float64)


# ------------------------------------------------------------------
# CMA-ES Optimizer
# ------------------------------------------------------------------

class CMAESOptimizer:
    """CMA-ES iterative parameter optimization.

    Uses a simplified CMA-ES algorithm to search the parameter space.
    Each generation samples candidates from a multivariate Gaussian,
    evaluates them with repeated single-thread solves, and updates the
    distribution mean toward the best candidates.

    Args:
        phase: 'sat' or 'opt'.
        pop_size: Number of candidates per generation.
        max_generations: Maximum number of generations.
        sigma0: Initial step size (standard deviation).
        sigma_threshold: Stop early if sigma drops below this.
        min_repeats: Minimum repeated solves per candidate.
        max_repeats: Maximum repeated solves per candidate.
        threshold: Convergence threshold for repeated eval.
        time_budget: Optional time budget per solve.
        random_state: Random seed for reproducibility.
    """

    def __init__(self, phase='sat', pop_size=10, max_generations=20,
                 sigma0=1.0, sigma_threshold=1e-6,
                 min_repeats=10, max_repeats=100, threshold=0.05,
                 time_budget=None, random_state=None):
        self.phase = phase
        self.pop_size = pop_size
        self.max_generations = max_generations
        self.sigma0 = sigma0
        self.sigma_threshold = sigma_threshold
        self.min_repeats = min_repeats
        self.max_repeats = max_repeats
        self.threshold = threshold
        self.time_budget = time_budget
        self._rng = np.random.default_rng(random_state)

    def optimize(self, model, signal_fn, initial_params=None):
        """Run CMA-ES search to find optimal parameters.

        Args:
            model: A closed CBQS model.
            signal_fn: Scoring function that takes an OptimizeResult
                and returns a float (higher is better).
            initial_params: Optional dict of initial parameters to use
                as the distribution mean (warm-start from regressor).

        Returns:
            dict with keys:
                best_params: Best parameter dict found.
                best_signal: Signal value of the best params.
                log: List of per-generation dicts with generation,
                    best_signal, mean_signal, sigma.
        """
        n_vars = model.n

        # Initialize distribution mean
        if initial_params is not None:
            mean = params_to_vector(initial_params, self.phase, n_vars)
        else:
            mean = _default_vector(self.phase, n_vars)

        dim = len(mean)
        sigma = self.sigma0

        # CMA-ES state: diagonal covariance (simplified)
        # Use (1+1)-style rank update on the mean
        n_elite = max(1, self.pop_size // 2)

        global_best_signal = -np.inf
        global_best_params = None
        gen_log = []

        for gen in range(self.max_generations):
            # Check convergence
            if sigma < self.sigma_threshold:
                break

            # Sample population
            candidates = []
            for _ in range(self.pop_size):
                noise = self._rng.standard_normal(dim) * sigma
                candidate_vec = mean + noise
                candidates.append(candidate_vec)

            # Evaluate each candidate
            signals = []
            param_dicts = []
            for vec in candidates:
                params = vector_to_params(vec, self.phase, n_vars)
                param_dicts.append(params)

                entry = _evaluate_strategy_repeated(
                    model, params, signal_fn, self.time_budget,
                    min_repeats=self.min_repeats,
                    max_repeats=self.max_repeats,
                    threshold=self.threshold,
                )
                signals.append(entry['mean_signal'])

            signals = np.array(signals)

            # Rank candidates by signal (descending)
            ranked = np.argsort(-signals)
            elite_indices = ranked[:n_elite]

            # Update mean: weighted average of elite candidates
            elite_vecs = np.array([candidates[i] for i in elite_indices])
            # Simple equal-weight mean of elites
            mean = elite_vecs.mean(axis=0)

            # Update sigma: std of elite vectors around the mean
            elite_diffs = elite_vecs - mean
            new_sigma = np.sqrt(np.mean(elite_diffs ** 2))
            # Smooth sigma update to avoid collapse
            sigma = 0.8 * new_sigma + 0.2 * sigma

            # Track best
            gen_best_idx = ranked[0]
            gen_best_signal = float(signals[gen_best_idx])

            if gen_best_signal > global_best_signal:
                global_best_signal = gen_best_signal
                global_best_params = param_dicts[gen_best_idx]

            gen_log.append({
                'generation': gen,
                'best_signal': float(global_best_signal),
                'mean_signal': float(signals.mean()),
                'sigma': float(sigma),
            })

        return {
            'best_params': global_best_params if global_best_params is not None else {},
            'best_signal': float(global_best_signal) if global_best_params is not None else 0.0,
            'log': gen_log,
        }
