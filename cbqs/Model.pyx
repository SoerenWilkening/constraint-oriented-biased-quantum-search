from copy import copy
from time import time
import time as time_mod
import warnings
from warnings import warn

import numpy as np
from joblib import Parallel, delayed
from .result import OptimizeResult
# CircuitBackendBinder is optional - requires circuit_backend directory
try:
	from .CircuitBackendBinder import circuit
except ImportError:
	circuit = None
from .Constants import *
from .Expression import Variable
from .Expression cimport Expression
from .state import state_py
from .state cimport init_state, free_state
from .Constraint import new_constraint
from .Constraint cimport add_expression_to_constraints, process_constraints
from .Expression cimport expression_t, merge_duplicate_variable_terms as c_merge_duplicate_variable_terms
from libc.stdlib cimport srand
from .SearchLib import (run_local_search, run_quantum_local_search, reset_c_flags)
from .VariableVector import _make_variable_vector, CVariableVector
from .SearchLib import run_sampling
from .StateGenerator import exact_simulator
from .state_sampler import approximate_state
from .SearchLib cimport initial_state_preparation
from .state cimport print_state
from .state cimport sw_tstbit
from .phase_params import (
	make_phase_param_defs, PhaseParamResolver, DEFAULTS as _PHASE_DEFAULTS,
	PHASES as _PHASES, PHASE_PARAM_SUFFIXES as _PHASE_SUFFIXES,
	strict_bool as _strict_bool,
)


def _merge_duplicate_variable_terms(Expression expr):
	"""Merge duplicate variable terms in an expression.

	Sorts terms by variable indices in C, then merges adjacent duplicates
	via a linear scan. O(T log T) in C with small constant factor.
	"""
	cdef int found_dup = c_merge_duplicate_variable_terms(expr.expr)
	if found_dup:
		warnings.warn(
			"Duplicate variable terms detected and merged in expression",
			UserWarning,
			stacklevel=3
		)

def _coerce_bool(value):
	"""Coerce value to bool. Accepts bool and int only (not strings)."""
	if isinstance(value, bool):
		return value
	if isinstance(value, int):
		return bool(value)
	raise ValueError(f"Cannot coerce {type(value).__name__} to bool")

