"""
OptimizeResult -- Pure Python result container for CBQS solver output.

Stores solution, objective, timing, search statistics, and verification
results from solve() and local_search() calls. Designed to be independent
of Cython/C layers for easy inspection, serialization, and testing.

Naming follows scipy.optimize.OptimizeResult convention.
"""


class OptimizeResult:
    """Container for solver optimization results.

    All constructor arguments are keyword-only. This is a plain Python class
    (not a dataclass) to ensure compatibility across Cython and pure Python.

    Parameters
    ----------
    solution : list or numpy.ndarray
        The solution vector.
    objective : float
        Objective value (sign-corrected for user-facing display).
    feasible : bool
        Whether the solution satisfies all constraints.
    solve_time : float
        Solve time in milliseconds.
    preprocessing_time : float
        Preprocessing time in milliseconds.
    iterations : int
        Number of iterations performed.
    oracle_calls : int
        Number of oracle (QTG) calls.
    history : list of tuple
        Best-of-portfolio improvement history. Each entry is
        ``(value, oracle)`` where ``oracle`` is the cumulative per-worker
        oracle count (``ctx->oracle_count``) at which the running
        best-of-portfolio ``value`` was achieved (NORTHSTAR §11 M0e; was
        ``elapsed_seconds`` pre-M0e). ``value`` is the objective for OPTIMIZE
        mode or the constraint satisfaction measure for SATISFY mode.
        The oracle counter is incremented only on the quantum ``solve()``/``ctg``
        path; the classical ``local_search()`` solver issues no oracle queries,
        so its history entries are stamped ``oracle == 0``.
    final_incumbents : list of tuple or None
        Per-worker final incumbents, one ``(value, feasible)`` per portfolio
        worker, used for the §8.3 median-of-P / best-of-P outcome-diversity
        gate. ``None`` (stored as ``[]``) when not produced (e.g. local_search).
    verified : bool or None
        Post-solve verification result. ``None`` if verification was not run.
    violations : list of str or None
        Violation descriptions from verification. ``None`` if not run or
        no violations found.
    num_threads : int
        Number of threads used during the solve.
    seed : int
        Random seed used for reproducibility.
    branch_diagnostics : dict or None
        Opt-phase branching diagnostics pooled across the decorrelated workers
        (M0g / bd 8an.1.7, NORTHSTAR §9). Keys: ``n`` (number of variables),
        ``opt_candidates`` (total candidates ``CSearch_opt`` generated),
        ``radius_mean`` / ``radius_var`` (realized Hamming-radius distribution),
        ``free_fraction`` (``f(n)`` = both-feasible "free" decisions per variable
        per candidate), the raw pooled sums ``opt_flip_sum`` / ``opt_flip_sumsq``
        / ``opt_free_sum`` (so callers can re-pool across seeds/instances), and
        ``per_worker`` (the raw per-worker counter dicts). ``None`` when not
        produced (e.g. the classical ``local_search`` path, which never enters
        the quantum ``opt`` phase).
    """

    __slots__ = (
        "solution",
        "objective",
        "feasible",
        "solve_time",
        "preprocessing_time",
        "iterations",
        "oracle_calls",
        "history",
        "final_incumbents",
        "verified",
        "violations",
        "num_threads",
        "seed",
        "branch_diagnostics",
    )

    def __init__(
        self,
        *,
        solution,
        objective,
        feasible,
        solve_time,
        preprocessing_time,
        iterations,
        oracle_calls,
        history,
        verified,
        violations,
        num_threads,
        seed,
        final_incumbents=None,
        branch_diagnostics=None,
    ):
        self.solution = solution
        self.objective = objective
        self.feasible = feasible
        self.solve_time = float(solve_time)
        self.preprocessing_time = float(preprocessing_time)
        self.iterations = int(iterations)
        self.oracle_calls = int(oracle_calls)
        self.history = history
        self.final_incumbents = final_incumbents if final_incumbents is not None else []
        self.verified = verified
        self.violations = violations
        self.num_threads = int(num_threads)
        self.seed = int(seed)
        self.branch_diagnostics = branch_diagnostics

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def time(self):
        """Total wall-clock time in milliseconds (preprocessing + solve)."""
        return self.preprocessing_time + self.solve_time

    # ------------------------------------------------------------------
    # Representations
    # ------------------------------------------------------------------

    def __repr__(self):
        return (
            f"OptimizeResult("
            f"obj={self.objective}, "
            f"feasible={self.feasible}, "
            f"time={self.time:.2f}ms, "
            f"iterations={self.iterations})"
        )

    def summary(self):
        """Return a multi-line formatted report of all result fields."""
        lines = []
        lines.append("=" * 50)
        lines.append("  CBQS OptimizeResult Summary")
        lines.append("=" * 50)

        # -- Solution section --
        lines.append("")
        lines.append("Solution")
        lines.append("-" * 50)
        sol = self.solution
        try:
            sol_len = len(sol)
        except TypeError:
            sol_len = None

        if sol_len is not None and sol_len > 20:
            # Truncate long solutions
            preview = list(sol[:10])
            lines.append(f"  solution:  [{', '.join(str(v) for v in preview)}, ... ({sol_len} elements)]")
        else:
            lines.append(f"  solution:  {list(sol) if sol_len is not None else sol}")
        lines.append(f"  objective: {self.objective}")
        lines.append(f"  feasible:  {self.feasible}")

        # -- Timing section --
        lines.append("")
        lines.append("Timing")
        lines.append("-" * 50)
        lines.append(f"  preprocessing_time: {self.preprocessing_time:.2f} ms")
        lines.append(f"  solve_time:         {self.solve_time:.2f} ms")
        lines.append(f"  total time:         {self.time:.2f} ms")

        # -- Search section --
        lines.append("")
        lines.append("Search")
        lines.append("-" * 50)
        lines.append(f"  iterations:   {self.iterations}")
        lines.append(f"  oracle_calls: {self.oracle_calls}")

        # -- History section --
        lines.append("")
        lines.append("History")
        lines.append("-" * 50)
        if self.history:
            lines.append(f"  improvements: {len(self.history)}")
            first = self.history[0]
            lines.append(f"  first: value={first[0]}, oracle={first[1]}")
            if len(self.history) > 1:
                last = self.history[-1]
                lines.append(f"  last:  value={last[0]}, oracle={last[1]}")
        else:
            lines.append("  improvements: 0 (no improvement history)")

        # -- Portfolio section --
        if self.final_incumbents:
            lines.append("")
            lines.append("Portfolio (per-worker final incumbents)")
            lines.append("-" * 50)
            feas_vals = [v for (v, f) in self.final_incumbents if f]
            lines.append(f"  workers: {len(self.final_incumbents)}")
            if feas_vals:
                ordered = sorted(feas_vals)
                med = ordered[len(ordered) // 2]
                lines.append(f"  feasible: {len(feas_vals)}  best={max(feas_vals)}  median={med}")
            else:
                lines.append("  feasible: 0")

        # -- Verification section --
        lines.append("")
        lines.append("Verification")
        lines.append("-" * 50)
        if self.verified is None:
            lines.append("  verified: not run")
        else:
            lines.append(f"  verified: {self.verified}")
        if self.violations:
            lines.append(f"  violations ({len(self.violations)}):")
            for v in self.violations:
                lines.append(f"    - {v}")
        elif self.violations is None:
            lines.append("  violations: N/A")
        else:
            lines.append("  violations: none")

        # -- Reproducibility section --
        lines.append("")
        lines.append("Reproducibility")
        lines.append("-" * 50)
        lines.append(f"  num_threads: {self.num_threads}")
        lines.append(f"  seed:        {self.seed}")

        lines.append("")
        lines.append("=" * 50)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self):
        """Return a JSON-serializable dictionary of all fields.

        Numpy arrays are converted to plain Python lists.
        Tuples in history are converted to lists.
        """
        sol = self.solution
        # Convert numpy arrays to lists if numpy is available
        try:
            import numpy as np

            if isinstance(sol, np.ndarray):
                sol = sol.tolist()
        except ImportError:
            pass

        # Ensure solution is a plain list if it has a tolist method
        if hasattr(sol, "tolist") and callable(sol.tolist):
            sol = sol.tolist()

        return {
            "solution": list(sol) if not isinstance(sol, list) else sol,
            "objective": self.objective,
            "feasible": self.feasible,
            "solve_time": self.solve_time,
            "preprocessing_time": self.preprocessing_time,
            "time": self.time,
            "iterations": self.iterations,
            "oracle_calls": self.oracle_calls,
            "history": [list(entry) for entry in self.history] if self.history else [],
            "final_incumbents": [list(entry) for entry in self.final_incumbents] if self.final_incumbents else [],
            "verified": self.verified,
            "violations": self.violations,
            "num_threads": self.num_threads,
            "seed": self.seed,
        }
