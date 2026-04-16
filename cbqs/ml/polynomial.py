"""Polynomial expansion and predictor for ES-trained CBQS parameter prediction.

Provides degree-2 polynomial feature expansion, coefficient vector pack/unpack
utilities, and a lightweight PolynomialPredictor class that maps Model objects
to solver parameters (branching weights, priorities, bias, factors).

The model learns small perturbations around the known-good default bias of n/4,
with bias delta bounded to +/-3% of n/4. Per-variable weights act as direct
perturbations. Factors are clipped to non-negative values.

The instance-level model uses a sub-linear form (intercept + linear terms only,
no cross or squared terms) for 12 terms total.

Total learnable parameters: 146 (110 per-variable + 36 instance-level).
"""
import numpy as np

# --- Dimensions ---
N_VAR_FEATURES = 9
N_INST_FEATURES = 11
N_VAR_TERMS = 55    # 1 + 9 + 36 + 9
N_INST_TERMS = 12   # 1 + 11  (sub-linear: intercept + linear only)
N_VAR_OUTPUTS = 2   # weight, priority
N_INST_OUTPUTS = 3  # bias_delta, branching_factor, bias_factor
THETA_SIZE = N_VAR_OUTPUTS * N_VAR_TERMS + N_INST_OUTPUTS * N_INST_TERMS  # 146

# Legacy constant for backward compatibility with old checkpoints.
_LEGACY_INST_TERMS = 78   # 1 + 11 + 55 + 11  (degree-2 full polynomial)
_LEGACY_THETA_SIZE = N_VAR_OUTPUTS * N_VAR_TERMS + N_INST_OUTPUTS * _LEGACY_INST_TERMS  # 344

# Default clipping bound for bias delta as fraction of n/4.
DEFAULT_DELTA_PCT = 0.03


def default_theta():
    """Return a theta vector whose predictions match the solver defaults.

    Defaults: bias_delta=0, branching_factor=0, bias_factor=1.
    All per-variable weights and priorities start at zero.
    """
    theta = np.zeros(THETA_SIZE, dtype=np.float64)
    # W_inst layout: row 0 = bias_delta, row 1 = branching_factor, row 2 = bias_factor
    # Column 0 of each row is the intercept term.
    bias_factor_intercept = N_VAR_OUTPUTS * N_VAR_TERMS + 2 * N_INST_TERMS  # 110 + 24 = 134
    theta[bias_factor_intercept] = 1.0
    return theta


def poly_expand(X, degree=2):
    """Expand features into degree-2 polynomial terms.

    Produces terms: [1, x1, ..., xn, x1*x2, ..., x(n-1)*xn, x1^2, ..., xn^2].

    Parameters
    ----------
    X : numpy.ndarray
        Feature array of shape (n_samples, n_features) or (n_features,) for a
        single sample.
    degree : int
        Polynomial degree (only degree=2 is supported).

    Returns
    -------
    numpy.ndarray
        Expanded feature array. Shape (n_samples, n_terms) for 2D input,
        or (n_terms,) for 1D input.

    Raises
    ------
    ValueError
        If degree != 2.
    """
    if degree != 2:
        raise ValueError(f"Only degree=2 is supported, got {degree}")

    is_1d = X.ndim == 1
    if is_1d:
        X = X.reshape(1, -1)

    n_samples, n_features = X.shape
    n_cross = n_features * (n_features - 1) // 2
    n_terms = 1 + n_features + n_cross + n_features

    result = np.empty((n_samples, n_terms), dtype=np.float64)

    # Intercept
    result[:, 0] = 1.0

    # Linear terms
    col = 1
    result[:, col:col + n_features] = X
    col += n_features

    # Cross-terms (i < j)
    for i in range(n_features):
        for j in range(i + 1, n_features):
            result[:, col] = X[:, i] * X[:, j]
            col += 1

    # Squared terms
    result[:, col:col + n_features] = X ** 2

    if is_1d:
        return result[0]
    return result


