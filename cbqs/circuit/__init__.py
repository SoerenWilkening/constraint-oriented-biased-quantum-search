"""
Quantum circuit simulator subpackage for CBQS.

Provides a pure-Python statevector simulator supporting standard quantum
gates, constraint-based oracle construction, and Grover's algorithm
for quantum search over constraint satisfaction problems.
"""
from .simulator import QuantumCircuit
from .gates import H, X, Z, phase_gate

__all__ = [
    "QuantumCircuit",
    "H",
    "X",
    "Z",
    "phase_gate",
]
