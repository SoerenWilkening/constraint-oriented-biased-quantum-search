"""
Random parameter sampling and data collection for CBQS ML training.

Provides functions for generating random solver parameters and two
data collector classes:

- SATDataCollector: Samples random SAT-phase parameters, evaluates
  them on a model, and returns the best configuration by training signal.

- OPTDataCollector: Uses Option C strategy -- screen opt_sat candidates
  via quick feasibility evaluation, pair top candidates with random opt
  parameters, and select the best (opt_sat, opt) pair by training signal.

Both collectors support configurable time budgets and training signals.
"""

import numpy as np


# ------------------------------------------------------------------
# Random parameter sampling
# ------------------------------------------------------------------

def random_sat_params(n_vars, rng):
    """Sample random SAT-phase parameters.

    Generates random branching weights, variable priorities, bias,
    branching_factor, and bias_factor suitable for the SAT phase.

    Args:
        n_vars: Number of variables in the model.
        rng: Random number generator instance.

    Returns:
        dict with keys: sat_branching_weights, sat_variable_priorities,
        sat_branching_bias, sat_branching_factor, sat_bias_factor.
    """
    weights = rng.exponential(scale=1.0, size=n_vars).tolist()
    priorities = rng.standard_normal(size=n_vars).tolist()
    # bias > -1; sample from exponential shifted to ensure > -1
    bias = float(rng.exponential(scale=n_vars / 4.0)) - 0.5
    bias = max(bias, -0.99)
    branching_factor = float(rng.exponential(scale=1.0))
    bias_factor = float(rng.exponential(scale=1.0))
    return {
        'sat_branching_weights': weights,
        'sat_variable_priorities': priorities,
        'sat_branching_bias': bias,
        'sat_branching_factor': branching_factor,
        'sat_bias_factor': bias_factor,
    }


def random_opt_sat_params(n_vars, rng):
    """Sample random opt_sat-phase parameters.

    Args:
        n_vars: Number of variables in the model.
        rng: Random number generator instance.

    Returns:
        dict with keys: opt_sat_branching_weights, opt_sat_variable_priorities,
        opt_sat_branching_bias, opt_sat_branching_factor, opt_sat_bias_factor.
    """
    weights = rng.exponential(scale=1.0, size=n_vars).tolist()
    priorities = rng.standard_normal(size=n_vars).tolist()
    bias = float(rng.exponential(scale=n_vars / 4.0)) - 0.5
    bias = max(bias, -0.99)
    branching_factor = float(rng.exponential(scale=1.0))
    bias_factor = float(rng.exponential(scale=1.0))
    return {
        'opt_sat_branching_weights': weights,
        'opt_sat_variable_priorities': priorities,
        'opt_sat_branching_bias': bias,
        'opt_sat_branching_factor': branching_factor,
        'opt_sat_bias_factor': bias_factor,
    }


def random_opt_only_params(n_vars, rng):
    """Sample random opt-phase parameters.

    Args:
        n_vars: Number of variables in the model.
        rng: Random number generator instance.

    Returns:
        dict with keys: opt_branching_weights, opt_variable_priorities,
        opt_branching_bias, opt_branching_factor, opt_bias_factor.
    """
    weights = rng.exponential(scale=1.0, size=n_vars).tolist()
    priorities = rng.standard_normal(size=n_vars).tolist()
    bias = float(rng.exponential(scale=n_vars / 4.0)) - 0.5
    bias = max(bias, -0.99)
    branching_factor = float(rng.exponential(scale=1.0))
    bias_factor = float(rng.exponential(scale=1.0))
    return {
        'opt_branching_weights': weights,
        'opt_variable_priorities': priorities,
        'opt_branching_bias': bias,
        'opt_branching_factor': branching_factor,
        'opt_bias_factor': bias_factor,
    }


def random_opt_params(n_vars, rng):
    """Sample random OPT parameters (opt_sat + opt phases combined).

    Args:
        n_vars: Number of variables in the model.
        rng: Random number generator instance.

    Returns:
        dict with keys: opt_sat_branching_weights, opt_sat_variable_priorities,
        opt_sat_branching_bias, opt_sat_branching_factor, opt_sat_bias_factor,
        opt_branching_weights, opt_variable_priorities,
        opt_branching_bias, opt_branching_factor, opt_bias_factor.
    """
    params = {}
    params.update(random_opt_sat_params(n_vars, rng))
    params.update(random_opt_only_params(n_vars, rng))
    return params