_PARAM_DEFS = {
	# --- Former solve() params (new in Phase 15) ---
	'M':                        {'default': -1,    'coerce': int,          'validate': None,
	                             'description': 'Per-worker cumulative oracle budget T(n): the run terminates once a worker has spent M oracle charges (2j+1 each), regardless of improvement frequency; the wall-clock stop is disabled. -1 auto-calculates the default T(n) = (n/32)^2 + 1200. Range: -1 or >= 1. Default: -1. Set before solve.'},
	'opt_switch_oracles':       {'default': -1,    'coerce': int,          'validate': None,
	                             'description': 'Cumulative per-worker oracle count at which the optimize phase switches from constraint-tightening (opt_sat) to objective maximization (opt), replacing the legacy counter>10 heuristic (NORTHSTAR §4). The switch only fires once a feasible point exists. -1 auto-calculates int(0.1*M); the effective value is clamped to [0, int(0.25*M)] (alpha<=0.25). Set before solve.'},
	'opt_sample_cap':           {'default': 0,     'coerce': int,          'validate': lambda v: v >= 0,
	                             'validate_msg': 'opt_sample_cap must be >= 0',
	                             'description': 'bd 0o8: per-worker cap on the classical Grover-round sample count (4j^2+1) simulated in CSearch_{sat,opt_sat,opt}. 0 (default) == unbounded, the exact O(4j^2) rejection simulation (faithful but O(n*j^2) wall-time -> large-n intractable). When >0 a round draws at most this many candidates, bounding the classical sim to O(n*cap) per round. This does NOT change the oracle count (the 2j+1 charge is applied in ctg before the sim, CLAUDE.md §1.2); it only reduces the per-round success probability for rare improvers (p < ~1/cap), an APPROXIMATE sampler whose deviation is tunable via cap. Used by the large-n baseline freeze. Set before solve.'},
	'stopping_time':            {'default': -1,    'coerce': float,        'validate': lambda v: v == -1 or v > 0,
	                             'validate_msg': 'stopping_time must be > 0 (seconds) or -1 (OFF)',
	                             'description': 'Wall-clock cap in SECONDS for the ctg solve. TRAINING use only — truncates the oracle-indexed trajectory so PI/anchors become machine-dependent (faithfulness/reproducibility WAIVED, NORTHSTAR §11). <=0 = OFF (default -1): oracle-budget-only termination (faithful). Set e.g. 2700 for a 45-min training cap. Checked between Grover rounds — cannot interrupt a single in-progress large-j round. Set before solve.'},
	'stop_val':                 {'default': -1,    'coerce': int,          'validate': None,
	                             'description': 'Target objective value; solver stops early if reached. -1 disables early stopping. Range: -1 or any int. Default: -1. Set before solve.'},
	'callback':                 {'default': None,  'coerce': None,         'validate': lambda v: v is None or callable(v),
	                             'validate_msg': 'callback must be callable or None',
	                             'description': 'Zero-arg callable invoked whenever a worker records a new feasible incumbent of its own (per-worker incumbent events, bd 4uf; fires more often than the pre-4uf global-improvement gate under multi-worker solves). None disables callbacks. Default: None. Set before solve.'},
	'max_delta':                {'default': 7,     'coerce': int,          'validate': lambda v: v >= 0,
	                             'validate_msg': 'max_delta must be non-negative',
	                             'description': 'Maximum Hamming distance for neighborhood search during sampling. Larger values explore more neighbors per iteration. Range: >= 0. Default: 7. Set before solve.'},
	'reset_delta':              {'default': True,  'coerce': _coerce_bool, 'validate': None,
	                             'description': 'Whether to reset the search delta to max_delta when an improvement is found. Range: True or False. Default: True. Set before solve.'},
	'depth_look_ahead':         {'default': 0,     'coerce': int,          'validate': lambda v: v >= 0,
	                             'validate_msg': 'depth_look_ahead must be non-negative',
	                             'description': 'Number of variables to look ahead when checking feasibility during branching. 0 disables look-ahead (checks only the next variable). Range: >= 0. Default: 0. Set before solve.'},
	'num_workers':              {'default': 12,    'coerce': int,          'validate': lambda v: v >= 1,
	                             'validate_msg': 'num_workers must be >= 1',
	                             'description': 'Number of parallel worker threads for solve(). Each worker runs an independent sampling search. Range: >= 1. Default: 12. Set before solve.'},
	'ignore_constraint_search': {'default': False, 'coerce': _coerce_bool, 'validate': None,
	                             'description': 'Skip constraint-guided search during sampling; uses random branching only. Range: True or False. Default: False. Set before solve.'},
	'monte_carlo_estimate':     {'default': False, 'coerce': _coerce_bool, 'validate': None,
	                             'description': 'Use Monte Carlo probability estimation instead of exact calculation during branching. Range: True or False. Default: False. Set before solve.'},
	'verify':                   {'default': False, 'coerce': _coerce_bool, 'validate': None,
	                             'description': 'Automatically verify solution feasibility and objective correctness after solve completes. Range: True or False. Default: False. Set before solve.'},
	'track_history':            {'default': True,  'coerce': _coerce_bool, 'validate': None,
	                             'description': 'Record incumbent solution history during solve for later analysis. Range: True or False. Default: True. Set before solve.'},

	# --- Former local_search() params ---
	'distance':                 {'default': 2,     'coerce': int,          'validate': lambda v: v >= 1,
	                             'validate_msg': 'distance must be >= 1',
	                             'description': 'Neighborhood distance (k) for local search: number of variable flips explored per move. Range: >= 1. Default: 2. Set before local_search.'},
	'max_worse_acceptances':    {'default': 10,    'coerce': int,          'validate': lambda v: v >= 0,
	                             'validate_msg': 'max_worse_acceptances must be non-negative',
	                             'description': 'Maximum consecutive non-improving moves allowed before local search terminates. Range: >= 0. Default: 10. Set before local_search.'},
	'stopping_condition':       {'default': 1,     'coerce': int,          'validate': lambda v: v in (0, 1),
	                             'validate_msg': 'stopping_condition must be STOPATBEST (0) or STOPATFIRST (1)',
	                             'description': 'Local search stopping criterion. STOPATBEST (0): explore full neighborhood, pick best move. STOPATFIRST (1): accept first improving move found. Range: 0 or 1. Default: 1. Set before local_search.'},

	# --- Existing params (from Phase 12/14) ---
	'branching_bias':           {'default': None,  'coerce': float,        'validate': lambda v: v > -1,
	                             'validate_msg': 'branching_bias must be greater than -1',
	                             'description': 'Assignment bias value for the branching formula; controls preference toward 0 or 1 assignments. None means auto-set to n/4 at close(). Range: > -1 or None. Default: None (auto). Set before solve.'},
	'branching_radius':         {'default': None,  'coerce': float,        'validate': lambda v: v > 0,
	                             'validate_msg': 'branching_radius must be > 0',
	                             'description': 'Target neighborhood radius r; the harness sets bias = n/r - 2 so the realized Hamming radius is r at every n (scale-invariant, NORTHSTAR §4/§1.5). Takes precedence over branching_bias when set. Per-phase variants (sat_/opt_sat_/opt_) supported. Range: > 0 (use r < n) or None. Default: None. Set before solve.'},
	# --- bd w29 (M5 / 71e): continuous oracle-indexed opt-radius DECAY schedule ---
	'opt_radius_schedule_r_start': {'default': None, 'coerce': float,       'validate': lambda v: v > 0,
	                             'validate_msg': 'opt_radius_schedule_r_start must be > 0',
	                             'description': 'bd w29 (M5/71e): broad opt-phase radius at oracle fraction t=0 of a CONTINUOUS within-opt-phase DECAY schedule. The opt-phase bias is recomputed BETWEEN Grover rounds (faithful classical write; inner sampler byte-unchanged) from r(t)=r_end+(r_start-r_end)*(1-t)^gamma with t=total_oracles/T(n) in [0,1]. Armed iff BOTH opt_radius_schedule_r_start AND opt_radius_schedule_r_end are set; then it OVERRIDES the static opt radius in the opt phase. r_start==r_end reproduces the static lever bit-for-bit. Range: > 0 or None. Default: None. Set before solve.'},
	'opt_radius_schedule_r_end':   {'default': None, 'coerce': float,       'validate': lambda v: v > 0,
	                             'validate_msg': 'opt_radius_schedule_r_end must be > 0',
	                             'description': 'bd w29 (M5/71e): tight opt-phase radius at oracle fraction t=1 (near T(n)) of the continuous opt-radius decay schedule (see opt_radius_schedule_r_start). Range: > 0 or None. Default: None. Set before solve.'},
	'opt_radius_schedule_gamma':   {'default': None, 'coerce': float,       'validate': lambda v: v > 0,
	                             'validate_msg': 'opt_radius_schedule_gamma must be > 0',
	                             'description': 'bd w29 (M5/71e): decay-shape exponent of the opt-radius schedule. 1.0 (the default when the schedule is armed) = linear; >1 tightens EARLY (steep early, gentle near t=1); <1 stays broad longer (gentle early, steep near t=1). Range: > 0 or None. Default: None (=> 1.0 when armed). Set before solve.'},
	# --- bd a0w (M5): angle-precision lever (Ross-Selinger / gridsynth) ---
	'angle_precision_eps':      {'default': None,  'coerce': float,        'validate': lambda v: v > 0,
	                             'validate_msg': 'angle_precision_eps must be > 0',
	                             'description': 'bd a0w (M5): absolute accuracy (radians) to which the QTG per-variable rotation R_y(theta_i) is synthesized, as Ross-Selinger/gridsynth would at ~3*log2(1/eps) T-gates. The branching decision quantizes THETA (theta = 2*asin(sqrt(1-value)), p_flip = sin^2(theta/2)) -- never the probability -- to |theta_q - theta| <= eps, then re-clamps so bounded decisions (NORTHSTAR §1.7) hold by construction. Per-phase variants (sat_/opt_sat_/opt_) supported. None (or <= 0) means EXACT angles: the lever is OFF and the solve is bit-for-bit the default. Range: > 0 or None. Default: None. Set before solve.'},
	'angle_precision_dither':   {'default': False, 'coerce': _strict_bool,  'validate': None,
	                             'description': 'bd a0w (M5): synthesis model for angle_precision_eps. False (default) = ONE rotation circuit compiled once and reused for all n variables, so grid rounding is SYSTEMATIC and the realized-radius error adds coherently (~n*dtheta). True = n independently synthesized circuits, i.e. a deterministic per-variable pseudorandom residual within eps, so the radius error averages (~sqrt(n)*dtheta). The offsets are a pure function of the variable index, so determinism under a fixed seed is unaffected. Ignored when angle_precision_eps is unset. Per-phase variants supported. Default: False. Set before solve.'},
	'branching_weights':        {'default': None,  'coerce': None,         'validate': 'special',
	                             'description': 'Per-variable SIGNED logit offsets (theta_i) for the branching formula: value = sigma(logit(base) + branching_factor*theta_i). Must be a 1D finite numpy array of length n (no normalization, no non-negativity; M0f). None disables per-variable weighting. Default: None. Set before solve.'},
	'branching_factor':         {'default': None,  'coerce': float,        'validate': lambda v: v >= 0,
	                             'validate_msg': 'branching_factor must be non-negative',
	                             'description': 'Weight of the branching_weights term in the 3-term branching formula. None uses the solver default. Range: >= 0 or None. Default: None. Set before solve.'},
	'bias_factor':              {'default': None,  'coerce': float,        'validate': lambda v: v >= 0,
	                             'validate_msg': 'bias_factor must be non-negative',
	                             'description': 'Weight of the assignment_bias term in the 3-term branching formula. None uses the solver default. Range: >= 0 or None. Default: None. Set before solve.'},
	'look_ahead_factor':        {'default': None,  'coerce': float,        'validate': lambda v: v >= 0,
	                             'validate_msg': 'look_ahead_factor must be non-negative',
	                             'description': 'Weight of the look-ahead term in the 3-term branching formula. None uses the solver default (0.0, disabled). Range: >= 0 or None. Default: None. Set before solve.'},
	'timeout':                  {'default': None,  'coerce': int,          'validate': lambda v: v > 0,
	                             'validate_msg': 'timeout must be positive',
	                             'description': 'Hard timeout in seconds; overrides stopping_time if set. None means use stopping_time instead. Range: > 0 or None. Default: None. Set before solve.'},
}

# Merge phase-specific parameter definitions (24 params: 3 phases x 8 suffixes)
_phase_defs = make_phase_param_defs()
# Add validation rules to scalar phase params
_PHASE_VALIDATORS = {
	'branching_bias': (lambda v: v > -1, 'branching_bias must be greater than -1'),
	'branching_radius': (lambda v: v > 0, 'branching_radius must be > 0'),
	'branching_factor': (lambda v: v >= 0, 'branching_factor must be non-negative'),
	'bias_factor': (lambda v: v >= 0, 'bias_factor must be non-negative'),
	'angle_precision_eps': (lambda v: v > 0, 'angle_precision_eps must be > 0'),
}
for _phase in _PHASES:
	for _suffix in _PHASE_SUFFIXES:
		_key = f"{_phase}_{_suffix}"
		if _suffix in _PHASE_VALIDATORS:
			_check, _msg = _PHASE_VALIDATORS[_suffix]
			_phase_defs[_key]['validate'] = _check
			_phase_defs[_key]['validate_msg'] = _msg
