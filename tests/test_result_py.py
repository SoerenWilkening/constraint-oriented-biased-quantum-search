"""
Unit tests for cbqs.result.OptimizeResult.

Tests the pure Python result container in isolation -- no Cython or solver
dependencies required.
"""

import json

import pytest

from cbqs.result import OptimizeResult


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_result(**overrides):
    """Create an OptimizeResult with sensible defaults, overridden by kwargs."""
    defaults = dict(
        solution=[1, 0, 1, 0],
        objective=42.0,
        feasible=True,
        solve_time=100.0,
        preprocessing_time=50.0,
        iterations=5000,
        oracle_calls=250,
        history=[(38.0, 5), (42.0, 20)],  # M0e: (value, oracle:int)
        verified=True,
        violations=None,
        num_threads=4,
        seed=42,
    )
    defaults.update(overrides)
    return OptimizeResult(**defaults)


# ===================================================================
# TestOptimizeResultConstruction
# ===================================================================


class TestOptimizeResultConstruction:
    """Tests for OptimizeResult.__init__ and attribute storage."""

    def test_all_kwargs_stored(self):
        r = _make_result()
        assert r.solution == [1, 0, 1, 0]
        assert r.objective == 42.0
        assert r.feasible is True
        assert r.solve_time == 100.0
        assert r.preprocessing_time == 50.0
        assert r.iterations == 5000
        assert r.oracle_calls == 250
        assert len(r.history) == 2
        assert r.verified is True
        assert r.violations is None
        assert r.num_threads == 4
        assert r.seed == 42

    def test_time_property(self):
        r = _make_result(solve_time=80.0, preprocessing_time=20.0)
        assert r.time == pytest.approx(100.0)

    def test_time_property_zero(self):
        r = _make_result(solve_time=0.0, preprocessing_time=0.0)
        assert r.time == pytest.approx(0.0)

    def test_numpy_array_solution(self):
        np = pytest.importorskip("numpy")
        arr = np.array([1, 0, 1, 0])
        r = _make_result(solution=arr)
        assert hasattr(r.solution, "__len__")
        assert list(r.solution) == [1, 0, 1, 0]

    def test_plain_list_solution(self):
        r = _make_result(solution=[0, 1, 0])
        assert r.solution == [0, 1, 0]

    def test_empty_history(self):
        r = _make_result(history=[])
        assert r.history == []

    def test_verified_none(self):
        r = _make_result(verified=None)
        assert r.verified is None

    def test_violations_none(self):
        r = _make_result(violations=None)
        assert r.violations is None

    def test_violations_list(self):
        viols = ["constraint 1 violated", "bound exceeded"]
        r = _make_result(violations=viols)
        assert r.violations == viols

    def test_keyword_only(self):
        """Constructor must require keyword arguments."""
        with pytest.raises(TypeError):
            OptimizeResult(
                [1, 0], 42.0, True, 10.0, 5.0, 100, 50, [], None, None, 1, 42
            )

    def test_numeric_coercion(self):
        """solve_time/preprocessing_time coerced to float; iterations/oracle_calls to int."""
        r = _make_result(solve_time=100, preprocessing_time=50, iterations=5000.0)
        assert isinstance(r.solve_time, float)
        assert isinstance(r.preprocessing_time, float)
        assert isinstance(r.iterations, int)

    def test_final_incumbents_defaults_empty(self):
        """final_incumbents defaults to [] when not provided (M0e; e.g. local_search)."""
        r = _make_result()
        assert r.final_incumbents == []

    def test_final_incumbents_stored(self):
        """final_incumbents stores the per-worker (value, feasible) list (M0e §8.3)."""
        incs = [(42.0, True), (40.0, True), (0.0, False)]
        r = _make_result(final_incumbents=incs)
        assert r.final_incumbents == incs
        d = r.to_dict()
        assert d["final_incumbents"] == [[42.0, True], [40.0, True], [0.0, False]]
        json.dumps(d)  # must remain JSON-serializable


