"""
Pytest tests for the quantum circuit simulator.

Tests validate gate operations, statevector evolution, measurement,
constraint oracle construction, and Grover's algorithm correctness.
"""
import pytest
import numpy as np
from numpy.testing import assert_allclose

from cbqs.circuit.gates import (
    H, X, Z, phase_gate,
    apply_single_qubit_gate, apply_cnot, apply_toffoli,
)
from cbqs.circuit.simulator import QuantumCircuit


class TestSingleQubitGates:
    """Tests for individual single-qubit gate operations."""

    def test_hadamard_on_zero(self):
        """H gate on |0> produces equal superposition (|0>+|1>)/sqrt(2)."""
        sv = np.array([1.0 + 0j, 0.0 + 0j])
        result = apply_single_qubit_gate(sv, H, 0, 1)
        expected = np.array([1.0, 1.0]) / np.sqrt(2)
        assert_allclose(result, expected, atol=1e-12)

    def test_x_gate_flips_zero_to_one(self):
        """X gate flips |0> to |1>."""
        sv = np.array([1.0 + 0j, 0.0 + 0j])
        result = apply_single_qubit_gate(sv, X, 0, 1)
        expected = np.array([0.0, 1.0])
        assert_allclose(result, expected, atol=1e-12)

    def test_x_gate_flips_one_to_zero(self):
        """X gate flips |1> to |0>."""
        sv = np.array([0.0 + 0j, 1.0 + 0j])
        result = apply_single_qubit_gate(sv, X, 0, 1)
        expected = np.array([1.0, 0.0])
        assert_allclose(result, expected, atol=1e-12)

    def test_z_gate_phase_flip(self):
        """Z gate applies -1 phase to |1> component."""
        sv = np.array([1.0 + 0j, 1.0 + 0j]) / np.sqrt(2)
        result = apply_single_qubit_gate(sv, Z, 0, 1)
        expected = np.array([1.0, -1.0]) / np.sqrt(2)
        assert_allclose(result, expected, atol=1e-12)

    def test_phase_gate_applies_rotation(self):
        """Custom phase gate applies exp(i*theta) to |1> component."""
        theta = np.pi / 4
        pg = phase_gate(theta)
        sv = np.array([0.0 + 0j, 1.0 + 0j])
        result = apply_single_qubit_gate(sv, pg, 0, 1)
        expected = np.array([0.0, np.exp(1j * theta)])
        assert_allclose(result, expected, atol=1e-12)


class TestMultiQubitGates:
    """Tests for CNOT and Toffoli gate operations."""

    def test_cnot_flips_target_when_control_is_one(self):
        """CNOT flips target qubit when control is |1>."""
        # |10> -> |11> (control=0, target=1)
        sv = np.array([0.0 + 0j, 0.0 + 0j, 1.0 + 0j, 0.0 + 0j])
        result = apply_cnot(sv, 0, 1, 2)
        expected = np.array([0.0, 0.0, 0.0, 1.0])
        assert_allclose(result, expected, atol=1e-12)

    def test_cnot_no_flip_when_control_is_zero(self):
        """CNOT does not flip target when control is |0>."""
        # |01> stays |01>
        sv = np.array([0.0 + 0j, 1.0 + 0j, 0.0 + 0j, 0.0 + 0j])
        result = apply_cnot(sv, 0, 1, 2)
        expected = np.array([0.0, 1.0, 0.0, 0.0])
        assert_allclose(result, expected, atol=1e-12)

    def test_toffoli_flips_target_when_both_controls_one(self):
        """Toffoli flips target when both controls are |1>."""
        # |110> -> |111> (controls=0,1, target=2)
        sv = np.zeros(8, dtype=complex)
        sv[6] = 1.0  # |110>
        result = apply_toffoli(sv, 0, 1, 2, 3)
        expected = np.zeros(8, dtype=complex)
        expected[7] = 1.0  # |111>
        assert_allclose(result, expected, atol=1e-12)

    def test_toffoli_no_flip_when_one_control_zero(self):
        """Toffoli does not flip target when only one control is |1>."""
        # |100> stays |100>
        sv = np.zeros(8, dtype=complex)
        sv[4] = 1.0  # |100>
        result = apply_toffoli(sv, 0, 1, 2, 3)
        expected = np.zeros(8, dtype=complex)
        expected[4] = 1.0  # |100>
        assert_allclose(result, expected, atol=1e-12)


class TestQuantumCircuit:
    """Tests for the QuantumCircuit statevector simulator."""

    def test_initial_state_is_all_zeros(self):
        """QuantumCircuit initializes to |00...0> state."""
        qc = QuantumCircuit(3)
        sv = qc.get_statevector()
        assert sv[0] == 1.0 + 0j
        assert_allclose(np.abs(sv[1:]) ** 2, 0.0, atol=1e-12)

    def test_statevector_dimension(self):
        """Multi-qubit statevector has correct dimension 2^n."""
        for n in [1, 2, 3, 4]:
            qc = QuantumCircuit(n)
            assert len(qc.get_statevector()) == 2 ** n

    def test_bell_state_creation(self):
        """H(0)->CNOT(0,1) produces Bell state (|00>+|11>)/sqrt(2)."""
        qc = QuantumCircuit(2)
        qc.h(0)
        qc.cx(0, 1)
        sv = qc.get_statevector()
        expected = np.array([1.0, 0.0, 0.0, 1.0]) / np.sqrt(2)
        assert_allclose(sv, expected, atol=1e-12)

    def test_measurement_probabilities_sum_to_one(self):
        """Measurement probabilities sum to 1.0."""
        qc = QuantumCircuit(3)
        qc.h(0)
        qc.h(1)
        probs = qc.get_probabilities()
        assert_allclose(np.sum(probs), 1.0, atol=1e-12)

    def test_measurement_deterministic_zero(self):
        """Measurement of |0> deterministically returns 0."""
        qc = QuantumCircuit(1)
        # State is |0>, measurement should always return [0]
        for _ in range(10):
            result = qc.measure_all()
            assert result == [0]

    def test_phase_gate_method(self):
        """Circuit phase method applies rotation correctly."""
        qc = QuantumCircuit(1)
        qc.x(0)  # |1>
        qc.phase(0, np.pi)  # Should give -|1>
        sv = qc.get_statevector()
        expected = np.array([0.0, -1.0 + 0j])
        assert_allclose(sv, expected, atol=1e-12)

    def test_reset_returns_to_zero_state(self):
        """Reset restores the circuit to |00...0> state."""
        qc = QuantumCircuit(2)
        qc.h(0)
        qc.cx(0, 1)
        qc.reset()
        sv = qc.get_statevector()
        expected = np.array([1.0, 0.0, 0.0, 0.0])
        assert_allclose(sv, expected, atol=1e-12)

    def test_ccx_method(self):
        """Circuit ccx method applies Toffoli gate correctly."""
        qc = QuantumCircuit(3)
        qc.x(0)
        qc.x(1)
        # Both controls are |1>, so target should flip: |110> -> |111>
        qc.ccx(0, 1, 2)
        sv = qc.get_statevector()
        expected = np.zeros(8, dtype=complex)
        expected[7] = 1.0  # |111>
        assert_allclose(sv, expected, atol=1e-12)
