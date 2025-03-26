import os

from Cython.Build import cythonize
from setuptools import setup, find_packages
from setuptools.extension import Extension

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

extensions = [
	Extension("iqs.Constants", ["iqs/Constants.py"]),
	Extension("iqs.Expression", ["iqs/Expression.pyx", "iqs/src/Expression.c"]),
	Extension("iqs.Metal_executor", ["iqs/Metal_executor.pyx"]),
	Extension("iqs.Model", ["iqs/Model.py"]),
	Extension("iqs.SearchLib",
	          ["iqs/SearchLib.pyx",
	           os.path.join("iqs", "src", "SearchLib.c"),
	           os.path.join("iqs", "src", "Branching.c"),
	           os.path.join("iqs", "src", "intarray.c"),
	           os.path.join("iqs", "src", "state.c"),
	           os.path.join("iqs", "src", "constraint.c")],
	          include_dirs = [os.path.join("iqs", "src")]),
]

setup(
	name = 'iqs',
	packages = find_packages(),
	include_package_data = True,  # Include package data
	install_requires = ["numpy", "pandas"],
	ext_modules = cythonize(extensions)
)
