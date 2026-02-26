"""Feature extraction from CBQS Model objects for ML-based branching weight prediction.

Provides the FeatureExtractor class which extracts per-variable and instance-level
structural features from closed Model objects. Features follow standard MIP feature
sets from solver ML literature (Khalil et al.).
"""
import numpy as np

from cbqs.Constants import INTEGER

# Per-variable features: 9 features per variable in fixed order.
VARIABLE_FEATURE_NAMES = [
    "degree",                    # Number of constraints this variable appears in
    "coeff_mean",                # Mean absolute coefficient across constraints
    "coeff_max",                 # Max absolute coefficient
    "coeff_min",                 # Min absolute coefficient (or 0 if not in any constraint)
    "objective_coefficient",     # Coefficient in objective function (0 if absent)
    "bounds_width",              # ub - lb (1 for binary)
    "is_integer",                # 1.0 if integer type, 0.0 otherwise
    "avg_neighbor_degree",       # Average degree of co-occurring variables
    "num_co_occurring_vars",     # Number of unique variables sharing a constraint
]

# Instance-level features: 11 features in fixed order.
INSTANCE_FEATURE_NAMES = [
    "n_variables",               # Total number of variables
    "n_constraints",             # Total number of constraints
    "constraint_density",        # n_constraints / n_variables (0 if no variables)
    "constraint_variable_ratio", # Same as constraint_density
    "objective_density",         # Fraction of variables with nonzero objective coefficient
    "integer_variable_fraction", # Fraction of variables that are integer type
    "coeff_mean",                # Global mean of absolute constraint coefficients
    "coeff_std",                 # Global std of absolute constraint coefficients
    "coeff_max",                 # Global max absolute constraint coefficient
    "bounds_tightness_mean",     # Mean of (ub - lb) across all variables
    "bounds_tightness_std",      # Std of (ub - lb) across all variables
]


def _parse_expression_terms(expr):
    """Extract (coefficient, variable_indices) pairs from an Expression.

    Iterates over the Expression's term list. Terms are lists where the first
    element is the coefficient and remaining elements are variable indices.
    Sense and rhs values (appended as ints for constraint expressions) are
    filtered out.

    Parameters
    ----------
    expr : Expression
        A CBQS Expression object (from obj_expr or con_expr).

    Returns
    -------
    list of (int, tuple of int)
        Each entry is (coefficient, (var_idx1, var_idx2, ...)).
    """
    result = []
    for item in expr:
        if isinstance(item, list) and len(item) >= 2:
            coeff = item[0]
            var_indices = tuple(item[1:])
            result.append((coeff, var_indices))
    return result


