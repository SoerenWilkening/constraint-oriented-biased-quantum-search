from libc.stdlib cimport calloc, free, srand
from libc.stdio cimport printf

cdef extern from "stdbool.h":
	ctypedef bint bool

cdef extern from "QPU.h":
	ctypedef struct gate_t:
		pass

	ctypedef struct circuit_t:
		pass

	ctypedef struct instruction_t:
		pass

	ctypedef struct sequence_t:
		pass

	circuit_t *init_circuit()
	void print_circuit(circuit_t *circ)

	sequence_t *QFT(sequence_t *seq, int num_qubits)
	void print_sequence(sequence_t *seq)

cdef extern from "execution.h":
	void qubit_mapping(unsigned int qubit_arrray[], circuit_t *circ);
	void run_instruction(sequence_t *res, const unsigned int qubit_array[], bint invert, circuit_t *circ);

cdef class circuit:
	cdef circuit_t *circ
	cdef perform_qft(self)