# ------------------------------------------------------------------
# Strategy evaluation
# ------------------------------------------------------------------

def _evaluate_strategy(model, params, signal_fn, time_budget=None):
    """Run solver with given params and score the result.

    Sets params on the model, calls solve(), and evaluates the result
    with the provided signal function.

    Args:
        model: The CBQS model to solve.
        params: Parameter dict to set on the model before solving.
        signal_fn: Scoring function that takes an OptimizeResult and
            returns a float.
        time_budget: Optional time budget in seconds. If set, configures
            stopping_time.

    Returns:
        dict with keys: params, result, signal.
    """
    for key, value in params.items():
        model.set_param(key, value)
    if time_budget is not None:
        model.set_param('stopping_time', int(time_budget))

    result = model.solve()
    score = signal_fn(result)
    return {
        'params': params,
        'result': result,
        'signal': score,
    }


def _evaluate_strategy_repeated(model, params, signal_fn, time_budget=None,
                                min_repeats=10, max_repeats=100,
                                threshold=0.05, epsilon=1e-8):
    """Evaluate a parameter config with repeated single-thread solves.

    Runs at least min_repeats solves. Continues until
    std_of_mean / (best - worst) < threshold, or max_repeats reached.
    If best - worst < epsilon, uses min_repeats.

    Args:
        model: The CBQS model to solve.
        params: Parameter dict to set on the model before solving.
        signal_fn: Scoring function that takes an OptimizeResult and
            returns a float.
        time_budget: Optional time budget in seconds.
        min_repeats: Minimum number of repeated solves.
        max_repeats: Maximum number of repeated solves (hard cap).
        threshold: Convergence threshold for std_of_mean / range.
        epsilon: Minimum range to consider the instance discriminating.

    Returns:
        dict with keys: params, mean_signal, std_signal, n_repeats,
                        raw_signals, raw_results.
    """
    raw_signals = []
    raw_results = []

    # Save original num_workers and force single-thread evaluation
    orig_workers = getattr(model, '_params', {}).get('num_workers', None)
    model.set_param('num_workers', 1)

    for i in range(max_repeats):
        entry = _evaluate_strategy(model, params, signal_fn, time_budget)
        raw_signals.append(entry['signal'])
        raw_results.append(entry['result'])

        n = i + 1
        if n < min_repeats:
            continue

        # Check adaptive stopping
        signals_arr = np.array(raw_signals)
        best = signals_arr.max()
        worst = signals_arr.min()
        spread = best - worst

        # Non-discriminating instance: stop at min_repeats
        if spread < epsilon:
            break

        std = signals_arr.std(ddof=1) if n > 1 else 0.0
        std_of_mean = std / np.sqrt(n)

        if std_of_mean / spread < threshold:
            break

    # Restore original num_workers
    if orig_workers is not None:
        model.set_param('num_workers', orig_workers)

    return {
        'params': params,
        'mean_signal': float(np.mean(raw_signals)),
        'std_signal': float(np.std(raw_signals, ddof=1)) if len(raw_signals) > 1 else 0.0,
        'n_repeats': len(raw_signals),
        'raw_signals': raw_signals,
        'raw_results': raw_results,
    }


# ------------------------------------------------------------------
# SATDataCollector
# ------------------------------------------------------------------

