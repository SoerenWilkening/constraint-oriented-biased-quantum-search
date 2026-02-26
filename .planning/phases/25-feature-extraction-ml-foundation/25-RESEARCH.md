# Phase 25: Feature Extraction & ML Foundation - Research

**Researched:** 2026-02-26
**Domain:** ML feature extraction from combinatorial optimization models; optional dependency packaging
**Confidence:** HIGH

## Summary

Phase 25 introduces a pure-Python `cbqs.ml` subpackage that extracts structural features from CBQS Model objects for downstream ML-based branching weight prediction. The implementation requires three distinct capabilities: (1) a FeatureExtractor class producing per-variable feature matrices and instance-level feature vectors, (2) an optional `sklearn` dependency wired through `pip install cbqs[ml]`, and (3) lazy import isolation so `import cbqs` never fails when sklearn is absent.

The codebase is well-structured for this work. Model objects expose all data needed for feature extraction through Python-accessible attributes: `n` (variable count), `variables` (dict of Variable objects with `lb`, `ub`, `vtype`), `obj_expr` (list of Expression objects), `con_expr` (list of Expression objects), `_params` (parameter dict), and `constraints_compiled` (closed flag). Expression objects expose their term structure through the `c_liste()` method and iteration protocol. No Cython helper is needed; direct attribute access is sufficient.

