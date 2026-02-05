"""Problem generators for benchmarking.

Generates standardized benchmark problems with reproducible random structure.
"""

import random


def create_small_problem(seed=42):
    """Create small benchmark problem.

    Args:
        seed: Random seed for reproducibility (default: 42)

    Returns:
        dict with:
        - n_vars: number of variables
        - constraints: list of (coeffs, vars, sense, rhs) tuples
        - objective: (coeffs, vars) tuple

    Problem size: 10 variables, 5 constraints
    """
    random.seed(seed)
    n = 10
    constraints = []
    for i in range(5):
        # Random constraint with 2-4 variables
        n_terms = random.randint(2, 4)
        var_indices = random.sample(range(n), n_terms)
        coeffs = [random.randint(-5, 5) for _ in range(n_terms)]
        sense = random.choice([6, 7, 8])  # GREATER, LOWER, EQUAL
        rhs = random.randint(-10, 10)
        constraints.append((coeffs, var_indices, sense, rhs))

    # Simple objective: sum of first few variables
    obj_vars = list(range(min(5, n)))
    obj_coeffs = [1] * len(obj_vars)

    return {
        'n_vars': n,
        'constraints': constraints,
        'objective': (obj_coeffs, obj_vars)
    }


def create_medium_problem(dense=False, seed=42):
    """Create medium benchmark problem.

    Args:
        dense: If True, create denser constraints (more variables per constraint)
        seed: Random seed for reproducibility (default: 42)

    Returns:
        dict with problem specification

    Problem size: 50 variables, 25 constraints
    """
    random.seed(seed)
    n = 50
    n_constraints = 25
    constraints = []

    for i in range(n_constraints):
        # More variables per constraint if dense
        n_terms = random.randint(5, 15) if dense else random.randint(2, 6)
        n_terms = min(n_terms, n)
        var_indices = random.sample(range(n), n_terms)
        coeffs = [random.randint(-10, 10) for _ in range(n_terms)]
        sense = random.choice([6, 7, 8])
        rhs = random.randint(-20, 20)
        constraints.append((coeffs, var_indices, sense, rhs))

    obj_vars = list(range(min(20, n)))
    obj_coeffs = [random.randint(1, 5) for _ in obj_vars]

    return {
        'n_vars': n,
        'constraints': constraints,
        'objective': (obj_coeffs, obj_vars)
    }


def create_large_problem(seed=42):
    """Create large benchmark problem.

    Args:
        seed: Random seed for reproducibility (default: 42)

    Returns:
        dict with problem specification

    Problem size: 200 variables, 100 constraints
    """
    random.seed(seed)
    n = 200
    n_constraints = 100
    constraints = []

    for i in range(n_constraints):
        n_terms = random.randint(3, 10)
        var_indices = random.sample(range(n), n_terms)
        coeffs = [random.randint(-20, 20) for _ in range(n_terms)]
        sense = random.choice([6, 7, 8])
        rhs = random.randint(-50, 50)
        constraints.append((coeffs, var_indices, sense, rhs))

    obj_vars = list(range(min(50, n)))
    obj_coeffs = [random.randint(1, 10) for _ in obj_vars]

    return {
        'n_vars': n,
        'constraints': constraints,
        'objective': (obj_coeffs, obj_vars)
    }
