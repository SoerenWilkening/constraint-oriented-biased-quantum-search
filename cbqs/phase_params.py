"""Phase-specific parameter definitions, resolution, and serialization.

Three solver phases (SAT, OPT_SAT, OPT) each have their own set of
branching parameters. Parameters are resolved with fallback:
    phase-specific > unprefixed > built-in default

Example:
    If sat_branching_bias=3 and branching_bias=5, the SAT phase uses 3.
    If only branching_bias=5 is set, all phases use 5.
    If nothing is set, the built-in default is used.
"""

import numpy as np


PHASES = ('sat', 'opt_sat', 'opt')

PHASE_PARAM_SUFFIXES = (
    'branching_weights',
    'branching_factor',
    'bias_factor',
    'branching_bias',
    'branching_radius',
    'variable_priorities',
)

# Built-in defaults for each suffix (unprefixed fallback values).
DEFAULTS = {
    'branching_weights': None,
    'branching_factor': 1.0,
    'bias_factor': 1.0,
    'branching_bias': 5.0,
    'branching_radius': None,
    'variable_priorities': None,
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
    """Generate parameter definition entries for all 18 phase-specific params.

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
                coerce = float
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
                with exactly 18 keys (3 phases x 6 suffixes).
        """
        resolved = self.resolve_all()
        flat = {}
        for phase in PHASES:
            for suffix in PHASE_PARAM_SUFFIXES:
                flat[f"{phase}_{suffix}"] = resolved[phase][suffix]
        return flat