**Primary recommendation:** Build `cbqs/ml/` as a pure-Python subpackage. Use Expression iteration to extract coefficient/variable structure. Wire sklearn via `extras_require` in setup.py. Use lazy import guard in `cbqs/ml/__init__.py`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Per-variable features combine domain info AND constraint participation: variable degree (# constraints), coefficient magnitude stats (mean/max/min), constraint type distribution, bounds width, integrality flag, objective coefficient
- Include basic neighbor/interaction features: average neighbor degree, number of unique co-occurring variables — captures local graph structure without GNN complexity
- Instance-level features go beyond requirements: constraint density, variable count, coefficient statistics PLUS constraint/variable ratio, objective density, integer variable fraction, bounds tightness stats
- Follow standard MIP feature sets from solver ML literature (e.g., Khalil et al. branching features) as reference
- Features are normalized/standardized by default
- FeatureExtractor class (not standalone function, not Model method)
- Separate methods: `extract_variable_features(model)` returns ndarray (n_vars, n_features), `extract_instance_features(model)` returns ndarray (n_features,)
- Returns plain numpy arrays (not result objects)
- Fixed feature set for v3.0 — no configurability for which features to compute
- Subpackage structure: `cbqs.ml.features`, `cbqs.ml.training`, `cbqs.ml.adaptation`
- sklearn availability check lives in `cbqs.ml.__init__` — clear error at import time if sklearn missing
- Create stub modules for future phases (training, adaptation) to establish structure upfront
- `import cbqs` without sklearn must work with zero import errors (INTG-02)
- Raise `ValueError('Model must be closed before feature extraction')` on unclosed models
- Return zeros for constraint-related features when model has no constraints (allows pipeline to continue)
- No size limits or warnings for large models — extract regardless of variable count

### Claude's Discretion
- Feature naming convention (string labels vs positional) — Claude picks what best serves debugging and downstream ML usage
- Normalization scope (per-instance vs fit/transform pattern) — Claude decides what integrates best with sklearn pipelines
- Public API re-export pattern (top-level `from cbqs.ml import FeatureExtractor` vs explicit subpackage imports)
- Type checking approach (isinstance vs duck typing) for Model validation

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FEAT-01 | User can extract per-variable feature matrix (n_vars x n_features) from a closed Model | FeatureExtractor.extract_variable_features() — data access pattern researched, all needed attributes accessible |
| FEAT-02 | User can extract instance-level feature vector (constraint density, variable count, coefficient statistics) | FeatureExtractor.extract_instance_features() — aggregation from con_expr, obj_expr, variables |
| FEAT-03 | Feature extraction works on models of any size without coupling to a fixed dimension | Fixed feature count per variable, n_vars rows — output shape scales with model, no size cap |
| INTG-01 | sklearn is an optional dependency installed via `pip install cbqs[ml]` | extras_require in setup.py — pattern researched |
| INTG-02 | Importing cbqs without sklearn installed does not raise errors | Lazy import guard — cbqs/__init__.py does NOT import cbqs.ml; ml subpackage guarded internally |
| INTG-03 | ML module has clear import error message when sklearn missing | ImportError catch in cbqs/ml/__init__.py with descriptive message |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | >=1.20 (already a dependency) | Feature matrix creation, array operations | Already required by cbqs core |
| scikit-learn | >=1.2 | StandardScaler for feature normalization | Required for downstream training phases; proven API |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| joblib | >=1.0 (already a dependency) | Future model persistence (Phase 26) | Already installed with cbqs |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| sklearn StandardScaler | Manual mean/std normalization | Manual is simpler for this phase but loses fit/transform pattern for Phase 26 |

**Installation:**
```bash
pip install cbqs[ml]  # Adds sklearn
```

## Architecture Patterns

### Recommended Project Structure
```
cbqs/
├── ml/
│   ├── __init__.py      # sklearn availability check, public re-exports
│   ├── features.py      # FeatureExtractor class
│   ├── training.py      # Stub for Phase 26
│   └── adaptation.py    # Stub for Phase 27
├── __init__.py           # Unchanged — does NOT import ml
├── Model.pyx             # Unchanged — feature extractor reads from this
└── ...
```

### Pattern 1: Lazy Import Guard for Optional Dependency
**What:** Check sklearn availability at `cbqs.ml` import time, raise clear error if missing.
**When to use:** When a subpackage requires an optional dependency that the main package does not.
**Example:**
```python
# cbqs/ml/__init__.py
try:
    import sklearn
except ImportError:
    raise ImportError(
        "cbqs.ml requires scikit-learn. Install it with: "
        "pip install cbqs[ml]"
    ) from None

from .features import FeatureExtractor

__all__ = ["FeatureExtractor"]
```

**Key detail:** The main `cbqs/__init__.py` must NOT import `cbqs.ml`. This ensures `from cbqs import Model` works even without sklearn. Users explicitly do `from cbqs.ml import FeatureExtractor` or `from cbqs.ml.features import FeatureExtractor`.

### Pattern 2: Expression Data Access via Python Iteration
**What:** Extract coefficient and variable information from Expression objects using Python iteration.
**When to use:** Reading constraint/objective structure for feature computation.
**Example:**
```python
# Each Expression is iterable. Iterating yields term lists.
# For a constraint expression like: 3*x0 + 2*x1 <= 5
# expr iteration yields: [3, 0], [2, 1], sense_value, rhs_value
# Each term is [coefficient, var_idx1, var_idx2, ...] where first element is coefficient
# and remaining elements are variable indices

def _parse_expression_terms(expr):
    """Extract (coefficient, variable_indices) pairs from an Expression."""
    terms = list(expr)
    # Last two entries are sense and rhs (if constraint)
    if len(terms) >= 2 and isinstance(terms[-1], int) and isinstance(terms[-2], int):
        data_terms = terms[:-2]
    else:
        data_terms = terms
    result = []
    for term in data_terms:
        if isinstance(term, list) and len(term) >= 2:
            coeff = term[0]
            var_indices = tuple(term[1:])
            result.append((coeff, var_indices))
    return result
```

### Pattern 3: Per-Instance Normalization with Feature Names
**What:** Normalize features per-instance using z-score (mean-center, unit-variance) and provide string labels.
**When to use:** When features have different scales and downstream ML benefits from standardization.
**Rationale:** Per-instance normalization is simpler than fit/transform for Phase 25 (no training data yet). Phase 26 can add a fit/transform pattern when training pipeline exists. String feature labels aid debugging and allow downstream users to interpret feature importance.

### Anti-Patterns to Avoid
- **Importing cbqs.ml from cbqs/__init__.py:** Would break INTG-02 (import without sklearn fails)
- **Accessing C-level struct fields directly from Python:** Use the Python-level Expression iteration, not Cython memory access
- **Coupling feature count to model size:** Feature matrix must be (n_vars, FIXED_N_FEATURES), not (n_vars, n_vars)
- **Using sklearn inside feature extraction code:** Feature computation is numpy-only. sklearn is only needed for normalization (StandardScaler). Could even defer sklearn usage to Phase 26 training — but the import guard is still needed.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Feature normalization | Manual mean/std division | numpy per-column standardization (or sklearn StandardScaler) | Edge cases: zero-variance columns, NaN handling |
| Constraint parsing | Custom C-level extractor | Expression.__iter__() protocol | Already implemented and tested in Expression.pyx |
| Optional dependency check | sys.modules inspection | try/except ImportError | Standard Python pattern, simple and reliable |

**Key insight:** The entire feature extraction pipeline can be built with numpy + Python attribute access on Model/Expression/Variable objects. No Cython helper or C-level access is needed.

## Common Pitfalls

### Pitfall 1: Importing ml from cbqs top-level
**What goes wrong:** Adding `from .ml import ...` to `cbqs/__init__.py` causes `import cbqs` to fail without sklearn.
**Why it happens:** Natural instinct to re-export subpackage APIs at top level.
**How to avoid:** Never import cbqs.ml from cbqs/__init__.py. Users must explicitly import `cbqs.ml`.
**Warning signs:** `ImportError: No module named 'sklearn'` when doing `from cbqs import Model`.

### Pitfall 2: Expression iteration sense/rhs handling
**What goes wrong:** The last two elements from iterating a constraint Expression are the `sense` and `rhs` values (integers), not term data.
**Why it happens:** Expression's `c_liste()` appends sense and rhs to the term list when they are set.
**How to avoid:** Check if sense != -2 before treating last elements as terms. Filter terms by list type (terms are lists, sense/rhs are ints).
**Warning signs:** Feature values that look like constraint senses (0, 1) appearing in coefficient statistics.

### Pitfall 3: Unclosed model data access
**What goes wrong:** Accessing `con_expr` or `obj_expr` on an unclosed model gives expression data but constraint indexing (preprocessing) hasn't been done.
**Why it happens:** Expressions are added during model construction but internal C index structures are built by `close()`.
**How to avoid:** Check `model.constraints_compiled` before extraction. Raise ValueError if False.
**Warning signs:** Missing constraint participation data, incomplete variable-constraint mapping.

### Pitfall 4: Zero-variance features with StandardScaler
**What goes wrong:** If all variables have identical feature values (e.g., all binary, same bounds), z-score normalization produces NaN or division by zero.
**Why it happens:** StandardScaler divides by standard deviation, which is 0 for constant columns.
**How to avoid:** Use numpy-based normalization that replaces zero-variance columns with zeros instead of NaN. Or pass through unchanged.
**Warning signs:** NaN values in feature matrix.

### Pitfall 5: Variable index assumptions
**What goes wrong:** Assuming variables are contiguous 0..n-1 when they might have gaps.
**Why it happens:** `add_variable` uses `max(index, self.n)` which can create gaps if called with explicit indices.
**How to avoid:** Use `model.variables` dict keys and sort them. Feature matrix row i should correspond to the i-th variable in sorted order.
**Warning signs:** IndexError when accessing variable features, wrong variable-to-row mapping.

## Code Examples

### Feature Extraction Data Access Pattern
```python
def _get_variable_constraint_participation(model):
    """Build variable-to-constraint participation data from model."""
    n = model.n
    # model.con_expr is a list of Expression objects (one per constraint)
    var_degree = [0] * n  # Number of constraints each variable appears in
    var_coefficients = [[] for _ in range(n)]  # Coefficients per variable

    for constraint_idx, expr in enumerate(model.con_expr):
        # Iterate over expression terms
        terms = list(expr)
        for term in terms:
            if isinstance(term, list) and len(term) >= 2:
                coeff = term[0]
                for var_idx in term[1:]:
                    if 0 <= var_idx < n:
                        var_degree[var_idx] += 1
                        var_coefficients[var_idx].append(coeff)

    return var_degree, var_coefficients
```

### Optional Dependency Guard
```python
# cbqs/ml/__init__.py
try:
    import sklearn
except ImportError:
    raise ImportError(
        "The cbqs.ml module requires scikit-learn. "
        "Install it with: pip install cbqs[ml]"
    ) from None

from .features import FeatureExtractor

__all__ = ["FeatureExtractor"]
```

### Setup.py extras_require Addition
```python
# In setup.py, update extras_require:
extras_require={
    "test": ["pytest>=7.0"],
    "dev": ["pytest>=7.0", "Cython>=3.0"],
    "ml": ["scikit-learn>=1.2"],
},
```

### Per-Variable Feature Vector
```python
# Features per variable (fixed set):
VARIABLE_FEATURE_NAMES = [
    "degree",                    # Number of constraints this variable appears in
    "coeff_mean",               # Mean absolute coefficient across constraints
    "coeff_max",                # Max absolute coefficient
    "coeff_min",                # Min absolute coefficient (or 0 if not in any constraint)
    "objective_coefficient",     # Coefficient in objective function (0 if absent)
    "bounds_width",             # ub - lb (1 for binary)
    "is_integer",               # 1.0 if integer type, 0.0 otherwise
    "avg_neighbor_degree",      # Average degree of co-occurring variables
    "num_co_occurring_vars",    # Number of unique variables sharing a constraint
]
```

### Instance-Level Feature Vector
```python
INSTANCE_FEATURE_NAMES = [
    "n_variables",              # Total number of variables
    "n_constraints",            # Total number of constraints
    "constraint_density",       # n_constraints / n_variables
    "constraint_variable_ratio",# n_constraints / n_variables (same as density for binary)
    "objective_density",        # Fraction of variables with nonzero objective coefficient
    "integer_variable_fraction",# Fraction of variables that are integer type
    "coeff_mean",              # Global mean of absolute constraint coefficients
    "coeff_std",               # Global std of absolute constraint coefficients
    "coeff_max",               # Global max absolute constraint coefficient
    "bounds_tightness_mean",   # Mean of (ub - lb) across all variables
    "bounds_tightness_std",    # Std of (ub - lb) across all variables
]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hand-designed per-problem features | Standard MIP feature sets (Khalil et al. 2016) | 2016+ | Transferable features across problem families |
| Full GNN on constraint-variable graph | Tabular features + tree models | 2020+ | Simpler, faster, sufficient for small feature sets |
| PassiveAggressiveRegressor for online | SGDRegressor | sklearn 1.8+ | PassiveAggressiveRegressor deprecated |

**Deprecated/outdated:**
- PassiveAggressiveRegressor: Deprecated sklearn 1.8, removed 1.10. Use SGDRegressor instead (already noted in REQUIREMENTS.md out-of-scope table)

## Open Questions

1. **Expression term parsing edge cases**
   - What we know: Expression iteration yields term lists where first element is coefficient and rest are variable indices. Sense/rhs appended for constraints.
   - What's unclear: Whether zero-coefficient terms are filtered or returned with coeff=0, and whether `len_literal[i] == 0` terms appear.
   - Recommendation: Filter terms with zero length or zero coefficient during parsing. Add defensive checks.

2. **Variable ordering in feature matrix**
   - What we know: `model.variables` is a dict with integer keys. `model.n` is the total count.
   - What's unclear: Whether variable indices are always 0..n-1 in practice (they should be for `add_variables(n)` usage, but `add_variable(index=k)` could create gaps).
   - Recommendation: Use sorted(model.variables.keys()) to establish canonical row ordering. Document that row i corresponds to the i-th variable in sorted index order.

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `cbqs/Model.pyx`, `cbqs/Expression.pyx`, `cbqs/Constraint.pyx`, `cbqs/Constraint.pxd`, `cbqs/Expression.pxd`, `cbqs/Model.pxd` — verified data access patterns, attribute availability, Expression iteration protocol
- Direct codebase inspection: `setup.py`, `pyproject.toml` — verified current dependency and packaging setup
- Direct codebase inspection: `cbqs/__init__.py` — verified current import structure with try/except pattern

### Secondary (MEDIUM confidence)
- Khalil et al. 2016 branching feature reference — well-established in MIP solver ML literature, features are standard practice

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - numpy already available, sklearn is standard for tabular ML
- Architecture: HIGH - codebase inspection confirms all data access patterns work via Python attributes
- Pitfalls: HIGH - identified from direct code reading, not assumptions

**Research date:** 2026-02-26
**Valid until:** 2026-03-28 (stable domain, 30-day validity)
