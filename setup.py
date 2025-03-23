import os

from Cython.Build import cythonize
from setuptools import setup, find_packages
from setuptools.extension import Extension

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

extensions = [
	Extension("iqs.Constants",["iqs/Constants.py"]),
	Extension("iqs.Expression",["iqs/Expression.py"]),
	Extension("iqs.Model",["iqs/Model.py"]),
	Extension("iqs.SearchLib",
	          ["iqs/SearchLib.pyx",
	           os.path.join("iqs", "src", "SearchLib.c"),
	           os.path.join("iqs", "src", "Branching.c"),
	           os.path.join("iqs", "src", "intarray.c"),
	           os.path.join("iqs", "src", "constraint.c")],
	          include_dirs = [os.path.join("iqs", "src")]),
]

# extensions = [
# 	Extension("IQS.Solver", [os.path.join("QAE_solver", "Solver.pyx")]),
# 	Extension("IQS.Model", [os.path.join("QAE_solver", "Model.py")]),
# 	Extension("IQS.StateGenerator", [os.path.join("QAE_solver", "StateGenerator.py")]),
# 	Extension("QAE_solver.SearchLib",
# 	          [os.path.join("QAE_solver", "SearchLib.pyx"),
# 	           os.path.join("QAE_solver", "iqs", "SearchLib.c"),
# 	           os.path.join("QAE_solver", "iqs", "Branching.c"),
# 	           os.path.join("QAE_solver", "iqs", "intarray.c"),
# 	           os.path.join("QAE_solver", "iqs", "constraint.c"),
# 	           os.path.join("QAE_solver", "iqs", "circuit_generator.c"),
# 	           os.path.join("QAE_solver", "iqs", "Circuit.c"),
# 	           os.path.join("QAE_solver", "iqs", "Gate.c")],
# 	          include_dirs = [os.path.join("QAE_solver", "iqs")]),
# ]

setup(
	name = 'iqs',
	packages=find_packages(),
	package_data={'QAE_solver.generators': ['main.m']},
	include_package_data=True,  # Include package data
	install_requires = ["numpy", "pandas"],
	ext_modules = cythonize(extensions, compiler_directives = {'language_level': "3"})
)
