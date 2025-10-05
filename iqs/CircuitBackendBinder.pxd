
cdef extern from "Backend/include/QPU.h":
	ctypedef enum Standardgate_t:
		X, Y, Z, R, H, Rx, Ry, Rz, P, M

	ctypedef struct gate_t:
		unsigned int Control[2];
		unsigned int *large_control;
		unsigned int NumControls;
		Standardgate_t Gate;
		double GateValue;
		unsigned int Target;
		unsigned int NumBasisGates;

	ctypedef struct circuit_t:
		gate_t ** sequence;
		unsigned int used_layer;
		unsigned int allocated_layer;
		unsigned int * allocated_gates_per_layer;
		unsigned int * used_gates_per_layer;

		int ** gate_index_of_layer_and_qubits;

		size_t ** occupied_layers_of_qubit;
		unsigned int * allocated_occupation_indices_per_qubit;
		unsigned int * used_occupation_indices_per_qubit;

		unsigned int allocated_qubits;
		unsigned int used_qubits;
		size_t used;
		char toff_decomp;

		unsigned int qubit_indices[2000];

	circuit_t *init_circuit()
	void print_circuit(circuit_t *circ)


cdef class circuit:
	cdef circuit_t *circ
