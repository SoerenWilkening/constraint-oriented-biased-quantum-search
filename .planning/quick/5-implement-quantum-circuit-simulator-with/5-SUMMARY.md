---
phase: quick-5
plan: 01
subsystem: quantum-simulation
tags: [quantum-computing, grover, statevector, circuit-simulator, constraint-satisfaction]

requires:
  - phase: none
    provides: standalone subpackage

provides:
  - Pure-Python statevector quantum circuit simulator
  - Quantum gate library (H, X, Z, CNOT, Toffoli, Phase)
  - Constraint-to-oracle compiler for SAT-like clauses
  - Grover's algorithm implementation with optimal iteration calculation

affects: [cbqs-circuit, quantum-search, benchmarking]

tech-stack:
  added: [numpy (already present)]
  patterns: [tensor-reshape gate application, direct statevector oracle, big-endian qubit ordering]

key-files:
  created:
    - cbqs/circuit/__init__.py
    - cbqs/circuit/gates.py
    - cbqs/circuit/simulator.py
    - cbqs/circuit/oracle.py
    - cbqs/circuit/grover.py
    - tests/test_circuit_simulator.py
  modified: []

key-decisions:
  - "Direct statevector manipulation for oracle (no ancilla qubits) -- simple and mathematically correct"
  - "Big-endian qubit ordering: qubit 0 is most significant bit, consistent throughout"
  - "Tensor reshape via np.tensordot for single-qubit gate application"
  - "Amplitude permutation for CNOT/Toffoli rather than full matrix construction"

patterns-established:
  - "Gate application via tensor reshape: statevector.reshape([2]*n) + tensordot + moveaxis"
  - "Oracle as direct statevector sign flip: iterate basis states, check constraint satisfaction"
  - "QuantumCircuit fluent API: qc.h(0); qc.cx(0,1); probs = qc.get_probabilities()"

requirements-completed: [QUICK-5]

duration: 4min
completed: 2026-03-03
---

# Quick Task 5: Quantum Circuit Simulator Summary

**Pure-Python statevector simulator with H/X/Z/CNOT/Toffoli/Phase gates, SAT-constraint oracle compiler, and Grover's algorithm achieving >94% target state probability on 3-qubit search**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-03T12:30:39Z
- **Completed:** 2026-03-03T12:34:29Z
- **Tasks:** 2/2
- **Files created:** 6

## Accomplishments

### Task 1: Quantum Gate Library and Statevector Simulator
- Implemented gate matrices (H, X, Z, phase_gate) as numpy arrays
- Gate application via tensor reshaping: reshape statevector to (2,2,...,2), apply via tensordot, reshape back
- CNOT and Toffoli via amplitude permutation (swap pairs where control bits are set)
- QuantumCircuit class: manages statevector, provides h/x/z/phase/cx/ccx/measure_all/get_probabilities/reset
- 17 tests covering all gates, Bell state creation, measurement, and dimension checks

### Task 2: Constraint Oracle and Grover's Algorithm
- ConstraintOracle: stores SAT-like clauses as (variable_index, expected_value) tuples
- Oracle applies phase flip by iterating basis states and checking constraint satisfaction
- Grover diffusion operator: H-X-signflip-X-H pattern with direct |11...1> phase flip
- optimal_iterations(): floor(pi/4 * sqrt(N/M)) formula
- grover_search(): creates uniform superposition, applies oracle+diffusion for specified iterations
- 8 additional tests for oracle phase flips, conjunction, Grover amplification, and formula

## Verification Results

- All 25 tests pass (17 gate/simulator + 4 oracle + 4 Grover)
- Integration check: 3-qubit search for |101> achieves 94.5% probability (target: >90%)
- 2-qubit single-solution Grover achieves >90% probability
- 3-qubit multi-solution Grover correctly amplifies both satisfying states

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 (RED) | d8b3778 | Failing tests for gate library and simulator |
| 1 (GREEN) | 52c0f39 | Gate library and simulator implementation |
| 2 (RED) | 8a6f49c | Failing tests for oracle and Grover |
| 2 (GREEN) | e6ac924 | Oracle and Grover implementation |

## Deviations from Plan

None -- plan executed exactly as written.

## Architecture Notes

**Qubit ordering:** Big-endian throughout. Qubit 0 is the most significant bit. State |q0 q1 q2> maps to index q0*4 + q1*2 + q2. This is consistent across gates, oracle, and Grover.

**Oracle strategy:** Direct statevector manipulation rather than gate decomposition. For each basis state index, extract bit values, check all clauses, flip amplitude sign if all satisfied. This avoids ancilla qubits entirely.

**Diffusion operator:** Standard H-X-MCZ-X-H pattern, with the multi-controlled Z implemented as a direct sign flip on the |11...1> amplitude (index 2^n - 1).

## Self-Check: PASSED

- All 6 created files verified on disk
- All 4 commit hashes (d8b3778, 52c0f39, 8a6f49c, e6ac924) verified in git log
