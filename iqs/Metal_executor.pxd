# from libc.stdint cimport uint64_t, uint32_t, int64_t
# from libc.stdlib cimport calloc, free, srand
#
# cdef extern from "generators/main.h":
# 	int gpu_qmax_search_c(int n, int M, double bias, uint32_t globalSeed,
# 	                    int *constraint, int c_terms,
# 	                    int *objective, int o_terms,
# 	                    int cur, uint32_t *arr,
# 	                    );
