import os

from Cython.Build import cythonize
from setuptools import setup, find_packages
from setuptools.extension import Extension

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
print(os.getcwd())

# Compiler & linker flags for AddressSanitizer
compiler_args = ["-O3", "-flto", "-pthread"]
# compiler_args = ["-g", "-flto", "-pthread"]

extensions = [
	Extension("iqs.Constants", ["iqs/Constants.py"], extra_compile_args = compiler_args),
	Extension("iqs.StateGenerator", ["iqs/StateGenerator.py"], extra_compile_args = compiler_args),
	Extension("iqs.Expression", ["iqs/Expression.pyx", "iqs/src/Expression.c"], extra_compile_args = compiler_args),
	Extension("iqs.Metal_executor", ["iqs/Metal_executor.pyx", "iqs/src/metal_files/exec_metal.m"],
	          extra_compile_args = compiler_args + ["-ObjC"],
	          include_dirs = [os.path.join("iqs", "src", "metal_files")]),
	Extension("iqs.Model", ["iqs/Model.py"], extra_compile_args = compiler_args),
	Extension("iqs.CircuitBackendBinder",
	          ["iqs/CircuitBackendBinder.pyx",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/QPU.c",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/circuit_allocations.c",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/ciruict_outputs.c",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/gate.c",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/Integer.c",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/IntegerAddition.c",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/IntegerComparison.c",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/IntegerMultiplication.c",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/LogicOperations.c",

			   "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Assembly/src/AssemblyBasics.c",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Assembly/src/AssemblyComparison.c",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Assembly/src/AssemblyIntegerAddition.c",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Assembly/src/AssemblyIntegerDivision.c",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Assembly/src/AssemblyIntegerMultiplication.c",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Assembly/src/AssemblyLogic.c",
	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Assembly/src/AssemblyReader.c",

	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Execution/src/execution.c",
	           ],
	          language="c",
	          extra_compile_args = compiler_args,
	          include_dirs = [
		          "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/include",
		          "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Assembly/include",
		          "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Execution/include",
	          ]),
	Extension("iqs.SearchLib",
	          ["iqs/SearchLib.pyx",
	           os.path.join("iqs", "src", "solver.c"),
	           os.path.join("iqs", "src", "SearchLib.c"),
	           os.path.join("iqs", "src", "Branching.c"),
	           os.path.join("iqs", "src", "intarray.c"),
	           os.path.join("iqs", "src", "Expression.c"),
	           os.path.join("iqs", "src", "state.c"),
	           os.path.join("iqs", "src", "local_search.c"),
	           os.path.join("iqs", "src", "constraint.c"),
	           os.path.join("iqs", "src", "quantum_search.c"),
	           ],
	          extra_compile_args = compiler_args,
	          include_dirs = [os.path.join("iqs", "src")]),

	Extension("iqs.state_sampler",
	          ["iqs/state_sampler.pyx",
	           os.path.join("iqs", "src", "solver.c"),
	           os.path.join("iqs", "src", "SearchLib.c"),
	           os.path.join("iqs", "src", "Branching.c"),
	           os.path.join("iqs", "src", "intarray.c"),
	           os.path.join("iqs", "src", "Expression.c"),
	           os.path.join("iqs", "src", "state.c"),
	           os.path.join("iqs", "src", "local_search.c"),
	           os.path.join("iqs", "src", "constraint.c"),
	           os.path.join("iqs", "src", "quantum_search.c"),
	           os.path.join("iqs", "src", "approximate_state_sampler.c"),
	           ],
	          extra_compile_args = compiler_args,
	          include_dirs = [os.path.join("iqs", "src")]),
]

setup(
	name = 'iqs',
	packages = find_packages(),
	include_package_data = True,  # Include package data
	install_requires = ["numpy", "pandas"],
	ext_modules = cythonize(extensions, language_level = 3),
)







# extensions = [
# 	Extension("iqs.CircuitBackend",
# 	          ["iqs/CircuitBackendBinder.pyx",
# 	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/QPU.c",
# 	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/circuit_allocations.c",
# 	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/ciruict_outputs.c",
# 	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/gate.c",
# 	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/Integer.c",
# 	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/IntegerAddition.c",
# 	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/IntegerComparison.c",
# 	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/IntegerMultiplication.c",
# 	           "/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/src/LogicOperations.c",
# 	           ],
# 	          language="c",
# 	          extra_compile_args = compiler_args,
# 	          include_dirs = ["/Users/sorenwilkening/Desktop/improved_quantum_search/circuit_backend/Backend/include"]),
# ]
