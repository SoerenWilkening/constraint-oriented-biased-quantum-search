"""
Quantum gate definitions and application functions.

Provides standard quantum gate matrices (H, X, Z, Phase) and functions
to apply single-qubit, CNOT, and Toffoli gates to statevectors.
All statevectors use big-endian qubit ordering: qubit 0 is the most
significant bit. For example, in a 3-qubit system, basis state |q0 q1 q2>
maps to index q0*4 + q1*2 + q2.
"""
import numpy as np
from typing import Optional

# Single-qubit gate matrices
H: np.ndarray = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
"""Hadamard gate: creates equal superposition."""

X: np.ndarray = np.array([[0, 1], [1, 0]], dtype=complex)
"""Pauli-X gate: bit flip."""

Z: np.ndarray = np.array([[1, 0], [0, -1]], dtype=complex)
"""Pauli-Z gate: phase flip."""


def phase_gate(theta: float) -> np.ndarray:
    """Create a phase gate with rotation angle theta.

    Parameters
    ----------
    theta : float
        Rotation angle in radians.

    Returns
    -------
    np.ndarray
        2x2 unitary matrix [[1, 0], [0, exp(i*theta)]].
    """
    return np.array([[1, 0], [0, np.exp(1j * theta)]], dtype=complex)


def apply_single_qubit_gate(
    statevector: np.ndarray,
    gate_matrix: np.ndarray,
    target_qubit: int,
    n_qubits: int,
) -> np.ndarray:
    """Apply a single-qubit gate to a statevector.

    Uses tensor reshaping: the statevector is reshaped to a tensor with
    n_qubits axes of dimension 2, the gate is applied along the target
    axis, and the result is flattened back.

    Parameters
    ----------
    statevector : np.ndarray
        Complex statevector of length 2^n_qubits.
    gate_matrix : np.ndarray
        2x2 unitary gate matrix.
    target_qubit : int
        Index of the qubit to apply the gate to (0-indexed, big-endian).
    n_qubits : int
        Total number of qubits in the system.

    Returns
    -------
    np.ndarray
        Updated statevector after gate application.
    """
    sv = statevector.reshape([2] * n_qubits)
    # tensordot contracts axis 1 of gate with the target_qubit axis of sv
    # Result has target_qubit axis moved to position 0, so we need to move it back
    sv = np.tensordot(gate_matrix, sv, axes=([1], [target_qubit]))
    # Move the new axis (at position 0) back to target_qubit position
    sv = np.moveaxis(sv, 0, target_qubit)
    return sv.reshape(-1)


def apply_cnot(
    statevector: np.ndarray,
    control: int,
    target: int,
    n_qubits: int,
) -> np.ndarray:
    """Apply a CNOT gate to a statevector.

    For each basis state, if the control qubit is 1, the target qubit is
    flipped. Implemented by permuting amplitudes directly.

    Parameters
    ----------
    statevector : np.ndarray
        Complex statevector of length 2^n_qubits.
    control : int
        Index of the control qubit.
    target : int
        Index of the target qubit.
    n_qubits : int
        Total number of qubits.

    Returns
    -------
    np.ndarray
        Updated statevector after CNOT application.
    """
    result = statevector.copy()
    n_states = 2 ** n_qubits
    # Bit positions (big-endian): qubit k corresponds to bit (n_qubits - 1 - k)
    control_bit = n_qubits - 1 - control
    target_bit = n_qubits - 1 - target

    for i in range(n_states):
        if (i >> control_bit) & 1:
            # Control is 1, compute swapped index by flipping target bit
            j = i ^ (1 << target_bit)
            if i < j:
                result[i], result[j] = result[j], result[i]
    return result


def apply_toffoli(
    statevector: np.ndarray,
    control1: int,
    control2: int,
    target: int,
    n_qubits: int,
) -> np.ndarray:
    """Apply a Toffoli (CCX) gate to a statevector.

    Flips the target qubit when both control qubits are 1.

    Parameters
    ----------
    statevector : np.ndarray
        Complex statevector of length 2^n_qubits.
    control1 : int
        Index of the first control qubit.
    control2 : int
        Index of the second control qubit.
    target : int
        Index of the target qubit.
    n_qubits : int
        Total number of qubits.

    Returns
    -------
    np.ndarray
        Updated statevector after Toffoli application.
    """
    result = statevector.copy()
    n_states = 2 ** n_qubits
    c1_bit = n_qubits - 1 - control1
    c2_bit = n_qubits - 1 - control2
    target_bit = n_qubits - 1 - target

    for i in range(n_states):
        if ((i >> c1_bit) & 1) and ((i >> c2_bit) & 1):
            j = i ^ (1 << target_bit)
            if i < j:
                result[i], result[j] = result[j], result[i]
    return result