class FeatureExtractor:
    """Extract structural features from CBQS Model objects.

    Extracts per-variable feature matrices and instance-level feature vectors
    from closed Model objects. Features capture constraint structure, variable
    properties, and local graph topology for downstream ML-based branching
    weight prediction.

    The feature set is fixed (9 per-variable features, 11 instance features)
    and follows standard MIP feature conventions from solver ML literature.

    Examples
    --------
    >>> from cbqs.Model import Model
    >>> from cbqs.ml.features import FeatureExtractor
    >>> m = Model()
    >>> xs = m.add_variables(5)
    >>> m.add_constraint(xs[0] + xs[1] <= 1)
    >>> m.set_objective(xs[0] + xs[1] + xs[2])
    >>> m.close()
    >>> fe = FeatureExtractor()
    >>> var_features = fe.extract_variable_features(m)  # shape: (5, 9)
    >>> inst_features = fe.extract_instance_features(m)  # shape: (11,)
    """

    @property
    def feature_names(self):
        """List of per-variable feature names in column order.

        Returns
        -------
        list of str
            9 feature name strings.
        """
        return list(VARIABLE_FEATURE_NAMES)

    @property
    def instance_feature_names(self):
        """List of instance-level feature names in column order.

        Returns
        -------
        list of str
            11 feature name strings.
        """
        return list(INSTANCE_FEATURE_NAMES)

    def extract_variable_features(self, model):
        """Extract per-variable feature matrix from a closed Model.

        Returns a normalized feature matrix where each row corresponds to a
        variable (in sorted index order) and each column to a feature. Features
        are z-score normalized per column; zero-variance columns are set to zero.

        Parameters
        ----------
        model : Model
            A closed CBQS Model instance (constraints_compiled must be True).

        Returns
        -------
        numpy.ndarray
            Feature matrix of shape (n_vars, 9) with dtype float64.

        Raises
        ------
        ValueError
            If the model has not been closed.
        """
        if not model.constraints_compiled:
            raise ValueError("Model must be closed before feature extraction")

        var_indices = sorted(model.variables.keys())
        n = len(var_indices)

        if n == 0:
            return np.zeros((0, 9), dtype=np.float64)

        idx_to_row = {idx: row for row, idx in enumerate(var_indices)}
        features = np.zeros((n, 9), dtype=np.float64)

        # Per-variable accumulators
        var_coefficients = [[] for _ in range(n)]
        var_co_occurring = [set() for _ in range(n)]

        # --- Objective coefficients (column 4) ---
        for expr in model.obj_expr:
            terms = _parse_expression_terms(expr)
            for coeff, var_idx_tuple in terms:
                for var_idx in var_idx_tuple:
                    if var_idx in idx_to_row:
                        row = idx_to_row[var_idx]
                        features[row, 4] += abs(coeff)

        # --- Constraint participation ---
        for expr in model.con_expr:
            terms = _parse_expression_terms(expr)

            # Collect all variable indices appearing in this constraint
            vars_in_constraint = set()
            for coeff, var_idx_tuple in terms:
                for var_idx in var_idx_tuple:
                    if var_idx in idx_to_row:
                        vars_in_constraint.add(var_idx)
                        row = idx_to_row[var_idx]
                        # Increment degree (column 0)
                        features[row, 0] += 1
                        # Collect coefficient for statistics
                        var_coefficients[row].append(abs(coeff))

            # Build co-occurrence sets
            for var_idx in vars_in_constraint:
                row = idx_to_row[var_idx]
                for other_idx in vars_in_constraint:
                    if other_idx != var_idx:
                        var_co_occurring[row].add(other_idx)

        # --- Coefficient statistics (columns 1-3) ---
        for row in range(n):
            coeffs = var_coefficients[row]
            if coeffs:
                features[row, 1] = np.mean(coeffs)   # coeff_mean
                features[row, 2] = np.max(coeffs)     # coeff_max
                features[row, 3] = np.min(coeffs)     # coeff_min

        # --- Variable properties (columns 5-6) ---
        for idx in var_indices:
            row = idx_to_row[idx]
            var = model.variables[idx]
            features[row, 5] = var.ub - var.lb       # bounds_width
            features[row, 6] = 1.0 if var.vtype == INTEGER else 0.0  # is_integer

        # --- Neighbor features (columns 7-8) ---
        for row in range(n):
            co_set = var_co_occurring[row]
            features[row, 8] = len(co_set)            # num_co_occurring_vars
            if co_set:
                neighbor_degrees = [features[idx_to_row[idx], 0] for idx in co_set
                                    if idx in idx_to_row]
                if neighbor_degrees:
                    features[row, 7] = np.mean(neighbor_degrees)  # avg_neighbor_degree

        # --- Per-column z-score normalization ---
        for col in range(9):
            col_data = features[:, col]
            mean = np.mean(col_data)
            std = np.std(col_data)
            if std > 0:
                features[:, col] = (col_data - mean) / std
            else:
                features[:, col] = 0.0

        return features

    def extract_instance_features(self, model):
        """Extract instance-level feature vector from a closed Model.

        Returns a feature vector capturing global model statistics: variable
        and constraint counts, density ratios, coefficient statistics, and
        bounds tightness measures.

        Parameters
        ----------
        model : Model
            A closed CBQS Model instance (constraints_compiled must be True).

        Returns
        -------
        numpy.ndarray
            Feature vector of shape (11,) with dtype float64.

        Raises
        ------
        ValueError
            If the model has not been closed.
        """
        if not model.constraints_compiled:
            raise ValueError("Model must be closed before feature extraction")

        features = np.zeros(11, dtype=np.float64)

        n_vars = len(model.variables)
        n_cons = len(model.con_expr)

        # Column 0: n_variables
        features[0] = n_vars

        # Column 1: n_constraints
        features[1] = n_cons

        # Column 2: constraint_density
        features[2] = n_cons / n_vars if n_vars > 0 else 0.0

        # Column 3: constraint_variable_ratio
        features[3] = n_cons / n_vars if n_vars > 0 else 0.0

        # Column 4: objective_density
        obj_vars = set()
        for expr in model.obj_expr:
            terms = _parse_expression_terms(expr)
            for coeff, var_idx_tuple in terms:
                if coeff != 0:
                    for var_idx in var_idx_tuple:
                        obj_vars.add(var_idx)
        features[4] = len(obj_vars) / n_vars if n_vars > 0 else 0.0

        # Column 5: integer_variable_fraction
        n_integer = sum(1 for v in model.variables.values() if v.vtype == INTEGER)
        features[5] = n_integer / n_vars if n_vars > 0 else 0.0

        # Columns 6-8: global constraint coefficient statistics
        all_coeffs = []
        for expr in model.con_expr:
            terms = _parse_expression_terms(expr)
            for coeff, var_idx_tuple in terms:
                all_coeffs.append(abs(coeff))

        if all_coeffs:
            features[6] = np.mean(all_coeffs)   # coeff_mean
            features[7] = np.std(all_coeffs)     # coeff_std
            features[8] = np.max(all_coeffs)     # coeff_max

        # Columns 9-10: bounds tightness statistics
        if n_vars > 0:
            bounds_widths = [v.ub - v.lb for v in model.variables.values()]
            features[9] = np.mean(bounds_widths)   # bounds_tightness_mean
            features[10] = np.std(bounds_widths)    # bounds_tightness_std

        return features
