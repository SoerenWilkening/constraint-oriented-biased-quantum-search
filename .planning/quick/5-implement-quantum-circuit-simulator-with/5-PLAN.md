---
phase: quick-5
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - cbqs/circuit/__init__.py
  - cbqs/circuit/gates.py
  - cbqs/circuit/simulator.py
  - cbqs/circuit/oracle.py
  - cbqs/circuit/grover.py
  - tests/test_circuit_simulator.py
autonomous: true
requirements: [QUICK-5]
must_haves:
  truths:
    - "Simulator correctly applies H, X, Z, CNOT, Toffoli, and custom phase gates to statevectors"
    - "Constraint-based oracle flips phase of states satisfying all SAT-like clauses"
    - "Grover search with constraint oracle amplifies probability of satisfying assignments"
    - "API allows defining constraints as Variable == value or clause lists, compiled into oracle circuits"
  artifacts:
    - path: "cbqs/circuit/__init__.py"
      provides: "Public API exports for circuit subpackage"
    - path: "cbqs/circuit/gates.py"
      provides: "Gate definitions (H, X, Z, CNOT, Toffoli, Phase) as unitary matrices and apply functions"
    - path: "cbqs/circuit/simulator.py"
      provides: "Statevector simulator with gate application and measurement"
    - path: "cbqs/circuit/oracle.py"
      provides: "Constraint-to-oracle compiler: SAT clauses to phase-flip circuits"
    - path: "cbqs/circuit/grover.py"
      provides: "Grover's algorithm using simulator + oracle"
    - path: "tests/test_circuit_simulator.py"
      provides: "Comprehensive tests for gates, simulator, oracle, and Grover"
  key_links:
    - from: "cbqs/circuit/grover.py"
      to: "cbqs/circuit/simulator.py"
      via: "uses QuantumCircuit for state evolution"
      pattern: "from .simulator import QuantumCircuit"
    - from: "cbqs/circuit/grover.py"
      to: "cbqs/circuit/oracle.py"
      via: "gets oracle circuit from constraint compiler"
      pattern: "from .oracle import ConstraintOracle"
    - from: "cbqs/circuit/oracle.py"
      to: "cbqs/circuit/gates.py"
      via: "builds oracle from gate primitives"
      pattern: "from .gates import"
---

<objective>
Implement a pure-Python quantum circuit simulator supporting Grover's algorithm with constraint-based oracle construction.

Purpose: Provide a lightweight statevector simulator within the cbqs package that can demonstrate quantum search over constraint satisfaction problems -- the core use case of the CBQS project -- without requiring external quantum computing frameworks.

Output: A `cbqs/circuit/` subpackage with gate definitions, statevector simulator, SAT-constraint oracle compiler, and Grover's algorithm implementation, plus comprehensive tests.
</objective>

<execution_context>
@./.claude/get-shit-done/workflows/execute-plan.md
@./.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@cbqs/__init__.py
@cbqs/Constraint.pyx (for understanding existing constraint API patterns)
@tests/conftest.py (for test style reference)
@tests/test_model_py.py (for test style reference)
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement quantum gate library and statevector simulator</name>
  <files>cbqs/circuit/__init__.py, cbqs/circuit/gates.py, cbqs/circuit/simulator.py, tests/test_circuit_simulator.py</files>
  <behavior>
    - Test: H gate on |0> produces equal superposition (|0> + |1>)/sqrt(2)
    - Test: X gate flips |0> to |1> and vice versa
    - Test: Z gate applies -1 phase to |1> component
    - Test: CNOT flips target qubit when control is |1>
    - Test: Toffoli flips target when both controls are |1>
    - Test: Custom phase gate applies exp(i*theta) to |1> component
    - Test: 2-qubit circuit H(0)->CNOT(0,1) produces Bell state (|00> + |11>)/sqrt(2)
    - Test: Measurement probabilities sum to 1.0
    - Test: Measurement of |0> deterministically returns 0
    - Test: Multi-qubit statevector has correct dimension 2^n
  </behavior>
  <action>
Create `cbqs/circuit/` subpackage. Use numpy for statevector and matrix operations (numpy is already a project dependency).

