

def set_seed(unsigned int seed):
	srand(seed)

def set_factors_wrapper(double objective_factor, double constraint_factor, double bias_factor, double look_factor):
	set_factors(objective_factor, constraint_factor, bias_factor, look_factor)

def set_bias_wrapper(double bias):
	set_bias(bias)

def set_obj_dependence_wrapper(dependence: list[double]):
	arr = np.array(dependence, dtype = np.double)
	cdef double * ptr = <double *> calloc(arr.shape[0], sizeof(double))
	for i in range(arr.shape[0]):
		ptr[i] = <double> arr[i]
	set_obj_dependence(ptr, len(dependence))
	free(ptr)  # Free allocated memory after C function copies it

def set_constraint_dependence_wrapper(dependence: list[double]):
	arr = np.array(dependence, dtype = np.double)
	cdef double * ptr = <double *> calloc(arr.shape[0], sizeof(double))
	for i in range(arr.shape[0]):
		ptr[i] = <double> arr[i]
	set_constraint_dependence(ptr, len(dependence))
	free(ptr)  # Free allocated memory after C function copies it