# ===================================================================
# TestOptimizeResultRepr
# ===================================================================


class TestOptimizeResultRepr:
    """Tests for OptimizeResult.__repr__."""

    def test_format_matches_pattern(self):
        r = _make_result(objective=42.0, feasible=True, iterations=5000)
        s = repr(r)
        assert s.startswith("OptimizeResult(")
        assert "obj=42.0" in s
        assert "feasible=True" in s
        assert "iterations=5000" in s
        assert s.endswith(")")

    def test_repr_with_integer_objective(self):
        r = _make_result(objective=7)
        s = repr(r)
        assert "obj=7" in s

    def test_repr_with_float_objective(self):
        r = _make_result(objective=3.14159)
        s = repr(r)
        assert "obj=3.14159" in s

    def test_repr_with_zero_time(self):
        r = _make_result(solve_time=0.0, preprocessing_time=0.0)
        s = repr(r)
        assert "time=0.00ms" in s

    def test_repr_time_formatting(self):
        r = _make_result(solve_time=1.234, preprocessing_time=0.0)
        s = repr(r)
        assert "time=1.23ms" in s

    def test_repr_is_string(self):
        r = _make_result()
        assert isinstance(repr(r), str)


# ===================================================================
# TestOptimizeResultSummary
# ===================================================================


class TestOptimizeResultSummary:
    """Tests for OptimizeResult.summary()."""

    def test_returns_nonempty_string(self):
        r = _make_result()
        s = r.summary()
        assert isinstance(s, str)
        assert len(s) > 0

    def test_contains_key_fields(self):
        r = _make_result()
        s = r.summary()
        assert "objective" in s.lower()
        assert "feasible" in s.lower()
        assert "solve_time" in s.lower() or "solve time" in s.lower()
        assert "preprocessing_time" in s.lower() or "preprocessing time" in s.lower()
        assert "iterations" in s.lower()
        assert "oracle_calls" in s.lower() or "oracle calls" in s.lower()

    def test_nonempty_history_shows_count(self):
        r = _make_result(history=[(10.0, 1), (20.0, 3)])
        s = r.summary()
        assert "improvements: 2" in s

    def test_empty_history(self):
        r = _make_result(history=[])
        s = r.summary()
        assert "improvements: 0" in s

    def test_verified_true(self):
        r = _make_result(verified=True)
        s = r.summary()
        assert "verified" in s.lower()
        assert "True" in s

    def test_verified_none(self):
        r = _make_result(verified=None)
        s = r.summary()
        assert "not run" in s.lower()

    def test_violations_shown(self):
        r = _make_result(violations=["x1 bound exceeded", "constraint 3 violated"])
        s = r.summary()
        assert "x1 bound exceeded" in s
        assert "constraint 3 violated" in s

    def test_no_violations(self):
        r = _make_result(verified=True, violations=[])
        s = r.summary()
        assert "violations: none" in s.lower()

    def test_summary_contains_seed(self):
        r = _make_result(seed=12345)
        s = r.summary()
        assert "12345" in s

    def test_summary_contains_num_threads(self):
        r = _make_result(num_threads=8)
        s = r.summary()
        assert "8" in s

    def test_long_solution_truncated(self):
        r = _make_result(solution=list(range(50)))
        s = r.summary()
        assert "50 elements" in s

    def test_short_solution_not_truncated(self):
        r = _make_result(solution=[1, 0, 1])
        s = r.summary()
        assert "[1, 0, 1]" in s


# ===================================================================
# TestOptimizeResultToDict
# ===================================================================