**cbqs/circuit/gates.py:**
Define gate matrices as numpy arrays and gate-application functions operating on statevectors:
- `H` (Hadamard): 1/sqrt(2) * [[1,1],[1,-1]]
- `X` (Pauli-X): [[0,1],[1,0]]
- `Z` (Pauli-Z): [[1,0],[0,-1]]
- `phase_gate(theta)`: [[1,0],[0,exp(i*theta)]]
- `apply_single_qubit_gate(statevector, gate_matrix, target_qubit, n_qubits)`: Apply gate via tensor product with identities. Use the standard approach: reshape statevector to (2,2,...,2) tensor with n_qubits axes, apply gate along target axis via `np.tensordot` or axis swapping, reshape back.
- `apply_cnot(statevector, control, target, n_qubits)`: For each basis state, if control qubit is 1, flip target qubit. Implement by permuting amplitudes.
- `apply_toffoli(statevector, control1, control2, target, n_qubits)`: Same pattern, flip target when both controls are 1.

**cbqs/circuit/simulator.py:**
Class `QuantumCircuit`:
- `__init__(self, n_qubits: int)`: Initialize statevector to |00...0> (2^n array, first element = 1.0+0j)
- `h(self, qubit)`, `x(self, qubit)`, `z(self, qubit)`: Apply respective single-qubit gates
- `phase(self, qubit, theta)`: Apply phase gate
- `cx(self, control, target)`: Apply CNOT
- `ccx(self, control1, control2, target)`: Apply Toffoli
- `measure_all(self) -> list[int]`: Sample one measurement outcome from |psi|^2 probabilities, return as list of bit values
- `get_probabilities(self) -> np.ndarray`: Return |amplitude|^2 for each basis state
- `get_statevector(self) -> np.ndarray`: Return copy of current statevector
- `reset(self)`: Reset to |00...0>

**cbqs/circuit/__init__.py:**
Export `QuantumCircuit` from simulator, gate constants from gates.

Write tests in `tests/test_circuit_simulator.py` FIRST (red), then implement (green). Use pytest style matching existing tests: classes grouping related tests, descriptive docstrings.
  </action>
  <verify>
    <automated>cd /Users/sorenwilkening/Desktop/Projects/constraint-oriented-biased-quantum-search && python -m pytest tests/test_circuit_simulator.py -x -v -k "not oracle and not grover" 2>&1 | tail -30</automated>
  </verify>
  <done>All gate and simulator tests pass. QuantumCircuit correctly evolves statevectors through H, X, Z, CNOT, Toffoli, and phase gates. Measurement produces valid probability distributions.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement constraint oracle compiler and Grover's algorithm</name>
  <files>cbqs/circuit/oracle.py, cbqs/circuit/grover.py, cbqs/circuit/__init__.py, tests/test_circuit_simulator.py</files>
  <behavior>
    - Test: Oracle flips phase of exactly the states satisfying a single clause (e.g., x0 AND x1)
    - Test: Oracle with multiple clauses only flips states satisfying ALL clauses (conjunction)
    - Test: Oracle on 3 qubits with clause "x0=1 AND x1=1" flips phase of |110> and |111> only
    - Test: Grover search on 2 qubits with single satisfying assignment finds it with high probability (>0.9)
    - Test: Grover search on 3 qubits with constraint x0=1, x1=0 amplifies |010> and |011>
    - Test: Grover with no satisfying assignment returns uniform distribution (no amplification)
    - Test: ConstraintOracle.from_clauses() API accepts list of (variable_index, value) tuples
    - Test: Grover optimal_iterations() returns correct floor(pi/4 * sqrt(N/M)) for N states, M solutions
  </behavior>
  <action>
