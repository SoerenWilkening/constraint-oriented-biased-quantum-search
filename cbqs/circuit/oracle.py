"""
Constraint-to-oracle compiler for quantum search.

Converts SAT-like constraint clauses into a phase-flipping oracle
suitable for Grover's algorithm. The oracle operates by direct
statevector manipulation: it checks each basis state against the
constraints and flips the sign of amplitudes for satisfying states.

This approach avoids ancilla qubits and multi-controlled gate
decomposition, keeping the simulator simple while being mathematically
correct for Grover's oracle.
"""
from typing import List, Tuple

from .simulator import QuantumCircuit


class ConstraintOracle:
    """A constraint-based oracle that flips the phase of satisfying states.

    Constraints are specified as a list of clauses, where each clause is
    a list of (variable_index, expected_value) pairs. A clause is satisfied
    when ALL its literals match. The oracle flips the phase of basis states
    that satisfy ALL clauses (conjunction of clauses).

    Parameters
    ----------
    n_qubits : int
        Number of qubits (variables) in the constraint system.

    Examples
    --------
    >>> oracle = ConstraintOracle(3)
    >>> oracle.add_clause([(0, 1), (1, 0)])  # x0=1 AND x1=0
    >>> oracle.add_clause([(2, 1)])           # AND x2=1
    # Only |101> (index 5) satisfies both clauses
    """

    def __init__(self, n_qubits: int):
        self.n_qubits = n_qubits
        self.clauses: List[List[Tuple[int, int]]] = []

    def add_clause(self, literals: List[Tuple[int, int]]) -> None:
        """Add a constraint clause.

        Parameters
        ----------
        literals : list of (int, int)
            List of (variable_index, expected_value) pairs. The clause
            is satisfied when all literals match the basis state's bits.
        """
        self.clauses.append(literals)

    @classmethod
    def from_clauses(
        cls,
        n_qubits: int,
        clauses: List[List[Tuple[int, int]]],
    ) -> "ConstraintOracle":
        """Create an oracle from a list of clauses.

        Parameters
        ----------
        n_qubits : int
            Number of qubits.
        clauses : list of list of (int, int)
            Each clause is a list of (variable_index, expected_value) tuples.

        Returns
        -------
        ConstraintOracle
            Oracle configured with the given clauses.
        """
        oracle = cls(n_qubits)
        for clause in clauses:
            oracle.add_clause(clause)
        return oracle

    def _satisfies(self, state_index: int) -> bool:
        """Check if a basis state satisfies all clauses.

        Parameters
        ----------
        state_index : int
            Integer index of the basis state.

        Returns
        -------
        bool
            True if all clauses are satisfied by the state.
        """
        for clause in self.clauses:
            clause_satisfied = True
            for var_idx, expected_val in clause:
                # Big-endian: qubit k corresponds to bit (n_qubits - 1 - k)
                bit_pos = self.n_qubits - 1 - var_idx
                actual_val = (state_index >> bit_pos) & 1
                if actual_val != expected_val:
                    clause_satisfied = False
                    break
            if not clause_satisfied:
                return False
        return True

    def apply(self, circuit: QuantumCircuit) -> None:
        """Apply the oracle to a quantum circuit's statevector.

        Flips the sign of amplitudes for basis states satisfying all
        constraint clauses.

        Parameters
        ----------
        circuit : QuantumCircuit
            The circuit whose statevector will be modified in-place.
        """
        n_states = 2 ** self.n_qubits
        for i in range(n_states):
            if self._satisfies(i):
                circuit.statevector[i] *= -1
