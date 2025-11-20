import os

from Cython.Build import cythonize
from setuptools import setup, find_packages
from setuptools.extension import Extension

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Compiler & linker flags for AddressSanitizer
compiler_args = ["-O3", "-flto", "-pthread"]

extensions = [
	Extension("cbqs.Constants", [os.path.join("cbqs", "Constants.py")], extra_compile_args = compiler_args),
	Extension("cbqs.StateGenerator", [os.path.join("cbqs", "StateGenerator.py")], extra_compile_args = compiler_args),
	Extension("cbqs.Expression", [
		os.path.join("cbqs", "Expression.pyx"),
		os.path.join("cbqs", "src", "Expression.c")
	], extra_compile_args = compiler_args),
	Extension("cbqs.Metal_executor", [
		os.path.join("cbqs", "Metal_executor.pyx"),
		os.path.join("cbqs", "src", "metal_files", "exec_metal.m")
	], extra_compile_args = compiler_args + ["-ObjC"], include_dirs = [os.path.join("cbqs", "src", "metal_files")]),
	Extension("cbqs.Model", ["cbqs/Model.py"], extra_compile_args = compiler_args),
	Extension("cbqs.CircuitBackendBinder",
	          [
		          os.path.join("cbqs", "CircuitBackendBinder.pyx"),
		          os.path.join("circuit_backend", "Backend", "src", "QPU.c"),
		          os.path.join("circuit_backend", "Backend", "src", "circuit_allocations.c"),
		          os.path.join("circuit_backend", "Backend", "src", "ciruict_outputs.c"),
		          os.path.join("circuit_backend", "Backend", "src", "gate.c"),
		          os.path.join("circuit_backend", "Backend", "src", "Integer.c"),
		          os.path.join("circuit_backend", "Backend", "src", "IntegerAddition.c"),
		          os.path.join("circuit_backend", "Backend", "src", "IntegerComparison.c"),
		          os.path.join("circuit_backend", "Backend", "src", "IntegerMultiplication.c"),
		          os.path.join("circuit_backend", "Backend", "src", "LogicOperations.c"),
		          os.path.join("circuit_backend", "Assembly", "src", "AssemblyBasics.c"),
		          os.path.join("circuit_backend", "Assembly", "src", "AssemblyComparison.c"),
		          os.path.join("circuit_backend", "Assembly", "src", "AssemblyIntegerAddition.c"),
		          os.path.join("circuit_backend", "Assembly", "src", "AssemblyIntegerDivision.c"),
		          os.path.join("circuit_backend", "Assembly", "src", "AssemblyIntegerMultiplication.c"),
		          os.path.join("circuit_backend", "Assembly", "src", "AssemblyLogic.c"),
		          os.path.join("circuit_backend", "Assembly", "src", "AssemblyReader.c"),
		          os.path.join("circuit_backend", "Execution", "src", "execution.c"),
	          ],
	          language = "c", extra_compile_args = compiler_args,
	          include_dirs = [
		          os.path.join("circuit_backend", "Backend", "include"),
		          os.path.join("circuit_backend", "Assembly", "include"),
		          os.path.join("circuit_backend", "Execution", "include"),
	          ]),
	Extension("cbqs.SearchLib",
	          [
		          os.path.join("cbqs", "SearchLib.pyx"),
		          os.path.join("cbqs", "src", "solver.c"),
		          os.path.join("cbqs", "src", "SearchLib.c"),
		          os.path.join("cbqs", "src", "Branching.c"),
		          os.path.join("cbqs", "src", "intarray.c"),
		          os.path.join("cbqs", "src", "Expression.c"),
		          os.path.join("cbqs", "src", "state.c"),
		          os.path.join("cbqs", "src", "local_search.c"),
		          os.path.join("cbqs", "src", "constraint.c"),
		          os.path.join("cbqs", "src", "quantum_search.c"),
	          ], extra_compile_args = compiler_args,include_dirs = [os.path.join("cbqs", "src")]),

	Extension("cbqs.state_sampler",
	          [
		          os.path.join("cbqs", "state_sampler.pyx"),
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
	          ], extra_compile_args = compiler_args, include_dirs = [os.path.join("cbqs", "src")]),
]

setup(
	name = 'cbqs',
	packages = find_packages(),
	include_package_data = True,  # Include package data
	install_requires = ["numpy", "pandas"],
	ext_modules = cythonize(extensions, language_level = 3),
)
