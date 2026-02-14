"""Solver performance benchmarks.

Run with: pytest benchmarks/ --benchmark-json=bench_results.json
Compare: pytest benchmarks/ --benchmark-compare --benchmark-compare-fail=mean:20%

These benchmarks measure solve time for representative constraint satisfaction
and optimization problems of varying sizes. The arena allocation optimizations
in Phase 6 should show measurable improvement in solve time.
"""

import pytest
from .bench_problems import create_small_problem, create_medium_problem, create_large_problem


def setup_model(problem_spec):
    """Create CBQS model from problem specification.

    Args:
        problem_spec: dict with n_vars, constraints, and objective

    Returns:
        Configured Model ready for solve()
    """
    from cbqs.Model import Model
    from cbqs.Constants import MINIMIZE

    model = Model()
    n = problem_spec['n_vars']

    # Create variables - add_variables returns a dict keyed by index
    vars_dict = model.add_variables(n)
    variables = [vars_dict[i] for i in range(n)]

    # Add constraints
    for coeffs, var_indices, sense, rhs in problem_spec['constraints']:
        # Build expression term by term to avoid multiply_constant pitfall
        terms = [c * variables[v] for c, v in zip(coeffs, var_indices)]
        expr = terms[0]
        for term in terms[1:]:
            expr = expr + term

        if sense == 6:  # GREATER
            model.add_constraint(expr >= rhs)
        elif sense == 7:  # LOWER
            model.add_constraint(expr <= rhs)
        else:  # EQUAL
            model.add_constraint(expr == rhs)

    # Add objective
    obj_coeffs, obj_vars = problem_spec['objective']
    obj_terms = [c * variables[v] for c, v in zip(obj_coeffs, obj_vars)]
    obj = obj_terms[0]
    for term in obj_terms[1:]:
        obj = obj + term
    model.set_objective(obj, MINIMIZE)

    # Compile constraints before solving
    model.close()

    return model


class TestSolverBenchmarks:
    """Solver performance benchmarks for different problem sizes."""

    def test_bench_small(self, benchmark):
        """Benchmark small problem (10 vars, 5 constraints).

        Small problems should be very fast and primarily measure
        solver overhead and initialization time.
        """
        problem = create_small_problem(seed=42)
        model = setup_model(problem)

        # Warmup run
        model.set_param('stopping_time', 1)
        model.set_param('num_workers', 1)
        model.solve()

        # Benchmark
        def do_solve():
            model.set_param('stopping_time', 2)
            return model.solve()

        result = benchmark.pedantic(
            do_solve,
            iterations=3,
            rounds=5
        )

        # Basic sanity check - solve returns an OptimizeResult
        from cbqs.result import OptimizeResult
        assert isinstance(result, OptimizeResult)

    def test_bench_medium(self, benchmark):
        """Benchmark medium problem (50 vars, 25 constraints).

        Medium problems exercise the main solver loop more significantly.
        """
        problem = create_medium_problem(seed=42)
        model = setup_model(problem)

        # Warmup
        model.set_param('stopping_time', 1)
        model.set_param('num_workers', 1)
        model.solve()

        def do_solve():
            model.set_param('stopping_time', 3)
            return model.solve()

        result = benchmark.pedantic(
            do_solve,
            iterations=2,
            rounds=3
        )

        from cbqs.result import OptimizeResult
        assert isinstance(result, OptimizeResult)

    def test_bench_large(self, benchmark):
        """Benchmark large problem (200 vars, 100 constraints).

        Large problems should show the most benefit from arena allocation
        optimizations as they involve more memory allocation cycles.
        """
        problem = create_large_problem(seed=42)
        model = setup_model(problem)

        # Warmup
        model.set_param('stopping_time', 2)
        model.set_param('num_workers', 1)
        model.solve()

        def do_solve():
            model.set_param('stopping_time', 5)
            return model.solve()

        result = benchmark.pedantic(
            do_solve,
            iterations=2,
            rounds=3
        )

        from cbqs.result import OptimizeResult
        assert isinstance(result, OptimizeResult)

    def test_bench_dense(self, benchmark):
        """Benchmark dense constraint problem.

        Dense problems have more variables per constraint, increasing
        the memory footprint per constraint evaluation.
        """
        problem = create_medium_problem(dense=True, seed=42)
        model = setup_model(problem)

        model.set_param('stopping_time', 1)
        model.set_param('num_workers', 1)
        model.solve()

        def do_solve():
            model.set_param('stopping_time', 3)
            return model.solve()

        result = benchmark.pedantic(
            do_solve,
            iterations=2,
            rounds=3
        )

        from cbqs.result import OptimizeResult
        assert isinstance(result, OptimizeResult)

    def test_bench_sparse(self, benchmark):
        """Benchmark sparse constraint problem.

        Sparse problems have fewer variables per constraint, which may
        show different allocation patterns.
        """
        problem = create_medium_problem(dense=False, seed=42)
        model = setup_model(problem)

        model.set_param('stopping_time', 1)
        model.set_param('num_workers', 1)
        model.solve()

        def do_solve():
            model.set_param('stopping_time', 3)
            return model.solve()

        result = benchmark.pedantic(
            do_solve,
            iterations=2,
            rounds=3
        )

        from cbqs.result import OptimizeResult
        assert isinstance(result, OptimizeResult)


