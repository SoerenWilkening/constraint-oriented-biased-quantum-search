"""
Grover's algorithm implementation using the statevector simulator.

Provides the standard Grover search algorithm with a diffusion operator
and optimal iteration calculation. Works with ConstraintOracle for
quantum search over constraint satisfaction problems.
"""
import math
from typing import Optional

from .simulator import QuantumCircuit
from .oracle import ConstraintOracle


def diffusion_operator(circuit: QuantumCircuit) -> None:
    """Apply the Grover diffusion operator (inversion about the mean).

    Implements: 2|s><s| - I, where |s> is the uniform superposition.
    Steps: H on all qubits, X on all qubits, multi-controlled Z
    (flip phase of |11...1>), X on all qubits, H on all qubits.

    The multi-controlled Z is implemented by directly flipping the sign
    of the |11...1> amplitude in the statevector.

    Parameters
    ----------
    circuit : QuantumCircuit
        The circuit to apply the diffusion operator to.
    """
    n = circuit.n_qubits

    # H on all qubits
    for q in range(n):
        circuit.h(q)

    # X on all qubits
    for q in range(n):
        circuit.x(q)

    # Multi-controlled Z: flip phase of |11...1> state
    # |11...1> has index 2^n - 1
    circuit.statevector[2 ** n - 1] *= -1

    # X on all qubits
    for q in range(n):
        circuit.x(q)

    # H on all qubits
    for q in range(n):
        circuit.h(q)


def optimal_iterations(n_states: int, n_solutions: int) -> int:
    """Calculate the optimal number of Grover iterations.

    Parameters
    ----------
    n_states : int
        Total number of basis states (N = 2^n_qubits).
    n_solutions : int
        Number of satisfying states (M).

    Returns
    -------
    int
        Optimal iteration count: floor(pi/4 * sqrt(N/M)).
    """
    if n_solutions <= 0:
        return 1
    return max(1, math.floor(math.pi / 4 * math.sqrt(n_states / n_solutions)))


def grover_search(
    n_qubits: int,
    oracle: ConstraintOracle,
    n_iterations: Optional[int] = None,
) -> QuantumCircuit:
    """Run Grover's quantum search algorithm.

    Creates a quantum circuit in uniform superposition, then applies
    the oracle and diffusion operator for the specified number of
    iterations.

    Parameters
    ----------
    n_qubits : int
        Number of qubits.
    oracle : ConstraintOracle
        Constraint oracle that flips phase of satisfying states.
    n_iterations : int, optional
        Number of Grover iterations. If None, defaults to 1.

    Returns
    -------
    QuantumCircuit
        Circuit after Grover iterations. Inspect with
        ``get_probabilities()`` or ``measure_all()``.
    """
    if n_iterations is None:
        n_iterations = 1

    # Initialize circuit with uniform superposition
    circuit = QuantumCircuit(n_qubits)
    for q in range(n_qubits):
        circuit.h(q)

    # Apply Grover iterations
    for _ in range(n_iterations):
        oracle.apply(circuit)
        diffusion_operator(circuit)

    return circuit