def linear_expand(X):
    """Expand features into intercept + linear terms only (sub-linear model).

    Produces terms: [1, x1, ..., xn].

    Parameters
    ----------
    X : numpy.ndarray
        Feature array of shape (n_samples, n_features) or (n_features,) for a
        single sample.

    Returns
    -------
    numpy.ndarray
        Expanded feature array. Shape (n_samples, 1 + n_features) for 2D input,
        or (1 + n_features,) for 1D input.
    """
    is_1d = X.ndim == 1
    if is_1d:
        X = X.reshape(1, -1)

    n_samples, n_features = X.shape
    result = np.empty((n_samples, 1 + n_features), dtype=np.float64)
    result[:, 0] = 1.0
    result[:, 1:] = X

    if is_1d:
        return result[0]
    return result


def migrate_theta_v1_to_v2(theta_v1):
    """Migrate a legacy 344-element theta to the new 146-element layout.

    The legacy layout used degree-2 polynomial (78 terms) for instance-level
    predictions. The new layout uses sub-linear (12 terms: intercept + linear).
    Migration extracts only the intercept and linear coefficients from each
    instance output row, discarding cross and squared terms.

    Parameters
    ----------
    theta_v1 : numpy.ndarray
        Legacy coefficient vector of shape (344,).

    Returns
    -------
    numpy.ndarray
        New coefficient vector of shape (146,).
    """
    if theta_v1.shape != (_LEGACY_THETA_SIZE,):
        raise ValueError(
            f"Expected legacy theta of shape ({_LEGACY_THETA_SIZE},), "
            f"got {theta_v1.shape}"
        )
    split = N_VAR_OUTPUTS * N_VAR_TERMS  # 110
    W_var_flat = theta_v1[:split]

    # Legacy W_inst is (3, 78). Extract columns [0, 1..12) = intercept + linear.
    W_inst_old = theta_v1[split:].reshape(N_INST_OUTPUTS, _LEGACY_INST_TERMS)
    W_inst_new = W_inst_old[:, :N_INST_TERMS]  # (3, 12)

    return np.concatenate([W_var_flat, W_inst_new.ravel()])


def pack_theta(W_var, W_inst):
    """Pack weight matrices into a flat coefficient vector.

    Parameters
    ----------
    W_var : numpy.ndarray
        Per-variable coefficient matrix, shape (N_VAR_OUTPUTS, N_VAR_TERMS).
    W_inst : numpy.ndarray
        Instance-level coefficient matrix, shape (N_INST_OUTPUTS, N_INST_TERMS).

    Returns
    -------
    numpy.ndarray
        Flat coefficient vector of shape (THETA_SIZE,).

    Raises
    ------
    ValueError
        If input shapes are incorrect.
    """
    if W_var.shape != (N_VAR_OUTPUTS, N_VAR_TERMS):
        raise ValueError(
            f"W_var shape must be ({N_VAR_OUTPUTS}, {N_VAR_TERMS}), "
            f"got {W_var.shape}"
        )
    if W_inst.shape != (N_INST_OUTPUTS, N_INST_TERMS):
        raise ValueError(
            f"W_inst shape must be ({N_INST_OUTPUTS}, {N_INST_TERMS}), "
            f"got {W_inst.shape}"
        )
    return np.concatenate([W_var.ravel(), W_inst.ravel()])


def unpack_theta(theta):
    """Unpack a flat coefficient vector into weight matrices.

    Parameters
    ----------
    theta : numpy.ndarray
        Flat coefficient vector of shape (THETA_SIZE,).

    Returns
    -------
    tuple of numpy.ndarray
        (W_var, W_inst) where W_var has shape (N_VAR_OUTPUTS, N_VAR_TERMS)
        and W_inst has shape (N_INST_OUTPUTS, N_INST_TERMS).

    Raises
    ------
    ValueError
        If theta has wrong length.
    """
    if theta.shape != (THETA_SIZE,):
        raise ValueError(
            f"theta must have shape ({THETA_SIZE},), got {theta.shape}"
        )
    split = N_VAR_OUTPUTS * N_VAR_TERMS
    W_var = theta[:split].reshape(N_VAR_OUTPUTS, N_VAR_TERMS)
    W_inst = theta[split:].reshape(N_INST_OUTPUTS, N_INST_TERMS)
    return W_var, W_inst


