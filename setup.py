import os

from Cython.Build import cythonize
from setuptools import setup, find_packages
from setuptools.extension import Extension

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

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
]

setup(
	name = 'iqs',
	packages = find_packages(),
	include_package_data = True,  # Include package data
	install_requires = ["numpy", "pandas"],
	ext_modules = cythonize(extensions, language_level = 3),
)
