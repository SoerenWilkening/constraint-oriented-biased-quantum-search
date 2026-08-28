"""Phase-specific parameter definitions, resolution, and serialization.

Three solver phases (SAT, OPT_SAT, OPT) each have their own set of
branching parameters. Parameters are resolved with fallback:
    phase-specific > unprefixed > built-in default

Example:
    If sat_branching_bias=3 and branching_bias=5, the SAT phase uses 3.
    If only branching_bias=5 is set, all phases use 5.
    If nothing is set, the built-in default is used.
"""

import math

import numpy as np


PHASES = ('sat', 'opt_sat', 'opt')

PHASE_PARAM_SUFFIXES = (
    'branching_weights',
    'branching_factor',
    'bias_factor',
    'branching_bias',
    'branching_radius',
    'variable_priorities',
    # bd a0w (M5): angle-precision lever (Ross-Selinger / gridsynth).
    'angle_precision_eps',
    'angle_precision_dither',
)

# Built-in defaults for each suffix (unprefixed fallback values).
DEFAULTS = {
    'branching_weights': None,
    'branching_factor': 1.0,
    'bias_factor': 1.0,
    'branching_bias': 5.0,
    'branching_radius': None,
    'variable_priorities': None,
    'angle_precision_eps': None,      # None/<=0 == exact angles == lever OFF
    'angle_precision_dither': False,  # False == systematic grid rounding
}

def strict_bool(value):
    """Strict bool coercion for flag params (CLAUDE.md §2.1 fail loud).

    Plain ``bool`` maps every non-empty string to True, so
    ``set_param('angle_precision_dither', 'false')`` would silently ARM the
    flag -- here that switches which PHYSICAL synthesis model an arm runs, which
    would corrupt a whole sweep with no error. Accept only real booleans and the
    integers 0/1 (numpy bools/ints included); reject everything else loudly.

    Args:
        value: the user-supplied value.

    Returns:
        bool.

    Raises:
        ValueError: for anything that is not a bool or 0/1.
    """
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        if value in (0, 1):
            return bool(value)
        raise ValueError(f"expected a boolean (True/False or 0/1), got {value!r}")
    raise ValueError(
        f"expected a boolean (True/False or 0/1), got {value!r} of type "
        f"{type(value).__name__} -- strings are NOT accepted ('false' is truthy)")


# Per-suffix coercion for the generated phase params. Everything not listed
# coerces to float (the historical behaviour); ``None`` means "no coercion"
# and is used for the array-valued suffixes, which validate separately.
COERCERS = {
    'branching_weights': None,
    'variable_priorities': None,
    'angle_precision_dither': strict_bool,
}