class TestOptimizeResultToDict:
    """Tests for OptimizeResult.to_dict()."""

    def test_returns_dict(self):
        r = _make_result()
        d = r.to_dict()
        assert isinstance(d, dict)

    def test_all_keys_present(self):
        r = _make_result()
        d = r.to_dict()
        expected_keys = {
            "solution",
            "objective",
            "feasible",
            "solve_time",
            "preprocessing_time",
            "time",
            "iterations",
            "oracle_calls",
            "history",
            "final_incumbents",
            "worker_histories",  # bd o3f
            "verified",
            "violations",
            "num_threads",
            "seed",
        }
        assert set(d.keys()) == expected_keys

    def test_values_match_constructor(self):
        r = _make_result(
            solution=[1, 0],
            objective=10.0,
            feasible=False,
            solve_time=5.0,
            preprocessing_time=2.0,
            iterations=100,
            oracle_calls=50,
            history=[(5.0, 5)],
            verified=False,
            violations=["v1"],
            num_threads=2,
            seed=99,
        )
        d = r.to_dict()
        assert d["solution"] == [1, 0]
        assert d["objective"] == 10.0
        assert d["feasible"] is False
        assert d["solve_time"] == 5.0
        assert d["preprocessing_time"] == 2.0
        assert d["time"] == 7.0
        assert d["iterations"] == 100
        assert d["oracle_calls"] == 50
        assert d["history"] == [[5.0, 5]]
        assert d["verified"] is False
        assert d["violations"] == ["v1"]
        assert d["num_threads"] == 2
        assert d["seed"] == 99

    def test_json_serializable(self):
        r = _make_result()
        d = r.to_dict()
        # Must not raise
        s = json.dumps(d)
        assert isinstance(s, str)
        # Round-trip
        parsed = json.loads(s)
        assert parsed["objective"] == 42.0

    def test_numpy_array_converted_to_list(self):
        np = pytest.importorskip("numpy")
        arr = np.array([1, 0, 1])
        r = _make_result(solution=arr)
        d = r.to_dict()
        assert isinstance(d["solution"], list)
        assert d["solution"] == [1, 0, 1]
        # Must be JSON-serializable (numpy int64 would fail without conversion)
        json.dumps(d)

    def test_history_tuples_converted_to_lists(self):
        r = _make_result(history=[(2.0, 3), (5.0, 6)])
        d = r.to_dict()
        for entry in d["history"]:
            assert isinstance(entry, list)

    def test_none_violations(self):
        r = _make_result(violations=None)
        d = r.to_dict()
        assert d["violations"] is None

    def test_empty_history(self):
        r = _make_result(history=[])
        d = r.to_dict()
        assert d["history"] == []

    def test_json_round_trip_preserves_types(self):
        r = _make_result()
        d = r.to_dict()
        s = json.dumps(d)
        parsed = json.loads(s)
        assert isinstance(parsed["feasible"], bool)
        assert isinstance(parsed["iterations"], int)
        assert isinstance(parsed["objective"], float)


# ===================================================================
# TestOptimizeResultNoneObjective
# ===================================================================


class TestOptimizeResultNoneObjective:
    """Tests for OptimizeResult with objective=None (SATISFY mode).

    Validates that repr, summary, and to_dict handle None objective
    without crashing, as fixed by Plan 09-01 (CRASH-03/04).
    """

    def test_optimize_result_none_objective(self):
        """OptimizeResult accepts None objective (SATISFY mode)."""
        result = _make_result(objective=None)
        assert result.objective is None
        assert result.feasible is True

    def test_optimize_result_none_objective_repr(self):
        """repr() works with None objective."""
        result = _make_result(objective=None)
        r = repr(result)
        assert "obj=None" in r
        assert "OptimizeResult" in r

    def test_optimize_result_none_objective_summary(self):
        """summary() works with None objective."""
        result = _make_result(
            objective=None,
            history=[(0, 50)],
        )
        s = result.summary()
        assert "None" in s
        assert "CBQS" in s

    def test_optimize_result_none_objective_to_dict(self):
        """to_dict() serializes None objective correctly."""
        result = _make_result(
            objective=None,
            feasible=False,
            verified=True,
            violations=[],
        )
        d = result.to_dict()
        assert d["objective"] is None
        assert d["feasible"] is False
        assert isinstance(d, dict)
        # Must still be JSON-serializable with None
        s = json.dumps(d)
        parsed = json.loads(s)
        assert parsed["objective"] is None