**cbqs/circuit/oracle.py:**
Class `ConstraintOracle`:
- `__init__(self, n_qubits: int)`: Store qubit count, initialize empty clause list
- `add_clause(self, literals: list[tuple[int, int]])`: Add a clause as list of (variable_index, expected_value) pairs. A clause is satisfied when ALL literals match. Example: `[(0, 1), (1, 0)]` means x0=1 AND x1=0.
- `from_clauses(cls, n_qubits, clauses)` (classmethod): Convenience constructor from list of clauses
- `apply(self, circuit: QuantumCircuit)`: Apply the oracle to the circuit's statevector. Implementation strategy -- direct statevector manipulation for efficiency:
  1. For each basis state index i (0 to 2^n - 1), extract the bit values
  2. Check if ALL clauses are satisfied by those bit values
  3. If yes, flip the sign of that amplitude: statevector[i] *= -1
  This avoids needing ancilla qubits and multi-controlled gate decomposition, which keeps the simulator simple while being mathematically correct for Grover's oracle.

**cbqs/circuit/grover.py:**
- `diffusion_operator(circuit: QuantumCircuit)`: Apply the standard Grover diffusion (inversion about mean). Implementation: H on all qubits, X on all qubits, multi-controlled Z (flip phase of |11...1>), X on all qubits, H on all qubits. For the multi-controlled Z: directly flip sign of the |11...1> amplitude in the statevector (index 2^n - 1) -- same direct approach as oracle.
- `grover_search(n_qubits: int, oracle: ConstraintOracle, n_iterations: int | None = None) -> QuantumCircuit`: Run Grover's algorithm:
  1. Create QuantumCircuit(n_qubits)
  2. Apply H to all qubits (uniform superposition)
  3. If n_iterations is None, use optimal_iterations (requires knowing M -- skip auto-detection, require explicit iteration count or default to 1)
  4. Repeat n_iterations times: oracle.apply(circuit), diffusion_operator(circuit)
  5. Return the circuit (user can measure or inspect probabilities)
- `optimal_iterations(n_states: int, n_solutions: int) -> int`: Return floor(pi/4 * sqrt(n_states / n_solutions))

Update `cbqs/circuit/__init__.py` to also export `ConstraintOracle`, `grover_search`, `optimal_iterations`.

Write oracle and Grover tests FIRST in `tests/test_circuit_simulator.py` (append to existing test file), then implement.
  </action>
  <verify>
    <automated>cd /Users/sorenwilkening/Desktop/Projects/constraint-oriented-biased-quantum-search && python -m pytest tests/test_circuit_simulator.py -x -v 2>&1 | tail -40</automated>
  </verify>
  <done>All oracle and Grover tests pass. ConstraintOracle correctly identifies satisfying assignments and flips their phase. Grover search amplifies correct solutions to >90% probability for small instances. Full test suite (gates + oracle + Grover) passes.</done>
</task>

</tasks>

<verification>
Run the full test suite to ensure no regressions:
```bash
cd /Users/sorenwilkening/Desktop/Projects/constraint-oriented-biased-quantum-search && python -m pytest tests/test_circuit_simulator.py -v
```

Quick integration check -- run a 3-qubit Grover search from Python:
```python
from cbqs.circuit import QuantumCircuit, ConstraintOracle, grover_search, optimal_iterations
oracle = ConstraintOracle.from_clauses(3, [[(0, 1), (1, 0), (2, 1)]])  # x0=1, x1=0, x2=1 -> state |101> = index 5
n_iter = optimal_iterations(8, 1)
qc = grover_search(3, oracle, n_iter)
probs = qc.get_probabilities()
assert probs[5] > 0.9, f"Expected >90% probability on |101>, got {probs[5]:.3f}"
print(f"Target state |101> probability: {probs[5]:.3f}")
```
</verification>

<success_criteria>
- cbqs/circuit/ subpackage exists with gates.py, simulator.py, oracle.py, grover.py, __init__.py
- All quantum gates (H, X, Z, CNOT, Toffoli, Phase) produce correct unitary transformations
- ConstraintOracle correctly compiles SAT-like clauses into phase-flipping oracles
- Grover's algorithm amplifies satisfying assignments to >90% probability for small instances (2-4 qubits)
- All tests in tests/test_circuit_simulator.py pass
- No regressions in existing test suite
</success_criteria>

<output>
After completion, create `.planning/quick/5-implement-quantum-circuit-simulator-with/5-SUMMARY.md`
</output>