class SATDataCollector:
    """Collect training data for SAT trainer.

    Samples random SAT parameter vectors, evaluates each on the given
    model, and returns the best configuration by training signal.

    Args:
        n_strategies: Number of random parameter configurations to try.
        time_budget: Optional per-solve time budget in seconds.
        signal_fn: Scoring function: takes OptimizeResult, returns float.
        random_state: Random seed for reproducibility.
        single_thread: If True, use repeated single-thread evaluation.
        min_repeats: Minimum repeated solves per config (single_thread mode).
        max_repeats: Maximum repeated solves per config (single_thread mode).
        threshold: Convergence threshold for adaptive stopping.
    """

    def __init__(self, n_strategies=10, time_budget=None,
                 signal_fn=None, random_state=None,
                 single_thread=True, min_repeats=10,
                 max_repeats=100, threshold=0.05):
        self.n_strategies = n_strategies
        self.time_budget = time_budget
        self.signal_fn = signal_fn or (lambda r: r.objective)
        self._rng = np.random.default_rng(random_state)
        self.single_thread = single_thread
        self.min_repeats = min_repeats
        self.max_repeats = max_repeats
        self.threshold = threshold

    def collect(self, model):
        """Collect SAT training data for a model.

        Samples n_strategies random SAT parameter vectors, evaluates
        each, and returns the best by signal. When single_thread is
        True, uses repeated single-thread evaluation with adaptive
        stopping.

        Args:
            model: A closed CBQS model.

        Returns:
            dict with keys: best_params, best_signal, all_results.
            best_params is the parameter dict of the best strategy.
            best_signal is the signal value of the best strategy.
            all_results is a list of dicts with params, result, signal.
        """
        n_vars = model.n
        all_results = []

        for _ in range(self.n_strategies):
            params = random_sat_params(n_vars, self._rng)
            if self.single_thread:
                entry = _evaluate_strategy_repeated(
                    model, params, self.signal_fn, self.time_budget,
                    min_repeats=self.min_repeats,
                    max_repeats=self.max_repeats,
                    threshold=self.threshold,
                )
                entry['signal'] = entry['mean_signal']
            else:
                entry = _evaluate_strategy(
                    model, params, self.signal_fn, self.time_budget,
                )
            all_results.append(entry)

        # Select best by signal
        best_idx = max(range(len(all_results)),
                       key=lambda i: all_results[i]['signal'])
        best = all_results[best_idx]

        return {
            'best_params': best['params'],
            'best_signal': best['signal'],
            'all_results': all_results,
        }


# ------------------------------------------------------------------
# OPTDataCollector (Option C)
# ------------------------------------------------------------------

