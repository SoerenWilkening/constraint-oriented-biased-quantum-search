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
from cbqs.circuit.oracle import ConstraintOracle
from cbqs.circuit.grover import grover_search, optimal_iterations


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


class TestConstraintOracle:
    """Tests for constraint-based oracle construction."""

    def test_oracle_single_clause_phase_flip(self):
        """Oracle flips phase of states satisfying a single clause (x0=1 AND x1=1).

        For 2 qubits, clause [(0,1),(1,1)] means x0=1 AND x1=1 -> only |11> = index 3.
        """
        oracle = ConstraintOracle.from_clauses(2, [[(0, 1), (1, 1)]])
        qc = QuantumCircuit(2)
        # Put into equal superposition to see phase flip
        qc.h(0)
        qc.h(1)
        sv_before = qc.get_statevector().copy()
        oracle.apply(qc)
        sv_after = qc.get_statevector()
        # Only index 3 (|11>) should have flipped sign
        for i in range(4):
            if i == 3:
                assert_allclose(sv_after[i], -sv_before[i], atol=1e-12)
            else:
                assert_allclose(sv_after[i], sv_before[i], atol=1e-12)

    def test_oracle_multiple_clauses_conjunction(self):
        """Oracle with multiple clauses only flips states satisfying ALL clauses.

        Clause 1: x0=1, Clause 2: x1=0. Only states with x0=1 AND x1=0 satisfy both.
        On 2 qubits: |10> = index 2.
        """
        oracle = ConstraintOracle.from_clauses(2, [[(0, 1)], [(1, 0)]])
        qc = QuantumCircuit(2)
        qc.h(0)
        qc.h(1)
        sv_before = qc.get_statevector().copy()
        oracle.apply(qc)
        sv_after = qc.get_statevector()
        # Only index 2 (|10>) should have flipped sign
        for i in range(4):
            if i == 2:
                assert_allclose(sv_after[i], -sv_before[i], atol=1e-12)
            else:
                assert_allclose(sv_after[i], sv_before[i], atol=1e-12)

    def test_oracle_3qubit_clause(self):
        """Oracle on 3 qubits with clause 'x0=1 AND x1=1' flips |110> and |111>.

        Clause: [(0,1),(1,1)] on 3 qubits. Satisfying states are any with x0=1,x1=1:
        |110> = index 6, |111> = index 7.
        """
        oracle = ConstraintOracle.from_clauses(3, [[(0, 1), (1, 1)]])
        qc = QuantumCircuit(3)
        for i in range(3):
            qc.h(i)
        sv_before = qc.get_statevector().copy()
        oracle.apply(qc)
        sv_after = qc.get_statevector()
        for i in range(8):
            if i in (6, 7):
                assert_allclose(sv_after[i], -sv_before[i], atol=1e-12)
            else:
                assert_allclose(sv_after[i], sv_before[i], atol=1e-12)

    def test_from_clauses_api(self):
        """ConstraintOracle.from_clauses() accepts list of (variable_index, value) tuples."""
        oracle = ConstraintOracle.from_clauses(3, [[(0, 1), (2, 0)]])
        assert oracle.n_qubits == 3
        assert len(oracle.clauses) == 1


class TestGroverSearch:
    """Tests for Grover's algorithm with constraint oracles."""

    def test_grover_2qubit_single_solution(self):
        """Grover on 2 qubits with single satisfying assignment finds it with >90% probability.

        Target: x0=1, x1=0 -> |10> = index 2. With N=4, M=1, optimal = 1 iteration.
        """
        oracle = ConstraintOracle.from_clauses(2, [[(0, 1), (1, 0)]])
        n_iter = optimal_iterations(4, 1)
        qc = grover_search(2, oracle, n_iter)
        probs = qc.get_probabilities()
        assert probs[2] > 0.9, f"Expected >90% on |10>, got {probs[2]:.3f}"

    def test_grover_3qubit_constraint(self):
        """Grover on 3 qubits with x0=1,x1=0 amplifies |010> and |011>.

        Clause: x0=1, x1=0. Satisfying states: |100>=4, |101>=5.
        Wait -- let me think about the bit ordering. x0=1,x1=0 means qubit 0 is 1, qubit 1 is 0.
        |100> = index 4 and |101> = index 5.
        N=8, M=2, optimal_iterations(8,2) = floor(pi/4*sqrt(4)) = floor(pi/4*2) = 1.
        """
        oracle = ConstraintOracle.from_clauses(3, [[(0, 1), (1, 0)]])
        n_iter = optimal_iterations(8, 2)
        qc = grover_search(3, oracle, n_iter)
        probs = qc.get_probabilities()
        # States |100>=4 and |101>=5 should have amplified probability
        total_good = probs[4] + probs[5]
        assert total_good > 0.9, f"Expected >90% on satisfying states, got {total_good:.3f}"

    def test_grover_no_solution_uniform(self):
        """Grover with no satisfying assignment returns near-uniform distribution.

        Create an impossible constraint set: x0=1 AND x0=0.
        No state can satisfy both clauses, so oracle flips nothing.
        After Grover iterations, distribution should stay roughly uniform.
        """
        oracle = ConstraintOracle.from_clauses(2, [[(0, 1)], [(0, 0)]])
        qc = grover_search(2, oracle, 1)
        probs = qc.get_probabilities()
        # Should be roughly uniform (0.25 each) since oracle does nothing
        assert_allclose(probs, [0.25, 0.25, 0.25, 0.25], atol=0.05)

    def test_optimal_iterations_formula(self):
        """optimal_iterations returns correct floor(pi/4 * sqrt(N/M))."""
        import math
        # N=4, M=1 -> floor(pi/4 * 2) = floor(1.57) = 1
        assert optimal_iterations(4, 1) == 1
        # N=8, M=1 -> floor(pi/4 * sqrt(8)) = floor(pi/4 * 2.828) = floor(2.22) = 2
        assert optimal_iterations(8, 1) == 2
        # N=16, M=1 -> floor(pi/4 * 4) = floor(3.14) = 3
        assert optimal_iterations(16, 1) == 3
        # N=8, M=2 -> floor(pi/4 * sqrt(4)) = floor(pi/4 * 2) = floor(1.57) = 1
        assert optimal_iterations(8, 2) == 1
