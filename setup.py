import os
import re
import sys
import sysconfig

from Cython.Build import cythonize
from setuptools import setup, find_packages
from setuptools.extension import Extension

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)


def _read_version():
    """Read version from cbqs/__init__.py without importing the package."""
    with open(os.path.join(script_dir, 'cbqs', '__init__.py')) as f:
        match = re.search(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", f.read(), re.MULTILINE)
    if not match:
        raise RuntimeError("Cannot find __version__ in cbqs/__init__.py")
    return match.group(1)


# ---------------------------------------------------------------------------
# Compiler flags
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    compiler_args = ["/O2", "/W3"]
else:
    compiler_args = ["-O3", "-flto", "-pthread", "-Wall", "-Wextra"]

# ---------------------------------------------------------------------------
# Shared C library -- compiled once, linked into each Cython extension
# ---------------------------------------------------------------------------
# These 15 C sources form the solver core.  Previously they were listed in
# every Extension that needed C code, causing each file to be compiled 5x.
# Using setuptools' `libraries` parameter (build_clib) compiles them once
# into a static archive (libcbqs_core.a) that each extension links against.
lib_cbqs_core_build_info = {
    'sources': [
        'cbqs/src/solver.c',
        'cbqs/src/SearchLib.c',
        'cbqs/src/Branching.c',
        'cbqs/src/intarray.c',
        'cbqs/src/Expression.c',
        'cbqs/src/dyn_expr.c',
        'cbqs/src/state.c',
        'cbqs/src/model.c',
        'cbqs/src/local_search.c',
        'cbqs/src/constraint.c',
        'cbqs/src/quantum_search.c',
        'cbqs/src/approximate_state_sampler.c',
        'cbqs/src/solver_ctx.c',
        'cbqs/src/prng.c',
        'cbqs/src/arena.c',
        'cbqs/src/variable_vector.c',
        'cbqs/src/platform.c',
    ],
    # SearchLib.c includes <Python.h>, so build_clib needs the Python
    # include directory in addition to the project source directory.
    'include_dirs': ['cbqs/src', sysconfig.get_path('include')],
    'macros': [],
}
if sys.platform == "win32":
    lib_cbqs_core_build_info['libraries'] = ['bcrypt']
lib_cbqs_core = ('cbqs_core', lib_cbqs_core_build_info)

# ---------------------------------------------------------------------------
# Extensions
# ---------------------------------------------------------------------------
import numpy as np
include_src = [os.path.join("cbqs", "src")]
include_src_numpy = include_src + [np.get_include()]

extensions = [
    # Pure-Python Cython compilations (no C sources)
    Extension("cbqs.Constants",
              [os.path.join("cbqs", "Constants.py")],
              extra_compile_args=compiler_args),
    Extension("cbqs.StateGenerator",
              [os.path.join("cbqs", "StateGenerator.py")],
              extra_compile_args=compiler_args),

    # Expression -- only needs Expression.c + dyn_expr.c (not the full library)
    Extension("cbqs.Expression",
              [os.path.join("cbqs", "Expression.pyx"),
               os.path.join("cbqs", "src", "Expression.c"),
               os.path.join("cbqs", "src", "dyn_expr.c")],
              extra_compile_args=compiler_args,
              include_dirs=include_src),
]

# Metal_executor requires macOS Objective-C runtime (-ObjC flag)
if sys.platform == "darwin":
    extensions.append(
        Extension("cbqs.Metal_executor",
                  [os.path.join("cbqs", "Metal_executor.pyx"),
                   os.path.join("cbqs", "src", "metal_files", "exec_metal.m")],
                  extra_compile_args=compiler_args + ["-ObjC"],
                  include_dirs=[os.path.join("cbqs", "src", "metal_files")])
    )

# Extensions that link against the shared cbqs_core static library
for ext_name, pyx_file in [
    ("cbqs.Model",         "cbqs/Model.pyx"),
    ("cbqs.SearchLib",     "cbqs/SearchLib.pyx"),
    ("cbqs.state_sampler", "cbqs/state_sampler.pyx"),
    ("cbqs.state",         "cbqs/state.pyx"),
    ("cbqs.Constraint",    "cbqs/Constraint.pyx"),
    ("cbqs.VariableVector", "cbqs/VariableVector.pyx"),
]:
    inc = include_src_numpy if "VariableVector" in ext_name else include_src
    extensions.append(
        Extension(ext_name, [pyx_file],
                  extra_compile_args=compiler_args,
                  include_dirs=inc,
                  libraries=['cbqs_core'])
    )

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
setup(
    name='cbqs',
    version=_read_version(),
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "numpy>=1.20",
        "joblib>=1.0",
    ],
    extras_require={
        "test": ["pytest>=7.0"],
        "dev": ["pytest>=7.0", "Cython>=3.0"],
    },
    libraries=[lib_cbqs_core],
    ext_modules=cythonize(extensions, language_level=3),
)