class PolynomialPredictor:
    """Lightweight predictor using degree-2 polynomial parameter functions.

    Maps a closed Model object to solver parameters using polynomial evaluation
    of extracted features. Bias is computed as n/4 + clipped delta; factors are
    clipped to non-negative values.

    Parameters
    ----------
    theta : numpy.ndarray
        Flat coefficient vector of shape (THETA_SIZE,).
    delta_pct : float
        Maximum bias delta as fraction of n/4 (default 0.03 = 3%).

    Examples
    --------
    >>> theta = np.zeros(THETA_SIZE)
    >>> predictor = PolynomialPredictor(theta)
    >>> params = predictor.predict(model)
    >>> params['branching_bias']  # n/4 for zero theta
    """

    def __init__(self, theta, delta_pct=DEFAULT_DELTA_PCT):
        self.W_var, self.W_inst = unpack_theta(np.asarray(theta, dtype=np.float64))
        self.delta_pct = delta_pct

    def predict(self, model):
        """Predict solver parameters from a closed Model.

        Parameters
        ----------
        model : Model
            A closed CBQS Model instance.

        Returns
        -------
        dict
            Parameter dict with keys: branching_weights, variable_priorities,
            branching_bias, branching_factor, bias_factor.
        """
        # Fused C pipeline: features → poly → matmul → params in one call.
        # Falls back to Python path for non-Model objects (e.g. tests).
        try:
            from cbqs.SearchLib import c_predict_params
            return c_predict_params(model, self.W_var, self.W_inst, self.delta_pct)
        except TypeError:
            pass

        # Python fallback
        from cbqs.ml.features import FeatureExtractor
        _fe = FeatureExtractor()
        var_features = _fe.extract_variable_features(model)
        inst_features = _fe.extract_instance_features(model)

        # Per-variable predictions
        var_terms = poly_expand(var_features, degree=2)
        var_out = var_terms @ self.W_var.T  # (n_vars, 2)
        weights = var_out[:, 0]
        priority_scores = var_out[:, 1]
        priorities = np.argsort(-priority_scores)

        # Instance-level predictions (sub-linear: intercept + linear only)
        inst_terms = linear_expand(inst_features)
        inst_out = self.W_inst @ inst_terms  # (3,)

        # Post-process
        n = len(model.variables)
        base_bias = n / 4.0
        bound = self.delta_pct * base_bias
        bias_delta = np.clip(inst_out[0], -bound, bound)
        bias = base_bias + bias_delta
        branching_factor = max(0.0, float(inst_out[1]))
        bias_factor = max(0.0, float(inst_out[2]))

        return {
            'branching_weights': np.maximum(0.0, weights),
            'variable_priorities': priorities,
            'branching_bias': float(bias),
            'branching_factor': branching_factor,
            'bias_factor': bias_factor,
        }

    def save(self, path):
        """Save predictor to a .npz file.

        Parameters
        ----------
        path : str
            File path (typically ending in .npz).
        """
        theta = pack_theta(self.W_var, self.W_inst)
        np.savez(path, theta=theta, delta_pct=np.array(self.delta_pct))

    @classmethod
    def load(cls, path):
        """Load a predictor from a .npz file.

        Supports both current (146-element) and legacy (344-element) theta
        vectors. Legacy checkpoints are automatically migrated by extracting
        intercept and linear coefficients from the old degree-2 instance model.

        Parameters
        ----------
        path : str
            File path to load from.

        Returns
        -------
        PolynomialPredictor
            A predictor instance with the saved coefficients.
        """
        data = np.load(path)
        theta = data['theta']
        delta_pct = float(data['delta_pct']) if 'delta_pct' in data else DEFAULT_DELTA_PCT
        if theta.shape == (_LEGACY_THETA_SIZE,):
            theta = migrate_theta_v1_to_v2(theta)
        return cls(theta, delta_pct=delta_pct)
