import os
import sys

from Cython.Build import cythonize
from setuptools import setup, find_packages
from setuptools.extension import Extension

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Compiler & linker flags for AddressSanitizer
compiler_args = ["-O3", "-flto", "-pthread"]

sources = [
	os.path.join("cbqs", "src", "solver.c"),
	os.path.join("cbqs", "src", "SearchLib.c"),
	os.path.join("cbqs", "src", "Branching.c"),
	os.path.join("cbqs", "src", "intarray.c"),
	os.path.join("cbqs", "src", "Expression.c"),
	os.path.join("cbqs", "src", "dyn_expr.c"),  # Phase 6: Dynamic expression storage
	os.path.join("cbqs", "src", "state.c"),
	os.path.join("cbqs", "src", "model.c"),
	os.path.join("cbqs", "src", "local_search.c"),
	os.path.join("cbqs", "src", "constraint.c"),
	os.path.join("cbqs", "src", "quantum_search.c"),
	os.path.join("cbqs", "src", "approximate_state_sampler.c"),
	os.path.join("cbqs", "src", "solver_ctx.c"),
	os.path.join("cbqs", "src", "prng.c"),  # Phase 4: xoshiro256** PRNG
	os.path.join("cbqs", "src", "arena.c"),  # Phase 6: Arena allocator
]

extensions = [
	Extension("cbqs.Constants", [os.path.join("cbqs", "Constants.py")], extra_compile_args = compiler_args),
	Extension("cbqs.StateGenerator", [os.path.join("cbqs", "StateGenerator.py")], extra_compile_args = compiler_args),
	Extension("cbqs.Expression", [os.path.join("cbqs", "Expression.pyx"), os.path.join("cbqs", "src", "Expression.c"), os.path.join("cbqs", "src", "dyn_expr.c")],
	          extra_compile_args = compiler_args, include_dirs = [os.path.join("cbqs", "src")]),
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
	install_requires = ["numpy", "pandas"],  # TODO: verify pandas is still needed
	ext_modules = cythonize(extensions, language_level = 3),
)
