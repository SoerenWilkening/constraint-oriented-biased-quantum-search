"""
Statevector quantum circuit simulator.

Provides a QuantumCircuit class that maintains a statevector and supports
applying quantum gates, measuring, and inspecting probabilities. Uses
big-endian qubit ordering: qubit 0 is the most significant bit.
"""
import numpy as np
from typing import List, Optional

from .gates import (
    H, X, Z, phase_gate,
    apply_single_qubit_gate, apply_cnot, apply_toffoli,
)


class QuantumCircuit:
    """A pure-Python statevector quantum circuit simulator.

    Maintains a complex statevector of dimension 2^n and supports applying
    standard quantum gates and performing measurements.

    Parameters
    ----------
    n_qubits : int
        Number of qubits in the circuit.

    Attributes
    ----------
    n_qubits : int
        Number of qubits.
    statevector : np.ndarray
        Current complex statevector of length 2^n_qubits.
    """

    def __init__(self, n_qubits: int):
        if n_qubits < 1:
            raise ValueError("n_qubits must be at least 1")
        self.n_qubits = n_qubits
        self.statevector = np.zeros(2 ** n_qubits, dtype=complex)
        self.statevector[0] = 1.0 + 0j

    def h(self, qubit: int) -> None:
        """Apply Hadamard gate to the specified qubit.

        Parameters
        ----------
        qubit : int
            Target qubit index.
        """
        self.statevector = apply_single_qubit_gate(
            self.statevector, H, qubit, self.n_qubits
        )

    def x(self, qubit: int) -> None:
        """Apply Pauli-X (bit flip) gate to the specified qubit.

        Parameters
        ----------
        qubit : int
            Target qubit index.
        """
        self.statevector = apply_single_qubit_gate(
            self.statevector, X, qubit, self.n_qubits
        )

    def z(self, qubit: int) -> None:
        """Apply Pauli-Z (phase flip) gate to the specified qubit.

        Parameters
        ----------
        qubit : int
            Target qubit index.
        """
        self.statevector = apply_single_qubit_gate(
            self.statevector, Z, qubit, self.n_qubits
        )

    def phase(self, qubit: int, theta: float) -> None:
        """Apply a phase rotation gate to the specified qubit.

        Parameters
        ----------
        qubit : int
            Target qubit index.
        theta : float
            Rotation angle in radians.
        """
        pg = phase_gate(theta)
        self.statevector = apply_single_qubit_gate(
            self.statevector, pg, qubit, self.n_qubits
        )

    def cx(self, control: int, target: int) -> None:
        """Apply CNOT gate.

        Parameters
        ----------
        control : int
            Control qubit index.
        target : int
            Target qubit index.
        """
        self.statevector = apply_cnot(
            self.statevector, control, target, self.n_qubits
        )

    def ccx(self, control1: int, control2: int, target: int) -> None:
        """Apply Toffoli (CCX) gate.

        Parameters
        ----------
        control1 : int
            First control qubit index.
        control2 : int
            Second control qubit index.
        target : int
            Target qubit index.
        """
        self.statevector = apply_toffoli(
            self.statevector, control1, control2, target, self.n_qubits
        )

    def get_statevector(self) -> np.ndarray:
        """Return a copy of the current statevector.

        Returns
        -------
        np.ndarray
            Copy of the complex statevector.
        """
        return self.statevector.copy()

    def get_probabilities(self) -> np.ndarray:
        """Return measurement probabilities for each basis state.

        Returns
        -------
        np.ndarray
            Array of |amplitude|^2 values for each basis state.
        """
        return np.abs(self.statevector) ** 2

    def measure_all(self) -> List[int]:
        """Sample one measurement outcome from the statevector.

        Collapses the state probabilistically and returns the measured
        bit values for each qubit in big-endian order.

        Returns
        -------
        list[int]
            List of bit values [q0, q1, ..., q_{n-1}] for the measured
            basis state.
        """
        probs = self.get_probabilities()
        outcome = np.random.choice(len(probs), p=probs)
        # Convert outcome index to bit list (big-endian)
        bits = []
        for i in range(self.n_qubits):
            bit_pos = self.n_qubits - 1 - i
            bits.append((outcome >> bit_pos) & 1)
        return bits

    def reset(self) -> None:
        """Reset the circuit to the |00...0> state."""
        self.statevector = np.zeros(2 ** self.n_qubits, dtype=complex)
        self.statevector[0] = 1.0 + 0j