class TestArenaImpact:
    """Tests specifically measuring arena allocation impact.

    These benchmarks are designed to stress the allocation paths
    that benefit from arena allocation.
    """

    def test_bench_many_constraints(self, benchmark):
        """Benchmark problem with many constraints.

        Problems with many constraints exercise constraint evaluation
        more frequently, which should benefit from arena-based temporary
        allocations.
        """
        from cbqs.Model import Model
        from cbqs.Constants import MINIMIZE

        # Create model with many constraints
        model = Model()
        n = 30
        vars_dict = model.add_variables(n)
        variables = [vars_dict[i] for i in range(n)]

        # Add 50 constraints (high constraint-to-variable ratio)
        import random
        random.seed(42)
        for _ in range(50):
            n_terms = random.randint(2, 5)
            var_indices = random.sample(range(n), n_terms)
            coeffs = [random.randint(-5, 5) for _ in range(n_terms)]
            rhs = random.randint(-10, 10)

            terms = [c * variables[v] for c, v in zip(coeffs, var_indices)]
            expr = terms[0]
            for term in terms[1:]:
                expr = expr + term

            model.add_constraint(expr <= rhs)

        # Simple objective
        obj = variables[0]
        for v in variables[1:10]:
            obj = obj + v
        model.set_objective(obj, MINIMIZE)
        model.close()

        # Warmup
        model.set_param('stopping_time', 1)
        model.set_param('num_workers', 1)
        model.solve()

        def do_solve():
            model.set_param('stopping_time', 3)
            return model.solve()

        result = benchmark.pedantic(
            do_solve,
            iterations=2,
            rounds=3
        )

        # Extra info for benchmark JSON
        benchmark.extra_info['problem_type'] = 'many_constraints'
        benchmark.extra_info['n_vars'] = n
        benchmark.extra_info['n_constraints'] = 50

        from cbqs.result import OptimizeResult
        assert isinstance(result, OptimizeResult)

    def test_bench_parallel_workers(self, benchmark):
        """Benchmark with multiple workers.

        Multiple workers create independent allocation streams,
        testing arena thread isolation.
        """
        problem = create_medium_problem(seed=42)
        model = setup_model(problem)

        # Warmup
        model.set_param('stopping_time', 1)
        model.set_param('num_workers', 2)
        model.solve()

        def do_solve():
            model.set_param('stopping_time', 3)
            return model.solve()

        result = benchmark.pedantic(
            do_solve,
            iterations=2,
            rounds=3
        )

        benchmark.extra_info['problem_type'] = 'parallel_workers'
        benchmark.extra_info['num_workers'] = 2

        from cbqs.result import OptimizeResult
        assert isinstance(result, OptimizeResult)
