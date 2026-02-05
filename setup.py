import os
import sys

from Cython.Build import cythonize
from setuptools import setup, find_packages
from setuptools.extension import Extension

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# from cbqs import __version__

# Compiler & linker flags for AddressSanitizer
compiler_args = ["-O3", "-flto", "-pthread"]

sources_circuit = [
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
]

sources = [
	os.path.join("cbqs", "src", "solver.c"),
	os.path.join("cbqs", "src", "SearchLib.c"),
	os.path.join("cbqs", "src", "Branching.c"),
	os.path.join("cbqs", "src", "intarray.c"),
	os.path.join("cbqs", "src", "Expression.c"),
	os.path.join("cbqs", "src", "state.c"),
	os.path.join("cbqs", "src", "model.c"),
	os.path.join("cbqs", "src", "local_search.c"),
	os.path.join("cbqs", "src", "constraint.c"),
	os.path.join("cbqs", "src", "quantum_search.c"),
	os.path.join("cbqs", "src", "approximate_state_sampler.c")
]

extensions = [
	Extension("cbqs.Constants", [os.path.join("cbqs", "Constants.py")], extra_compile_args = compiler_args),
	Extension("cbqs.StateGenerator", [os.path.join("cbqs", "StateGenerator.py")], extra_compile_args = compiler_args),
	Extension("cbqs.Expression", [os.path.join("cbqs", "Expression.pyx"), os.path.join("cbqs", "src", "Expression.c")],
	          extra_compile_args = compiler_args),
]

# Metal_executor requires macOS Objective-C runtime (-ObjC flag)
if sys.platform == "darwin":
	extensions.append(
		Extension("cbqs.Metal_executor", [
			os.path.join("cbqs", "Metal_executor.pyx"),
			os.path.join("cbqs", "src", "metal_files", "exec_metal.m")
		], extra_compile_args = compiler_args + ["-ObjC"], include_dirs = [os.path.join("cbqs", "src", "metal_files")])
	)

extensions += [
	Extension("cbqs.Model", ["cbqs/Model.pyx"] + sources, extra_compile_args = compiler_args, include_dirs = [os.path.join("cbqs", "src")]),
	Extension("cbqs.SearchLib", ["cbqs/SearchLib.pyx"] + sources, extra_compile_args = compiler_args,
	          include_dirs = [os.path.join("cbqs", "src")]),
	Extension("cbqs.state_sampler", ["cbqs/state_sampler.pyx"] + sources, extra_compile_args = compiler_args,
	          include_dirs = [os.path.join("cbqs", "src")]),
	Extension("cbqs.state", ["cbqs/state.pyx"] + sources, extra_compile_args = compiler_args,
	          include_dirs = [os.path.join("cbqs", "src")]),
	Extension("cbqs.Constraint", ["cbqs/Constraint.pyx"] + sources, extra_compile_args = compiler_args,
	          include_dirs = [os.path.join("cbqs", "src")]),
	Extension("cbqs.branching", ["cbqs/branching.pyx"] + sources, extra_compile_args = compiler_args,
	          include_dirs = [os.path.join("cbqs", "src")]),
]

setup(
	name = 'cbqs',
	version = "1.0.1",
	packages = find_packages(),
	include_package_data = True,  # Include package data
	install_requires = ["numpy", "pandas"],
	ext_modules = cythonize(extensions, language_level = 3),
)