def radius_to_bias(n, r):
    """Convert a target neighborhood radius ``r`` to a scalar ``bias`` (M0f).

    The expected number of flips from the incumbent is ``n / (bias + 2)``, so
    setting ``bias = n/r - 2`` makes the realized Hamming radius exactly ``r`` at
    *every* ``n`` -- the scale-invariant lever of NORTHSTAR §4/§1.5 (``bias = n/d``
    alone is only ~``d`` flips for ``n >> d`` and is compressed at small ``n``).

    Args:
        n: number of variables (> 0).
        r: target radius (> 0; should be < n so the resulting bias stays > -1).

    Returns:
        float bias = n/r - 2.

    Raises:
        ValueError: if ``r <= 0`` or ``n <= 0``.
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    if r <= 0:
        raise ValueError(f"branching_radius must be > 0, got {r}")
    return n / float(r) - 2.0

# Validation rules per suffix.
# Each entry is (validator_fn, error_message).
# validator_fn returns True if valid, False otherwise.
# None means no validation beyond type.
_VALIDATORS = {
    'branching_bias': (
        lambda v: v > -1,
        'branching_bias must be > -1',
    ),
    'branching_radius': (
        lambda v: v > 0,
        'branching_radius must be > 0',
    ),
    'angle_precision_eps': (
        lambda v: v > 0,
        'angle_precision_eps must be > 0',
    ),
    'branching_factor': (
        lambda v: v >= 0,
        'branching_factor must be non-negative',
    ),
    'bias_factor': (
        lambda v: v >= 0,
        'bias_factor must be non-negative',
    ),
    'branching_weights': None,  # validated separately via validate_weights
    'variable_priorities': None,  # validated separately via validate_priorities
}


def validate_weights(value, n_vars):
    """Validate branching_weights array.

    Args:
        value: weights array or None.
        n_vars: expected number of variables.

    Raises:
        ValueError: if weights are invalid.
    """
    if value is None:
        return
    arr = np.asarray(value, dtype=np.float64)
    if arr.ndim != 1 or len(arr) != n_vars:
        raise ValueError(
            f"branching_weights must have length {n_vars}, got {len(arr)}"
        )
    # M0f: weights are SIGNED per-variable logit offsets (theta_i) -- no
    # non-negativity (the L1 normalization that motivated it was dropped too).
    if not np.all(np.isfinite(arr)):
        raise ValueError("branching_weights must not contain NaN or Inf")


def validate_priorities(value, n_vars):
    """Validate variable_priorities array.

    Args:
        value: priorities array or None.
        n_vars: expected number of variables.

    Raises:
        ValueError: if priorities are invalid.
    """
    if value is None:
        return
    arr = np.asarray(value, dtype=np.float64)
    if arr.ndim != 1 or len(arr) != n_vars:
        raise ValueError(
            f"variable_priorities must have length {n_vars}, got {len(arr)}"
        )


def make_phase_param_defs():
    """Generate parameter definition entries for all 24 phase-specific params.

    Returns:
        dict: mapping 'phase_suffix' -> {'default': ..., 'coerce': ..., 'validate': ...}
            suitable for inclusion in _PARAM_DEFS.
    """
    defs = {}
    for phase in PHASES:
        for suffix in PHASE_PARAM_SUFFIXES:
            key = f"{phase}_{suffix}"
            default = DEFAULTS[suffix]

            if suffix in ('branching_weights', 'variable_priorities'):
                coerce = None
                validate = 'special'
            else:
                coerce = COERCERS.get(suffix, float)
                validate = None

            description = (
                f"Phase-specific {suffix} for {phase} phase. "
                f"See '{suffix}' for details."
            )

            defs[key] = {
                'default': default,
                'coerce': coerce,
                'validate': validate,
                'description': description,
            }
    return defs


class PhaseParamResolver:
    """Resolves phase-specific parameters with fallback to unprefixed defaults.

    Resolution order for resolve(phase, suffix):
        1. param_store['{phase}_{suffix}']   (phase-specific override)
        2. param_store['{suffix}']            (unprefixed fallback)
        3. defaults['{suffix}']               (built-in default)

    Args:
        param_store: dict of user-set parameters (both prefixed and unprefixed).
        defaults: dict of built-in defaults keyed by suffix.
    """

    def __init__(self, param_store, defaults):
        self._store = param_store
        self._defaults = defaults

    def resolve(self, phase, param_suffix):
        """Resolve a single parameter for a given phase.

        Args:
            phase: one of 'sat', 'opt_sat', 'opt'.
            param_suffix: one of PHASE_PARAM_SUFFIXES.

        Returns:
            The resolved parameter value.

        Raises:
            ValueError: if phase or param_suffix is unknown, or if
                the resolved value fails validation.
        """
        if phase not in PHASES:
            raise ValueError(f"Unknown phase: '{phase}'")
        if param_suffix not in PHASE_PARAM_SUFFIXES:
            raise ValueError(f"Unknown param suffix: '{param_suffix}'")

        phase_key = f"{phase}_{param_suffix}"

        # Resolution order: phase-specific > unprefixed > default
        if phase_key in self._store:
            value = self._store[phase_key]
        elif param_suffix in self._store:
            value = self._store[param_suffix]
        else:
            value = self._defaults.get(param_suffix)

        # Validate scalar params
        if value is not None:
            validator_entry = _VALIDATORS.get(param_suffix)
            if validator_entry is not None:
                check_fn, err_msg = validator_entry
                if not check_fn(value):
                    raise ValueError(err_msg)

        return value

    def resolve_all(self):
        """Resolve all parameters for all phases.

        Returns:
            dict: {phase: {suffix: value}} for all phases and suffixes.
        """
        result = {}
        for phase in PHASES:
            phase_dict = {}
            for suffix in PHASE_PARAM_SUFFIXES:
                phase_dict[suffix] = self.resolve(phase, suffix)
            result[phase] = phase_dict
        return result

    def to_ctx_kwargs(self):
        """Flatten resolved params to kwargs for C solver context setters.

        Returns:
            dict: {'sat_branching_bias': 5.0, 'opt_branching_factor': 1.0, ...}
                with exactly 24 keys (3 phases x 8 suffixes).
        """
        resolved = self.resolve_all()
        flat = {}
        for phase in PHASES:
            for suffix in PHASE_PARAM_SUFFIXES:
                flat[f"{phase}_{suffix}"] = resolved[phase][suffix]
        return flat


# --------------------------------------------------------------------------- #
# bd a0w (M5): angle-precision REPORTING helpers.
#
# The lever's input is always the gridsynth accuracy ``eps`` (radians) -- the
# quantity Ross-Selinger actually takes. Bits and T-counts are derived for
# READING the results and are never an input to the solver.
# --------------------------------------------------------------------------- #

def angle_precision_bits(eps):
    """Equivalent uniform-grid bits for a synthesis accuracy ``eps`` (radians).

    A ``b``-bit uniform grid over the R_y angle range ``[0, pi]`` has spacing
    ``pi/2**b`` and hence max rounding error ``pi/2**(b+1)``; matching that to
    ``eps`` gives ``b = log2(pi / (2*eps))``.

    Args:
        eps: absolute angle accuracy in radians (> 0).

    Returns:
        float equivalent bits (may be fractional; ``eps`` is continuous).

    Raises:
        ValueError: if ``eps <= 0``.
    """
    if eps is None or eps <= 0:
        raise ValueError(f"angle_precision_eps must be > 0 to report bits, got {eps}")
    return math.log2(math.pi / (2.0 * eps))


def t_count_per_rotation(eps):
    """Ross-Selinger T-count to synthesize one R_y to accuracy ``eps``.

    The Ross-Selinger / gridsynth cost is ``~3*log2(1/eps)`` T-gates per
    rotation (the leading term; the additive constant is implementation
    dependent and deliberately not modelled here).

    Args:
        eps: absolute angle accuracy in radians (0 < eps < 1).

    Returns:
        float T-gates per rotation.

    Raises:
        ValueError: if ``eps <= 0``.
    """
    if eps is None or eps <= 0:
        raise ValueError(f"angle_precision_eps must be > 0 to report a T-count, got {eps}")
    return 3.0 * math.log2(1.0 / eps)


def t_count_per_qtg_application(eps, n):
    """Ross-Selinger T-count for one QTG state preparation over ``n`` variables.

    One R_y per variable, so ``n * t_count_per_rotation(eps)``. This is the
    INSIDE-the-oracle cost axis (bd a0w) -- it is reported ALONGSIDE the oracle
    count and never folded into the equal-``T(n)`` oracle pricing (NORTHSTAR
    §1.1/§5).
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    return n * t_count_per_rotation(eps)
