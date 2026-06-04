"""
Pytest configuration and shared fixtures for cbqs test suite.

Prerequisites:
    The cbqs package must be compiled and installed before running tests:
        CC=gcc python3 setup.py build_ext --inplace
    or:
        pip install -e .
"""
import pytest


@pytest.fixture(autouse=True)
def _cap_default_oracle_budget(request):
    """Keep the suite fast under the bd 8an.1.4 (M0d) oracle-budget change.

    solve()'s default ``M`` is now the full per-worker oracle budget
    ``T(n) = (n/4)**2 + 1200`` and the wall-clock stop is disabled, so a default
    solve runs >=1206 oracles regardless of ``stopping_time`` (correct in
    production, but ~15x slower across the suite). Cap the *default* ``M`` so
    default-budget solves stay fast in tests.

    Tests that must exercise the real ``T(n)`` budget opt in with
    ``set_param('M', -1)``: an explicit ``-1`` overrides this capped default and
    re-triggers the ``T(n)`` formula in ``solve()``. Tests that set ``M`` to any
    other value are unaffected. ``test_set_param`` asserts the documented default
    (``-1``), so it is exempted from the cap.
    """
    import sys
    if request.module.__name__ == "test_set_param":
        yield
        return
    param_defs = sys.modules["cbqs.Model"]._PARAM_DEFS
    original = param_defs["M"]["default"]
    param_defs["M"]["default"] = 200
    try:
        yield
    finally:
        param_defs["M"]["default"] = original


@pytest.fixture
def simple_model():
    """Create a fresh Model instance for tests that need one."""
    from cbqs.Model import Model
    m = Model()
    return m


@pytest.fixture
def five_var_model():
    """Create a Model with 5 binary variables already added."""
    from cbqs.Model import Model
    m = Model()
    xs = m.add_variables(5)
    return m, xs