_PARAM_DEFS.update(_phase_defs)

_KNOWN_PARAMS = set(_PARAM_DEFS.keys())

cdef class Model:
	"""Constraint-oriented biased quantum search model.

	The central class for defining and solving combinatorial optimization
	and satisfiability problems using quantum-inspired branching search,
	local search, or quantum local search algorithms.

	Typical usage follows a five-step workflow:

	1. **Add variables** -- ``add_variable()`` / ``add_variables()``
	2. **Set objective** -- ``set_objective(expr, sense)``
	3. **Add constraints** -- ``add_constraint(expr <= rhs)``
	4. **Close the model** -- ``close()`` (preprocesses constraints)
	5. **Solve** -- ``solve()`` / ``local_search()``

	Solver parameters are configured via ``set_param()`` before calling
	the solve method. Results are returned as ``OptimizeResult`` objects.

	Method groups
	-------------
	Modeling : add_variable, add_variables, set_objective, add_constraint, close
	Parameters : set_param, get_param
	Solving : solve, local_search, quantum_local_search
	Results : objective_value, solution, oracle_calls, runtime
	Reproducibility : seed, seed_used, num_threads
	Verification : verify_solution

	Examples
	--------
	>>> from cbqs import Model, MAXIMIZE
	>>> m = Model()
	>>> x = m.add_variables(3)
	>>> m.set_objective(x[0] + 2*x[1] + x[2], MAXIMIZE)
	>>> m.add_constraint(x[0] + x[1] + x[2] <= 2)
	>>> m.close()
	>>> m.set_param('num_workers', 4)
	>>> result = m.solve()
	>>> print(result.objective)
	"""

	def __cinit__(self):
		self.mod = init_model()
		self.gpu_imported = False

	def __init__(self):
		self.initialized = False
		self.sparsity = None
		self.stgen = None
		self.global_opt = None
		self.gpu_imported: bool = False

		self.calls = 0
		self.met = None
		self.objective: new_constraint = new_constraint()
		self.constraint: new_constraint = new_constraint()

		self.obj_expr = []
		self.con_expr = []

		self.sense = MAXIMIZE

		self.n: int = 0
		self.variables = {}

		self.initial_state: state_py | None = None

		self.mod.solver = SATISFY

		self.feasible = 0
		self.grover_iterations: list[int] | int = 0
		self.quantum_cycles: list[int] | int = 0
		self.final_state: list[state_py] | state_py | list | None = None
		self.improved: bool = False

		self.gpu_compiled: bool = False

		self.constraints_compiled: bool = False

		self.circuit: circuit | None = None

		# Post-solve verification (Phase 7)
		self._verified = None  # None = not verified, True = passed, False = failed

		# Thread isolation (Phase 4): seed and thread configuration
		self._seed = None  # None = auto-generate
		self._num_threads = None  # None = auto-detect
		self._seed_used = None  # Populated after solve() by SearchLib

		# Generic parameter storage (Phase 12)
		self._params = {}

	def set_param(self, str name, value):
		"""Set a solver parameter by name.

		Parameters persist across multiple solve() calls until changed.
		Passing None resets the parameter to its default value.
		Type coercion is applied automatically (e.g., ``set_param('M', '100')``
		stores ``int(100)``). Validation is performed at set-time.

		Parameters
		----------
		name : str
			Parameter name. See ``_PARAM_DEFS`` for the full list.
		value : object
			Value to set. Pass ``None`` to reset to default.

		Raises
		------
		ValueError
			If *name* is unknown or *value* fails validation.

		Examples
		--------
		>>> m.set_param('num_workers', 4)
		>>> m.set_param('stopping_time', 60)
		>>> m.set_param('num_workers', None)  # reset to default (12)
		"""
		if name not in _KNOWN_PARAMS:
			raise ValueError(f"Unknown parameter: '{name}'")

		# Reset to default: remove from _params so get_param returns default
		if value is None:
			self._params.pop(name, None)
			return

		pdef = _PARAM_DEFS[name]

		# Special case: branching_weights (unprefixed and phase-specific)
		if name == 'branching_weights' or name.endswith('_branching_weights'):
			arr = np.asarray(value, dtype=np.float64)
			if arr.ndim != 1:
				raise ValueError("branching_weights must be a 1D array")
			if self.n > 0 and len(arr) != self.n:
				raise ValueError(
					f"Expected array of length {self.n}, got {len(arr)}"
				)
			# M0f: branching_weights are SIGNED per-variable logit offsets
			# (theta_i) -- no non-negativity check (the L1 normalization that
			# motivated it was dropped too). NaN/Inf are still rejected.
			if np.any(np.isnan(arr)) or np.any(np.isinf(arr)):
				raise ValueError(
					"branching_weights must not contain NaN or Inf"
				)
			self._params[name] = value
			return

		# Special case: variable_priorities (phase-specific)
		if name.endswith('_variable_priorities'):
			arr = np.asarray(value, dtype=np.float64)
			if arr.ndim != 1:
				raise ValueError("variable_priorities must be a 1D array")
			if self.n > 0 and len(arr) != self.n:
				raise ValueError(
					f"Expected array of length {self.n}, got {len(arr)}"
				)
			self._params[name] = value
			return

		# Type coercion
		if pdef['coerce'] is not None:
			try:
				value = pdef['coerce'](value)
			except (ValueError, TypeError) as e:
				raise ValueError(
					f"Cannot coerce value for '{name}': {e}"
				) from None

		# Validation
		if pdef['validate'] is not None and pdef['validate'] != 'special':
			if not pdef['validate'](value):
				msg = pdef.get('validate_msg', f"Invalid value for {name}: {value}")
				raise ValueError(msg)

		self._params[name] = value

	def get_param(self, str name):
		"""Get a solver parameter by name.

		Returns the stored value if previously set via ``set_param()``,
		or the documented default otherwise.

		Parameters
		----------
		name : str
			Parameter name. See ``_PARAM_DEFS`` for the full list.

		Returns
		-------
		object
			Current parameter value.

		Raises
		------
		ValueError
			If *name* is unknown.
		"""
		if name not in _KNOWN_PARAMS:
			raise ValueError(f"Unknown parameter: '{name}'")
		if name in self._params:
			return self._params[name]
		return _PARAM_DEFS[name]['default']

	def _get_effective(self, str name):
		"""Get effective param value: stored value if set, else default from _PARAM_DEFS."""
		val = self._params.get(name)
		if val is not None:
			return val
		return _PARAM_DEFS[name]['default']

	def _resolve_phase_params(self):
		"""Resolve phase-specific parameters with fallback to unprefixed defaults.

		Uses PhaseParamResolver to resolve all 24 phase-specific parameters
		(3 phases x 8 suffixes) with the resolution order:
		    phase-specific > unprefixed > built-in default

		Returns
		-------
		dict
			``{phase: {suffix: value}}`` for all phases and suffixes.
		"""
		resolver = PhaseParamResolver(self._params, _PHASE_DEFAULTS)
		return resolver.resolve_all()

	def __copy__(self):
		"""Create a shallow copy of this model.

		Copies the objective and constraint containers (including their
		underlying C data), the initial state, solver mode, optimization
		sense, and all parameter settings. The copy shares no mutable
		state with the original and can be solved independently.

		Returns
		-------
		Model
			A new Model instance with copied state.
		"""
		new_m = Model()
		new_m.objective = copy(self.objective)
		new_m.constraint = copy(self.constraint)
		new_m.initial_state = copy(self.initial_state)
		new_m.mod.solver = self.mod.solver
		new_m.sense = self.sense
		new_m._params = dict(self._params)
		return new_m

	def __str__(self):
		if not self.improved:
			return "No better solution found"
		return f"""
Found solution with Objective = {self.objective_value}
using either {self.grover_iterations} grover iterations 
or {self.runtime}s sampling
		"""

	def reset(self):
		"""Reset solve state so the model can be re-solved.

		Clears the solution, objective value, improvement flag, and initial
		state while keeping variables, constraints, objectives, and parameters
		intact. Call this between successive solve() calls on the same model.
		"""
		self.quantum_cycles: int = 0
		self.final_state: state_py | None = None
		self.improved: bool = False
		self.global_opt = None
		self.initialized = False
		# Free and reset C-level global_opt and initial_state so the
		# solver starts fresh (manual_initial will re-initialize them).
		if self.mod.global_opt is not NULL:
			free_state(self.mod.global_opt, 1)
			self.mod.global_opt = NULL
		if self.mod.initial_state is not NULL:
			free_state(self.mod.initial_state, 1)
			self.mod.initial_state = NULL
		self.mod.runtime = 0.0
		self.mod.qtg_applications = 0

	def add_variable(self, index: int = 0, name: str = "x", bound: int = 1) -> int | Variable | Expression:
		"""Add a single decision variable to the model.

		For binary variables (bound=1), returns a ``Variable``. For bounded
		integer variables (bound>1), automatically creates auxiliary binary
		variables and an upper-bound constraint, returning an ``Expression``
		representing the integer value.

		Parameters
		----------
		index : int, optional
			Variable index. If less than the current variable count,
			the next available index is used. Default: 0.
		name : str, optional
			Variable name prefix. Default: ``"x"``.
		bound : int, optional
			Upper bound on the variable value. 1 for binary, >1 for
			bounded integer (encoded with ceil(log2(bound))+1 bits).
			Default: 1.

		Returns
		-------
		Variable or Expression
			A ``Variable`` for binary, or an ``Expression`` for bounded
			integer variables.

		Examples
		--------
		>>> x = m.add_variable(name="x")       # binary variable
		>>> y = m.add_variable(bound=7)         # integer variable 0..7
		"""
		if bound > 1:
			number = int(np.floor(np.log2(bound))) + 1
			x = self.add_variables(number, name = name)
			expr = sum(2 ** i * x[list(x.keys())[i]] for i in range(number))
			self.add_constraint(expr <= bound)
			return expr

		x = Variable(max(index, self.n), f"{name}{max(index, self.n)})")
		self.variables[max(index, self.n)] = x
		self.n += 1
		return x

	def add_variables(self, n: int = 1, name: str = "x", bound = 1):
		"""Add multiple decision variables to the model.

		Creates *n* variables and returns a :class:`CVariableVector` for
		binary variables or a ``dict`` for bounded integers.

		Parameters
		----------
		n : int, optional
			Number of variables to add. Must be >= 1. Default: 1.
		name : str, optional
			Variable name prefix. Variables are named ``{name}{index}``.
			Default: ``"x"``.
		bound : int, optional
			Upper bound per variable. 1 for binary, >1 for bounded
			integer (each encoded with multiple bits). Default: 1.

		Returns
		-------
		CVariableVector or dict
			For binary (bound=1): CVariableVector with dict-like access.
			For bounded integer: dict mapping index to Expression.

		Raises
		------
		ValueError
			If *n* < 1.

		Examples
		--------
		>>> x = m.add_variables(5)          # 5 binary variables
		>>> y = m.add_variables(3, bound=7) # 3 integer variables 0..7
		"""
		cdef int i
		cdef int start
		if n < 1:
			raise ValueError(f"Number of variables must be >= 1, got {n}")
		if bound > 1:
			x = {}
			for i in range(n):
				x[i] = self.add_variable(self.n, name = name, bound = bound)
			return x
		start = self.n
		vec = _make_variable_vector(self, start, n, name_prefix=name)
		for i in range(n):
			self.variables[start + i] = Variable(start + i, f"{name}{start + i}")
		self.n += n
		return vec

	def set_objective(self, Expression objective = None, sense: int = MAXIMIZE, validate = True) -> None:
		"""Set the objective function and optimization sense.

		The objective expression defines what to optimize. In SATISFY mode
		(no objective set), the solver searches for any feasible solution.

		Parameters
		----------
		objective : Expression
			The objective expression to maximize or minimize.
		sense : int, optional
			``MAXIMIZE`` or ``MINIMIZE``. Default: ``MAXIMIZE``.
		validate : bool, optional
			Whether to validate inputs and merge duplicate terms.
			Default: True. Pass ``False`` to skip both ``merge()``
			and ``_merge_duplicate_variable_terms()`` for expressions
			that are already clean (e.g. produced by ``bilinear_reduce``
			/ matmul, where each (i,j) pair appears exactly once).

		Raises
		------
		ValueError
			If *objective* is None (when validate=True).
		TypeError
			If *sense* is not MAXIMIZE or MINIMIZE.

		Examples
		--------
		>>> x = m.add_variables(3)
		>>> m.set_objective(x[0] + 2*x[1] + x[2], MAXIMIZE)
		"""
		if sense not in [MINIMIZE, MAXIMIZE]:
			raise TypeError(
				f"Invalid sense {sense}. Use MAXIMIZE ({MAXIMIZE}) or MINIMIZE ({MINIMIZE})"
			)
		if validate:
			if objective is None:
				raise ValueError("Objective expression cannot be None")

		self.sense = sense
		self.mod.solver = OPTIMIZE
		expr = objective
		if validate:
			expr.merge()
			_merge_duplicate_variable_terms(expr)
		if sense == MINIMIZE:
			expr = expr <= 0
		else:
			expr = expr >= 0

		self.obj_expr.append(expr)
		add_expression_to_constraints(self.mod.obj, <expression_t *> objective.expr)
		self.objective.add_expression(expr)

	def add_constraint(self, Expression constraint = None, validate = True) -> None:
		"""Add a constraint to the model.

		The constraint must be an ``Expression`` with a comparison applied
		(``<=``, ``>=``, or ``==``). Raw expressions without a comparison
		operator are rejected.

		Parameters
		----------
		constraint : Expression
			A constraint expression created via comparison operators,
			e.g., ``expr <= 5`` or ``expr == 0``.
		validate : bool, optional
			Whether to validate inputs and merge duplicate terms.
			Default: True. Pass ``False`` to skip both ``merge()``
			and ``_merge_duplicate_variable_terms()`` for expressions
			that are already clean (e.g. produced by ``bilinear_reduce``
			/ matmul, where each (i,j) pair appears exactly once).

		Raises
		------
		ValueError
			If *constraint* is None or has no comparison operator applied.

		Examples
		--------
		>>> x = m.add_variables(3)
		>>> m.add_constraint(x[0] + x[1] + x[2] <= 2)
		>>> m.add_constraint(x[0] + x[1] >= 1)
		"""
		if validate:
			if constraint is None:
				raise ValueError("Constraint cannot be None")
			if constraint.sense == -2:
				raise ValueError(
					"Expression is not a constraint. Apply <=, >=, or == first "
					"(e.g., expr <= 5)"
				)
		expr = constraint
		if validate:
			expr.merge()
			_merge_duplicate_variable_terms(expr)
		add_expression_to_constraints(self.mod.con, <expression_t *> constraint.expr)
		self.constraint.add_expression(expr)
		self.con_expr.append(expr)

	def manual_initial(self, P: int, assignment: list) -> None:
		"""Set an explicit initial state for the solver.

		Overrides the default all-zeros starting point with a user-supplied
		variable assignment. Used when a good starting solution is already
		known (e.g., from a heuristic or previous run).

		Parameters
		----------
		P : int
			ADVISORY initial value for the state's ``tot_profit`` slot. It is
			**not** read back as the objective, and what it does depends on
			whether ``assignment`` is feasible — because the C core stores a
			DIFFERENT quantity in that one slot in each phase:

			* **Feasible ``assignment``** — ``P`` is **IGNORED**. ``ctg``
			  recomputes the objective from ``assignment`` itself
			  (``objective_value``) on entry, so ``result.objective`` always
			  describes ``result.solution``. This is deliberate: that state is
			  also stamped feasible and seeded into the shared incumbent, so an
			  unvalidated ``P`` would otherwise be published as a *confidently
			  feasible* wrong answer (bd 47j).
			* **Infeasible ``assignment``** — ``P`` is **HONOURED**, but as a
			  constraint-VIOLATION bound, not an objective: phase 1 keeps a
			  violation sum in ``tot_profit`` and accepts a candidate only when
			  ``tot_profit > total_violation``. A small ``P`` (the ``0`` of the
			  default cold start) accepts nothing short of full feasibility; a
			  large ``P`` also accepts intermediate violation reductions, which
			  changes the trajectory (measured). Recomputing an objective here
			  would be meaningless — the field does not hold one in phase 1.

			Callers that want the objective of a feasible warm start reported
			back do not need to supply it; callers that pass a wrong ``P``
			cannot corrupt a feasible start's reported objective.
		assignment : list of int
			Binary assignment array of length *n* (one entry per variable,
			each 0 or 1).
		"""
		self.initialized = True

		arr = np.array(assignment, dtype = np.int32)
		cdef int * ptr = <int *> calloc(arr.shape[0], sizeof(int))
		for i in range(arr.shape[0]): ptr[i] = <int> arr[i]
		self.mod.initial_state = init_state(P, ptr, arr.shape[0])
		self.mod.global_opt = init_state(P, ptr, arr.shape[0])
		free(<void *> ptr)

	def compile(self):
		"""No-op retained for backward compatibility.

		.. deprecated::
			This method is no longer needed. Constraint preprocessing
			is handled by ``close()``. Calling ``compile()`` has no
			effect.
		"""
		self.gpu_compiled = True

	def __del__(self):
		free_model(self.mod)
		if self.final_state is not None: self.final_state = None
		if self.initial_state is not None: self.initial_state = None
		self.objective = None
		self.constraint = None
		self.circuit = None

	def close(self, enforce_density = False, validate = True):
		"""Preprocess constraints and prepare the model for solving.

		Must be called after all variables, objectives, and constraints
		have been added and before any solve method. Builds internal
		index structures for efficient constraint evaluation during search.

		If ``branching_bias`` has not been set via ``set_param()``, it is
		automatically initialized to ``n / 4``.

		Parameters
		----------
		enforce_density : bool, optional
			Force dense constraint representation regardless of sparsity.
			Default: False (auto-detect based on clause density).
		validate : bool, optional
			Check that variables and constraints exist before closing.
			Default: True.

		Raises
		------
		ValueError
			If the model has no variables or no constraints (when
			validate=True).
		"""
		if validate:
			if self.n == 0:
				raise ValueError("Model has no variables; add variables before closing")
			if len(self.con_expr) == 0:
				raise ValueError("Model has no constraints; add constraints before closing")
		if not self.constraints_compiled:
			self.objective.process(self.n)
			# bd 3c4: also preprocess the Python-side self.constraint, symmetric with
			# self.objective above. close() processed the C-model constraint
			# (self.mod.con, used by solve()/ctg) but NOT this object, so its
			# incremental-eval index arrays (positive/negative_indices+offsets) stayed
			# NULL -- and the quantum_local_search path consumes self.constraint
			# directly, segfaulting in adjusted_constraint_violation on the NULL arrays.
			self.constraint.process(self.n)
			process_constraints(self.mod.obj, self.n, enforce_density)
			process_constraints(self.mod.con, self.n, enforce_density)
			# Set default branching bias if not explicitly configured via set_param
			if 'branching_bias' not in self._params:
				self._params['branching_bias'] = self.n / 4
			self.constraints_compiled = True

	def general_greedy(self):
		"""Run a greedy construction heuristic to build an initial solution.

		Assigns variables one by one using the C-level greedy algorithm.
		The result is stored as the initial state for subsequent solve calls.
		If no initial state has been set, a default all-zeros state is
		created first.

		Returns
		-------
		tuple ``(value, feasible)``
			``feasible`` (bool): whether the greedy construction satisfies all
			constraints. ``value`` (int or None): the greedy objective
			(``global_opt.tot_profit * sense``, same space as ``objective_value``
			and the incumbent history) when feasible, else ``None`` — an infeasible
			greedy ``tot_profit`` holds a constraint-violation sum, not an objective.

			This is a pure read of fields ``initial_state_preparation`` just wrote
			into ``global_opt`` (solver.c); the greedy value is only live in the
			window BEFORE ``solve()`` overwrites ``global_opt``. The warm harness
			(bd 8an.9) captures it here to seed the faithful oracle-0 incumbent
			(``benchmarks.baselines.warm_repair_history``).
		"""
		if not self.initialized:
			self.manual_initial(0, [0] * self.n)
		initial_state_preparation(self.mod)
		cdef bint greedy_feasible = self.mod[0].global_opt[0].feasible
		greedy_value = self.objective_value if greedy_feasible else None
		return greedy_value, bool(greedy_feasible)

	def solve(self):
		"""Solve the optimization or satisfiability problem.

		Uses quantum-inspired biased sampling search with configurable
		branching, look-ahead, and multi-threaded parallel workers. All
		solver parameters are configured via ``set_param()`` before
		calling ``solve()``. This method takes no arguments.

		The model must be closed (via ``close()``) before solving.

		Returns
		-------
		OptimizeResult
			Result object containing:
			- ``solution`` (ndarray): best variable assignment found
			- ``objective`` (int): best objective value
			- ``feasible`` (bool): whether the solution satisfies all constraints
			- ``solve_time`` (float): wall-clock solve time in milliseconds
			- ``history`` (list): incumbent history if track_history is True
			- ``verified`` (bool or None): verification result if verify is True

		Raises
		------
		ValueError
			If constraints have not been compiled (``close()`` not called).

		Examples
		--------
		>>> m = Model()
		>>> x = m.add_variables(5)
		>>> m.set_objective(sum(x[i] for i in x), MAXIMIZE)
		>>> m.add_constraint(sum(x[i] for i in x) <= 3)
		>>> m.close()
		>>> m.set_param('num_workers', 4)
		>>> m.set_param('stopping_time', 30)
		>>> result = m.solve()
		>>> print(result.objective, result.feasible)
		"""
		if not self.constraints_compiled:
			raise ValueError("No constraints compiled")

		# Read all params from _params (with defaults from _PARAM_DEFS)
		M = self._get_effective('M')
		opt_switch_oracles = self._get_effective('opt_switch_oracles')
		opt_sample_cap = self._get_effective('opt_sample_cap')
		stopping_time = self._get_effective('stopping_time')
		stop_val = self._get_effective('stop_val')
		callback = self._get_effective('callback')
		max_delta = self._get_effective('max_delta')
		reset_delta = self._get_effective('reset_delta')
		depth_look_ahead = self._get_effective('depth_look_ahead')
		num_workers = self._get_effective('num_workers')
		ignore_constraint_search = self._get_effective('ignore_constraint_search')
		monte_carlo_estimate = self._get_effective('monte_carlo_estimate')
		verify = self._get_effective('verify')
		track_history = self._get_effective('track_history')

		self.calls += 1

		if self.mod.solver == SATISFY:
			if M != -1: warn("Defined M will be ignored when solving SAT")
			if stop_val != -1: warn("Defined stop_val will be ignored when solving SAT")

		if not self.initialized: self.manual_initial(0, [0] * self.n)
		# Default per-worker oracle budget T(n) = (n/32)^2 + 1200 (NORTHSTAR §3/§11;
		# lowered from (n/4)^2 on 2026-06-11, bd 8an.4.9 — quadratic shape kept,
		# depth constant /8, for large-n freeze tractability). mod->M is a
		# *cumulative* oracle cap enforced by the never-reset total_oracles
		# accumulator in ctg (the wall-clock stop is disabled there), so the run
		# terminates at ~T(n) oracles regardless of improvement frequency.
		if M == -1: M = int((self.n / 32.0) ** 2 + 1200)

		# M0f: opt_sat->opt exploit->explore switch point, in cumulative oracle
		# units (NORTHSTAR §4), replacing the legacy counter>10. -1 auto-defaults
		# to 10% of the budget; the effective value is clamped to [0, 0.25*M]
		# (alpha<=0.25). The switch is additionally gated on feasibility in ctg,
		# so it can never run CSearch_opt before a feasible point exists.
		if opt_switch_oracles == -1:
			opt_switch_oracles = int(0.1 * M)
		opt_switch_oracles = max(0, min(opt_switch_oracles, int(0.25 * M)))

		not_stop = [1]

		self.mod.M = M
		self.mod.opt_switch_oracles = opt_switch_oracles
		self.mod.opt_sample_cap = opt_sample_cap
		self.mod.depth_look_ahead = depth_look_ahead
		self.mod.stop_val = stop_val
		self.mod.stopping_time = stopping_time
		self.mod.ignore_constraint_search = ignore_constraint_search
		self.mod.monte_carlo_estimate = monte_carlo_estimate
		self.mod.max_delta = max_delta
		self.mod.reset_delta = reset_delta

		solve_start_time = time_mod.monotonic()
		res = Parallel(n_jobs = num_workers, backend = "threading")(
			delayed(run_sampling)(self, callback, not_stop, track_history, solve_start_time, worker_id)
			for worker_id in range(num_workers)
		)

		reset_c_flags()
		# res[i] = (cur_sol, oracle_count_i, feasible, arr, t_total, incumb, history, preprocessing_time_ms, branch_diag, worker_runtime_s)
		# res[i][1] is worker i's own race-free oracle count. Portfolio cost
		# convention (NORTHSTAR §6/§11): each worker is capped at T(n) and scored
		# best-of-P, so the reported oracle cost is the per-worker budget ~T(n).
		# Write it once here, single-threaded, into the (now unwritten-by-ctg)
		# qtg_applications slot so the result/property read a race-free value.
		self.mod.qtg_applications = max((r[1] for r in res), default=0)
		# bd lif: ctg now writes its wall-clock telemetry to the per-worker
		# ctx->runtime (r[9]) instead of the racy shared mod->runtime. Reduce it
		# max-over-workers (the portfolio finishes when the slowest worker does)
		# once here, single-threaded, into the (now unwritten-by-ctg) mod->runtime
		# slot so result.solve_time and the .runtime property read a race-free value.
		self.mod.runtime = max((r[9] for r in res), default=0.0)
		self.final_state = self.global_opt

		# Per-worker FINAL incumbents (value, feasible) -- r[5] -- for §8.3
		# median-of-P / best-of-P outcome-diversity gate (NORTHSTAR §8.3, M0e).
		final_incumbents = [r[5] for r in res]

		# Best-of-portfolio improvement curve vs ORACLE budget (NORTHSTAR §11/§1.3 M0e):
		# concatenate the per-worker (value, oracle, elapsed_s) streams, sort by oracle,
		# and keep the running-best value (bd qls: the kept entry is the producing
		# worker's full triple, so `history` also carries wall-clock elapsed). bd 4uf: streams are now COMPLETE per-worker incumbent
		# logs (no longer filtered by the wall-time global_opt race), so this running-
		# best filter is LOAD-BEARING for the best-of-P curve — different workers'
		# streams overlap and most cross-worker events are dominated. Each worker's own
		# stream is monotone (a worker's incumbents only improve), and the merged curve
		# is a pure function of (master seed, worker_id, P) — scheduling-independent,
		# which is what makes the §6 PI deterministic. For MAXIMIZE this is the
		# running-MAX; MINIMIZE/SATISFY keep the running-min in their improving
		# direction.
		if track_history:
			merged = []
			for r in res:
				merged.extend(r[6])
			merged.sort(key=lambda entry: entry[1])  # by oracle stamp
			if self.mod[0].solver == SATISFY or self.sense != MAXIMIZE:
				is_better = lambda new, best: new < best
			else:
				is_better = lambda new, best: new > best
			merged_history = []
			best_val = None
			for entry in merged:
				value = entry[0]
				if best_val is None or is_better(value, best_val):
					best_val = value
					merged_history.append(entry)
		else:
			merged_history = []

		# bd o3f: keep the raw per-worker streams (index == worker_id) so the
		# user can replay the running-max over any worker subset post hoc.
		# Same (value, oracle, elapsed_s) schema; `history` above is exactly
		# their running-max merge.
		worker_histories = [list(r[6]) for r in res] if track_history else []

		# Extract solution array from global_opt
		cdef int n_bits = self.mod[0].global_opt[0].vector.bits
		solution = np.array([sw_tstbit(self.mod[0].global_opt[0].vector, i) for i in range(n_bits)], dtype=np.int32)

		# Handle verification
		if verify:
			with warnings.catch_warnings(record=True) as caught_warnings:
				warnings.simplefilter("always")
				self.verify_solution()
			verified = self._verified
			violations = [str(w.message) for w in caught_warnings]
		else:
			verified = None
			violations = None

		# Determine feasibility
		if self.mod[0].solver == SATISFY:
			# In SATISFY mode, feasibility means all constraints are satisfied.
			# The C-level global_opt.feasible flag is not reliably set for SATISFY,
			# so check tot_profit against the expected stop value instead.
			# Cast to Python int to avoid C signed/unsigned comparison issues.
			is_feasible = (int(self.mod[0].global_opt[0].tot_profit)
			               == -int(self.mod[0].con[0].num_constraints))
		else:
			is_feasible = bool(self.mod[0].global_opt[0].feasible)

		# Opt-phase branching diagnostics, pooled across the decorrelated workers
		# (M0g / bd 8an.1.7, NORTHSTAR §9). Each worker's ctx counted, over every
		# candidate CSearch_opt generated, the realized Hamming radius (NumChanges)
		# and the # of both-feasible "free" decisions. Pooling the raw sums across
		# workers (they are i.i.d. samples of the same instance under decorrelated
		# seeds) gives the realized-radius mean+variance and the free-decision
		# fraction f(n) the scale-invariance test compares across n. The raw pooled
		# sums are kept so callers can re-pool across seeds/instances.
		_bd_cand = sum(r[8]["opt_candidates"] for r in res)
		_bd_flip = sum(r[8]["opt_flip_sum"]   for r in res)
		_bd_fsq  = sum(r[8]["opt_flip_sumsq"] for r in res)
		_bd_free = sum(r[8]["opt_free_sum"]   for r in res)
		if _bd_cand > 0:
			_r_mean = _bd_flip / _bd_cand
			_r_var = max(0.0, _bd_fsq / _bd_cand - _r_mean * _r_mean)
			_f_n = _bd_free / (_bd_cand * n_bits) if n_bits > 0 else None
		else:
			_r_mean = None
			_r_var = None
			_f_n = None
		# M2a (bd 8an.3.1, NORTHSTAR §4/§12): per-phase decision-touch pooling.
		# For each phase, pool the raw per-worker counters and derive the
		# touch fraction = consulted / decisions, where "consulted" encodes the
		# per-phase semantics ONCE (solver.c): both-feasible is consulted in
		# every phase; both-infeasible is consulted ONLY in opt_sat (sat forces
		# bit=0, opt truncates the candidate). None (not 0.0) when the phase
		# never ran — unmeasured, not measured-zero.
		_dt = {}
		for _ph, _kd, _kf, _kb, _kx, _binf_consulted in (
			("sat",     "sat_decisions",    "sat_free",     "sat_bothinf",    "sat_forced",    False),
			("opt_sat", "optsat_decisions", "optsat_free",  "optsat_bothinf", "optsat_forced", True),
			("opt",     "opt_decisions",    "opt_free_sum", "opt_bothinf",    "opt_forced",    False),
		):
			_dec  = sum(r[8][_kd] for r in res)
			_free = sum(r[8][_kf] for r in res)
			_binf = sum(r[8][_kb] for r in res)
			_forc = sum(r[8][_kx] for r in res)
			_consulted = _free + (_binf if _binf_consulted else 0)
			_dt[_ph] = {
				"decisions": int(_dec),
				"free": int(_free),
				"bothinf": int(_binf),
				"forced": int(_forc),
				"touch_fraction": (_consulted / _dec) if _dec > 0 else None,
			}
		branch_diagnostics = {
			"n": int(n_bits),
			"opt_candidates": int(_bd_cand),
			"radius_mean": _r_mean,
			"radius_var": _r_var,
			"free_fraction": _f_n,
			"opt_flip_sum": int(_bd_flip),
			"opt_flip_sumsq": int(_bd_fsq),
			"opt_free_sum": int(_bd_free),
			"decision_touch": _dt,
			"per_worker": [dict(r[8]) for r in res],
		}

		# Build OptimizeResult
		result = OptimizeResult(
			solution=solution,
			objective=self.objective_value,
			feasible=is_feasible,
			solve_time=self.mod[0].runtime * 1000.0,
			preprocessing_time=max(r[7] for r in res),
			iterations=self.mod[0].qtg_applications,
			oracle_calls=self.mod[0].qtg_applications,
			history=merged_history,
			verified=verified,
			violations=violations,
			num_threads=num_workers,
			seed=self._seed_used if self._seed_used is not None else 0,
			final_incumbents=final_incumbents,
			branch_diagnostics=branch_diagnostics,
			worker_histories=worker_histories,
		)

		return result

	def local_search(self):
		"""Execute the local search solver.

		Iteratively improves the current solution by exploring k-flip
		neighborhoods with tabu-list cycling prevention. All parameters
		are configured via ``set_param()`` before calling. Key
		parameters: ``distance``, ``max_worse_acceptances``,
		``stopping_condition``, ``stopping_time``.

		Returns
		-------
		OptimizeResult
			Result object with the same fields as ``solve()``.

		Examples
		--------
		>>> m.close()
		>>> m.set_param('distance', 3)
		>>> m.set_param('max_worse_acceptances', 20)
		>>> result = m.local_search()
		>>> print(result.objective, result.feasible)
		"""
		# Read all params from _params (with defaults from _PARAM_DEFS)
		distance = self._get_effective('distance')
		callback = self._get_effective('callback')
		stopping_time = self._get_effective('stopping_time')
		max_worse_acceptances = self._get_effective('max_worse_acceptances')
		stopping_condition = self._get_effective('stopping_condition')
		verify = self._get_effective('verify')
		track_history = self._get_effective('track_history')

		if not self.initialized: self.manual_initial(0, [0] * self.n)

		self.mod[0].max_worse_acceptances = max_worse_acceptances
		self.mod[0].stopping_condition = stopping_condition
		self.mod[0].distance = distance
		self.mod[0].stopping_time = stopping_time
		self.mod[0].stop_val = -1

		# run_local_search returns (cur_sol, history, preprocessing_time_ms, solve_time_ms)
		solve_start_time = time_mod.monotonic()
		cur_sol, history, preprocessing_time_ms, solve_time_ms = run_local_search(self, callback, track_history, solve_start_time)
		self.final_state = cur_sol

		# Extract solution array from global_opt
		cdef int n_bits = self.mod[0].global_opt[0].vector.bits
		solution = np.array([sw_tstbit(self.mod[0].global_opt[0].vector, i) for i in range(n_bits)], dtype=np.int32)

		# Handle verification
		if verify:
			with warnings.catch_warnings(record=True) as caught_warnings:
				warnings.simplefilter("always")
				self.verify_solution()
			verified = self._verified
			violations = [str(w.message) for w in caught_warnings]
		else:
			verified = None
			violations = None

		# Build and return OptimizeResult
		result = OptimizeResult(
			solution=solution,
			objective=self.objective_value,
			feasible=bool(self.mod[0].global_opt[0].feasible),
			solve_time=solve_time_ms,
			preprocessing_time=preprocessing_time_ms,
			iterations=self.mod[0].qtg_applications,
			oracle_calls=self.mod[0].qtg_applications,
			history=history,
			verified=verified,
			violations=violations,
			num_threads=self._num_threads if self._num_threads is not None else 1,
			seed=self._seed_used if self._seed_used is not None else 0,
		)

		return result

	def quantum_local_search(self):
		"""Execute the quantum local search solver.

		Combines local search neighborhood exploration with quantum-inspired
		Grover amplification. Runs multi-threaded workers that each
		independently perform quantum-accelerated local improvements.
		All parameters are configured via ``set_param()`` before calling.

		Key parameters: ``distance``, ``num_workers``, ``callback``.
		"""
		# Read all params from _params (with defaults from _PARAM_DEFS)
		distance = self._get_effective('distance')
		callback = self._get_effective('callback')
		num_workers = self._get_effective('num_workers')

		# bd 3c4: each worker needs its OWN fresh initial state. quantum_local_search
		# mutates cur_sol (== the passed state) IN PLACE, so a single shared object
		# would be corrupted/raced across workers. The former code passed
		# self.initial_state, which is None in the normal flow -> the public method
		# raised TypeError and never ran. Build the per-worker start from the model's
		# C initial state (all-zeros by default), seeded all the same so divergence
		# comes only from the decorrelated per-worker PRNG stream.
		if not self.initialized:
			self.manual_initial(0, [0] * self.n)
		init_bits = [sw_tstbit(self.mod.initial_state[0].vector, _i) for _i in range(self.n)]

		# Pass each worker its 0-based index (and the model seed) so
		# run_quantum_local_search seeds a decorrelated per-worker PRNG stream,
		# mirroring 8an.1.3's run_sampling fan-out. The former `for _` gave every
		# worker the same (unseeded) stream -> portfolio collapse under a fixed seed.
		Parallel(n_jobs=num_workers, backend="threading")(
			delayed(run_quantum_local_search)(
				state_py(0, list(init_bits)),
				self.constraint,
				self.objective,
				distance,
				callback,
				self._seed,
				worker_id
			) for worker_id in range(num_workers)
		)

	def approximate_benchmarking(self, samples = 1024, M = 100):
		"""Benchmark the solver using approximate quantum state simulation.

		Repeatedly generates approximate quantum states, runs the
		quantum search, and records iteration counts and objective
		improvements until no further improvement is found.

		Parameters
		----------
		samples : int, optional
			Number of samples per approximate state. Default: 1024.
		M : int, optional
			Maximum Grover iterations per quantum search call.
			Default: 100.

		Returns
		-------
		tuple
			``(total_iterations, deltas, incumbents)`` where
			*total_iterations* is the cumulative oracle call count,
			*deltas* is a list of search deltas per round, and
			*incumbents* is a list of ``(objective, iterations)`` tuples
			tracking improvement over time.
		"""
		deltas = []
		incumbents = []

		total_iterations = 0
		srand(int(time()))
		threshold = copy(self.initial_state)

		while True:
			state = approximate_state(self.n, self.n / 4)
			state.opt_sampler(self.objective, self.constraint, threshold, samples)

			r, it, rounds = state.QSearch(M)
			total_iterations += 2 * it + 1
			deltas.append(state.delta)
			del state
			if r is None:
				break
			else:
				del threshold
				threshold = r
				incumbents.append((-threshold.objective_value, total_iterations))
			# del threshold
		del threshold
		return total_iterations, deltas, incumbents

	def exact_benchmark(self, M):
		"""Benchmark the solver using exact quantum state simulation.

		Uses an exact state generator (with a Gurobi model) to run the
		quantum maximum search with precise state probabilities.

		Parameters
		----------
		M : int
			Maximum Grover iterations per quantum search call.

		Returns
		-------
		list
			Incumbent solution history from the quantum max search.
		"""
		self._params.setdefault('branching_bias', self.n / 4)
		if self.stgen is None:
			self.stgen = exact_simulator(self)
			self.stgen.generate_gurobi_model()

		inc = self.stgen.QMaxSearch(M)
		return inc

	def _callback_value(self):
		"""Current GLOBAL incumbent value for the history callback.

		In SATISFY mode, returns constraints satisfied count.
		In OPTIMIZE mode, returns objective value scaled by sense.

		bd 4uf: reads the SHARED ``mod->global_opt`` — only safe on
		single-trajectory paths with no concurrent writer (local_search,
		quantum_local_search; the ``raw=None`` fallback). The multi-worker ctg
		path must use :meth:`_value_from_raw` on the per-worker
		``ctx->callback_value`` instead.

		Returns
		-------
		int
			Current incumbent value.
		"""
		if self.mod[0].solver == SATISFY:
			return self.mod[0].con[0].num_constraints + self.mod[0].global_opt[0].tot_profit
		return self.mod[0].global_opt[0].tot_profit * self.sense

	def _value_from_raw(self, raw):
		"""Apply the sign/sat convention to a PER-WORKER internal incumbent value.

		``raw`` is a worker's ``cur_sol->tot_profit`` delivered via
		``ctx->callback_value`` (bd 4uf / NORTHSTAR §11 per-worker incumbent
		logging) — the exact transformation `_callback_value` applies to the
		global incumbent and the per-worker final incumbent uses at return
		(SearchLib.pyx), so history values and ``final_incumbents`` stay
		mutually consistent. Reads no shared state.

		Returns
		-------
		int
			The worker incumbent in reporting convention (satisfied count for
			SATISFY, sense-applied objective otherwise).
		"""
		if self.mod[0].solver == SATISFY:
			return self.mod[0].con[0].num_constraints + raw
		return raw * self.sense

	@property
	def objective_value(self):
		"""Best objective value found by the solver.

		Returns
		-------
		int or None
			The objective value of the best solution, accounting for
			the optimization sense (MAXIMIZE/MINIMIZE). Returns None
			in SATISFY mode where there is no objective.
		"""
		if self.mod[0].solver == SATISFY:
			return None
		return self.mod[0].global_opt[0].tot_profit * self.sense

	@property
	def oracle_calls(self):
		"""Per-worker oracle budget spent in the last solve (best-of-portfolio).

		Each portfolio worker accumulates its own race-free oracle count and is
		capped at T(n); the reported figure is the max over workers (~T(n)), per
		the NORTHSTAR §6/§11 portfolio-cost convention. Replaces the former racy
		shared counter.

		Returns
		-------
		int
			Per-worker cumulative oracle call count (best-of-portfolio).
		"""
		return self.mod[0].qtg_applications

	@property
	def runtime(self):
		"""Wall-clock time of the last solve in seconds.

		Returns
		-------
		float
			Elapsed time in seconds.
		"""
		return self.mod[0].runtime

	@property
	def solution(self):
		"""Best solution found by the solver.

		.. note::
			This legacy property returns 0. Use the ``solution`` field
			of the ``OptimizeResult`` returned by ``solve()`` or
			``local_search()`` instead.

		Returns
		-------
		int
			Always returns 0 (deprecated).
		"""
		return 0

	# ============================================================
	# Thread Isolation Properties (Phase 4)
	# ============================================================

	@property
	def seed(self):
		"""Random seed for reproducibility.

		Set before calling ``solve()``. If ``None`` (the default), a
		random seed is generated automatically. After solving, inspect
		``seed_used`` to retrieve the actual seed for reproducibility.

		Returns
		-------
		int or None
			The configured seed, or None for auto-generation.

		Raises
		------
		TypeError
			If set to a non-integer, non-None value.
		"""
		return self._seed

	@seed.setter
	def seed(self, value):
		if value is not None and not isinstance(value, int):
			raise TypeError("seed must be an integer or None")
		self._seed = value

	@property
	def seed_used(self):
		"""Actual random seed used in the most recent solve call.

		Useful for reproducing results when no explicit seed was set:
		save ``seed_used`` after a run, then set ``seed = seed_used``
		before re-running.

		Returns
		-------
		int or None
			The seed that was used, or None if ``solve()`` has not
			been called.
		"""
		return self._seed_used

	@property
	def num_threads(self):
		"""Number of threads for parallel solving.

		Set before calling ``solve()``. If ``None`` (the default),
		auto-detects the number of CPU cores. Can also be configured
		via the ``CBQS_THREADS`` environment variable.

		Returns
		-------
		int or None
			The configured thread count, or None for auto-detection.

		Raises
		------
		ValueError
			If set to a non-positive integer.
		"""
		return self._num_threads

	@num_threads.setter
	def num_threads(self, value):
		if value is not None:
			if not isinstance(value, int) or value < 1:
				raise ValueError("num_threads must be a positive integer or None")
		self._num_threads = value

	# ============================================================
	# Post-Solve Verification (Phase 7)
	# ============================================================

	def verify_solution(self):
		"""Verify that the current solution satisfies all constraints
		and that the reported objective value matches recomputation.

		Checks constraint feasibility via the C evaluation engine and
		independently recomputes the objective value. Emits
		``UserWarning`` for each detected violation but does not raise
		exceptions.

		Returns
		-------
		bool
			True if the solution passes all checks, False otherwise.
			Also sets the internal ``_verified`` flag.
		"""
		if self.mod[0].global_opt is NULL:
			warnings.warn(
				"No solution to verify: solve() has not been called",
				UserWarning, stacklevel=2
			)
			self._verified = False
			return False

		verified = True

		# Reconstruct a state_py from the C-level global_opt for evaluation
		cdef int n_bits = self.mod[0].global_opt[0].vector.bits
		arr = [sw_tstbit(self.mod[0].global_opt[0].vector, i) for i in range(n_bits)]
		cdef long long obj_val = self.mod[0].global_opt[0].tot_profit
		st = state_py(obj_val, arr)

		# Check constraint satisfaction using existing C evaluation
		constraints_ok = self.constraint.eval_con(st)
		if not constraints_ok:
			warnings.warn(
				"Post-solve verification FAILED: solution violates one or more constraints",
				UserWarning, stacklevel=2
			)
			verified = False

		# Recompute objective value and compare with reported value
		# Skip in SATISFY mode (no objective to verify)
		if self.mod[0].solver != SATISFY:
			recomputed_obj = self.objective.eval_obj(st) * self.sense
			reported_obj = self.objective_value
			EPSILON = 1e-9
			if abs(recomputed_obj - reported_obj) > EPSILON:
				warnings.warn(
					f"Post-solve verification FAILED: reported objective {reported_obj} "
					f"does not match recomputed {recomputed_obj}",
					UserWarning, stacklevel=2
				)
				verified = False

		self._verified = verified
		return verified