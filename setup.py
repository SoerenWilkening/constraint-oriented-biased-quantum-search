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
	Extension("cbqs.Constants", ["cbqs/Constants.py"], extra_compile_args = compiler_args),
	Extension("cbqs.StateGenerator", ["cbqs/StateGenerator.py"], extra_compile_args = compiler_args),
	Extension("cbqs.Expression", ["cbqs/Expression.pyx", "cbqs/src/Expression.c"], extra_compile_args = compiler_args),
	Extension("cbqs.Metal_executor", ["cbqs/Metal_executor.pyx", "cbqs/src/metal_files/exec_metal.m"],
	          extra_compile_args = compiler_args + ["-ObjC"],
	          include_dirs = [os.path.join("cbqs", "src", "metal_files")]),
	Extension("cbqs.Model", ["cbqs/Model.py"], extra_compile_args = compiler_args),
	Extension("cbqs.CircuitBackendBinder",
	          ["cbqs/CircuitBackendBinder.pyx",
	           "circuit_backend/Backend/src/QPU.c",
	           "circuit_backend/Backend/src/circuit_allocations.c",
	           "circuit_backend/Backend/src/ciruict_outputs.c",
	           "circuit_backend/Backend/src/gate.c",
	           "circuit_backend/Backend/src/Integer.c",
	           "circuit_backend/Backend/src/IntegerAddition.c",
	           "circuit_backend/Backend/src/IntegerComparison.c",
	           "circuit_backend/Backend/src/IntegerMultiplication.c",
	           "circuit_backend/Backend/src/LogicOperations.c",

			   "circuit_backend/Assembly/src/AssemblyBasics.c",
	           "circuit_backend/Assembly/src/AssemblyComparison.c",
	           "circuit_backend/Assembly/src/AssemblyIntegerAddition.c",
	           "circuit_backend/Assembly/src/AssemblyIntegerDivision.c",
	           "circuit_backend/Assembly/src/AssemblyIntegerMultiplication.c",
	           "circuit_backend/Assembly/src/AssemblyLogic.c",
	           "circuit_backend/Assembly/src/AssemblyReader.c",

	           "circuit_backend/Execution/src/execution.c",
	           ],
	          language="c",
	          extra_compile_args = compiler_args,
	          include_dirs = [
		          "circuit_backend/Backend/include",
		          "circuit_backend/Assembly/include",
		          "circuit_backend/Execution/include",
	          ]),
	Extension("cbqs.SearchLib",
	          ["cbqs/SearchLib.pyx",
	           os.path.join("cbqs", "src", "solver.c"),
	           os.path.join("cbqs", "src", "SearchLib.c"),
	           os.path.join("cbqs", "src", "Branching.c"),
	           os.path.join("cbqs", "src", "intarray.c"),
	           os.path.join("cbqs", "src", "Expression.c"),
	           os.path.join("cbqs", "src", "state.c"),
	           os.path.join("cbqs", "src", "local_search.c"),
	           os.path.join("cbqs", "src", "constraint.c"),
	           os.path.join("cbqs", "src", "quantum_search.c"),
	           ],
	          extra_compile_args = compiler_args,
	          include_dirs = [os.path.join("cbqs", "src")]),

	Extension("cbqs.state_sampler",
	          ["cbqs/state_sampler.pyx",
	           os.path.join("cbqs", "src", "solver.c"),
	           os.path.join("cbqs", "src", "SearchLib.c"),
	           os.path.join("cbqs", "src", "Branching.c"),
	           os.path.join("cbqs", "src", "intarray.c"),
	           os.path.join("cbqs", "src", "Expression.c"),
	           os.path.join("cbqs", "src", "state.c"),
	           os.path.join("cbqs", "src", "local_search.c"),
	           os.path.join("cbqs", "src", "constraint.c"),
	           os.path.join("cbqs", "src", "quantum_search.c"),
	           os.path.join("cbqs", "src", "approximate_state_sampler.c"),
	           ],
	          extra_compile_args = compiler_args,
	          include_dirs = [os.path.join("cbqs", "src")]),
]

setup(
	name = 'cbqs',
	packages = find_packages(),
	include_package_data = True,  # Include package data
	install_requires = ["numpy", "pandas"],
	ext_modules = cythonize(extensions, language_level = 3),
)
