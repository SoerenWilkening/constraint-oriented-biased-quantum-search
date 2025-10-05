
cdef extern from "QPU.h":

	ctypedef struct gate_t:
		pass

	ctypedef struct circuit_t:
		pass

	ctypedef struct instruction_t:
		pass

	circuit_t *init_circuit()
	void print_circuit(circuit_t *circ)


cdef class circuit:
	cdef circuit_t *circ
