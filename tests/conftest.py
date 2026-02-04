"""
Pytest configuration and shared fixtures for cbqs test suite.

Prerequisites:
    The cbqs package must be compiled and installed before running tests:
        CC=gcc python3 setup.py build_ext --inplace
    or:
        pip install -e .
"""
import pytest


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
