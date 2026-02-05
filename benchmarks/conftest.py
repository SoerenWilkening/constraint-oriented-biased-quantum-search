"""Benchmark fixtures for CBQS solver performance testing.

Provides pytest fixtures for small, medium, and large benchmark problems.
"""

import pytest
from .bench_problems import create_small_problem, create_medium_problem, create_large_problem


@pytest.fixture
def small_problem():
    """Small problem: 10 variables, 5 constraints."""
    return create_small_problem()


@pytest.fixture
def medium_problem():
    """Medium problem: 50 variables, 25 constraints."""
    return create_medium_problem()


@pytest.fixture
def large_problem():
    """Large problem: 200 variables, 100 constraints."""
    return create_large_problem()


@pytest.fixture
def dense_problem():
    """Dense problem: high constraint density."""
    return create_medium_problem(dense=True)


@pytest.fixture
def sparse_problem():
    """Sparse problem: low constraint density."""
    return create_medium_problem(dense=False)
