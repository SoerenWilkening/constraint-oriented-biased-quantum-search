"""
Quantum circuit simulator subpackage for CBQS.

Provides a pure-Python statevector simulator supporting standard quantum
gates, constraint-based oracle construction, and Grover's algorithm
for quantum search over constraint satisfaction problems.
"""
from .simulator import QuantumCircuit
from .gates import H, X, Z, phase_gate
from .oracle import ConstraintOracle
from .grover import grover_search, optimal_iterations

__all__ = [
    "QuantumCircuit",
    "H",
    "X",
    "Z",
    "phase_gate",
    "ConstraintOracle",
    "grover_search",
    "optimal_iterations",
]