class OPTDataCollector:
    """Collect training data for OPT trainer using Option C.

    Option C strategy:
    1. Sample N random opt_sat parameter vectors.
    2. Quick feasibility screening: evaluate each with a short budget.
    3. Select top K opt_sat candidates by screening signal.
    4. For each of K candidates, sample M opt parameter vectors and
       run full solve with the (opt_sat, opt) pair.
    5. Return the best pair by training signal.

    For trivially feasible models, opt_sat screening is skipped and
    only opt parameters are sampled.

    Args:
        n_opt_sat: Number of opt_sat candidates to screen.
        top_k: Number of top candidates to keep from screening.
        n_opt_per_candidate: Number of opt parameter vectors to try
            per candidate.
        screening_budget: Time budget in seconds for each screening solve.
        full_budget: Time budget in seconds for each full solve.
        signal_fn: Scoring function for full solves.
        screening_signal_fn: Scoring function for screening. If None,
            uses signal_fn.
        random_state: Random seed for reproducibility.
        single_thread: If True, use repeated single-thread evaluation.
        min_repeats: Minimum repeated solves per config (single_thread mode).
        max_repeats: Maximum repeated solves per config (single_thread mode).
        threshold: Convergence threshold for adaptive stopping.
    """

    def __init__(self, n_opt_sat=10, top_k=3, n_opt_per_candidate=5,
                 screening_budget=None, full_budget=None,
                 signal_fn=None, screening_signal_fn=None,
                 random_state=None, single_thread=True,
                 min_repeats=10, max_repeats=100, threshold=0.05):
        self.n_opt_sat = n_opt_sat
        self.top_k = top_k
        self.n_opt_per_candidate = n_opt_per_candidate
        self.screening_budget = screening_budget
        self.full_budget = full_budget
        self.signal_fn = signal_fn or (lambda r: r.objective)
        self.screening_signal_fn = screening_signal_fn or self.signal_fn
        self._rng = np.random.default_rng(random_state)
        self.single_thread = single_thread
        self.min_repeats = min_repeats
        self.max_repeats = max_repeats
        self.threshold = threshold

    def collect(self, model):
        """Collect OPT training data using Option C.

        Args:
            model: A closed CBQS model.

        Returns:
            dict with keys: best_opt_sat_params, best_opt_params,
            best_signal, trivially_feasible, all_results.
        """
        trivially_feasible = self._is_trivially_feasible(model)

        if trivially_feasible:
            return self._collect_trivially_feasible(model)

        # Phase 1: Screen opt_sat candidates
        candidates = self._screen_opt_sat(model)

        # Phase 2: Pair top candidates with opt params
        pair_results = self._evaluate_pairs(model, candidates)

        if not pair_results:
            return {
                'best_opt_sat_params': None,
                'best_opt_params': None,
                'best_signal': None,
                'trivially_feasible': False,
                'all_results': [],
            }

        # Select best pair
        best_idx = max(range(len(pair_results)),
                       key=lambda i: pair_results[i]['signal'])
        best = pair_results[best_idx]

        return {
            'best_opt_sat_params': best['opt_sat_params'],
            'best_opt_params': best['opt_params'],
            'best_signal': best['signal'],
            'trivially_feasible': False,
            'all_results': pair_results,
        }

    def _is_trivially_feasible(self, model):
        """Check if a model is trivially feasible.

        A model is trivially feasible if it was explicitly marked as such,
        typically because all constraints are satisfied by a zero solution.

        Args:
            model: The model to check.

        Returns:
            bool indicating whether the model is trivially feasible.
        """
        return getattr(model, '_trivially_feasible', False)

    def _collect_trivially_feasible(self, model):
        """Collect data for a trivially feasible model.

        Skips opt_sat screening and only samples opt parameters.

        Args:
            model: A trivially feasible model.

        Returns:
            dict with keys: best_opt_sat_params, best_opt_params,
            best_signal, trivially_feasible, all_results.
        """
        n_vars = model.n
        all_results = []
        n_total = self.top_k * self.n_opt_per_candidate

        for _ in range(n_total):
            opt_params = random_opt_only_params(n_vars, self._rng)
            if self.single_thread:
                entry = _evaluate_strategy_repeated(
                    model, opt_params, self.signal_fn, self.full_budget,
                    min_repeats=self.min_repeats,
                    max_repeats=self.max_repeats,
                    threshold=self.threshold,
                )
                entry['signal'] = entry['mean_signal']
            else:
                entry = _evaluate_strategy(
                    model, opt_params, self.signal_fn, self.full_budget,
                )
            entry['opt_sat_params'] = None
            entry['opt_params'] = opt_params
            all_results.append(entry)

        if not all_results:
            return {
                'best_opt_sat_params': None,
                'best_opt_params': None,
                'best_signal': None,
                'trivially_feasible': True,
                'all_results': [],
            }

        best_idx = max(range(len(all_results)),
                       key=lambda i: all_results[i]['signal'])
        best = all_results[best_idx]

        return {
            'best_opt_sat_params': None,
            'best_opt_params': best['opt_params'],
            'best_signal': best['signal'],
            'trivially_feasible': True,
            'all_results': all_results,
        }

    def _screen_opt_sat(self, model):
        """Screen opt_sat candidates via quick feasibility evaluation.

        Samples n_opt_sat random opt_sat parameter vectors, evaluates
        each with a short budget, and returns the top_k by screening
        signal.

        Args:
            model: The model to screen.

        Returns:
            list of dict, top K candidates. Each dict has keys: params,
            result, signal.
        """
        n_vars = model.n
        screening_results = []

        for _ in range(self.n_opt_sat):
            params = random_opt_sat_params(n_vars, self._rng)
            entry = _evaluate_strategy(
                model, params, self.screening_signal_fn,
                self.screening_budget,
            )
            screening_results.append(entry)

        # Sort by signal descending, take top_k
        screening_results.sort(key=lambda e: e['signal'], reverse=True)
        top_k = min(self.top_k, len(screening_results))
        return screening_results[:top_k]

    def _evaluate_pairs(self, model, opt_sat_candidates):
        """Evaluate (opt_sat, opt) parameter pairs.

        For each opt_sat candidate, samples n_opt_per_candidate random
        opt parameter vectors and evaluates the combination.

        Args:
            model: The model to solve.
            opt_sat_candidates: Top opt_sat candidates from screening.

        Returns:
            list of dict, each with keys: opt_sat_params, opt_params,
            result, signal.
        """
        n_vars = model.n
        pair_results = []

        for candidate in opt_sat_candidates:
            opt_sat_params = candidate['params']

            for _ in range(self.n_opt_per_candidate):
                opt_params = random_opt_only_params(n_vars, self._rng)

                # Combine opt_sat and opt params
                combined = {}
                combined.update(opt_sat_params)
                combined.update(opt_params)

                if self.single_thread:
                    entry = _evaluate_strategy_repeated(
                        model, combined, self.signal_fn, self.full_budget,
                        min_repeats=self.min_repeats,
                        max_repeats=self.max_repeats,
                        threshold=self.threshold,
                    )
                    entry['signal'] = entry['mean_signal']
                else:
                    entry = _evaluate_strategy(
                        model, combined, self.signal_fn, self.full_budget,
                    )
                entry['opt_sat_params'] = opt_sat_params
                entry['opt_params'] = opt_params
                pair_results.append(entry)

        return pair_results
