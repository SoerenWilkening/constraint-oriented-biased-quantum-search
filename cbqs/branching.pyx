import warnings

import numpy as np


def set_seed(unsigned int seed):
	srand(seed)

def set_factors_wrapper(double objective_factor, double constraint_factor, double bias_factor, double look_factor):
	warnings.warn("set_branching_factors is deprecated; use Model.set_param() instead", DeprecationWarning, stacklevel=2)
	set_factors(objective_factor, constraint_factor, bias_factor, look_factor)

def set_bias_wrapper(double bias):
	warnings.warn("set_branching_bias is deprecated; use Model.set_param('branching_bias', value) instead", DeprecationWarning, stacklevel=2)
	set_bias(bias)

def set_obj_dependence_wrapper(dependence: list[double]):
	warnings.warn("set_obj_dependence is deprecated; use Model.set_param('manual_bias', value) instead", DeprecationWarning, stacklevel=2)
	arr = np.array(dependence, dtype = np.double)
	cdef double * ptr = <double *> calloc(arr.shape[0], sizeof(double))
	for i in range(arr.shape[0]):
		ptr[i] = <double> arr[i]
	set_obj_dependence(ptr, len(dependence))
	free(ptr)  # Free allocated memory after C function copies it

def set_constraint_dependence_wrapper(dependence: list[double]):
	warnings.warn("set_constraint_dependence is deprecated; use Model.set_param() instead", DeprecationWarning, stacklevel=2)
	arr = np.array(dependence, dtype = np.double)
	cdef double * ptr = <double *> calloc(arr.shape[0], sizeof(double))
	for i in range(arr.shape[0]):
		ptr[i] = <double> arr[i]
	set_constraint_dependence(ptr, len(dependence))
	free(ptr)  # Free allocated memory after C function copies it