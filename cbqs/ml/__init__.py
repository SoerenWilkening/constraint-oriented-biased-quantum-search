"""ML subpackage for CBQS — feature extraction and weight prediction.

The ES pipeline (PolynomialPredictor, ESTrainer, ESTrainerConfig) requires
numpy only. The legacy pipeline (WeightPredictor, etc.) requires scikit-learn
as an optional dependency. Install with: pip install cbqs[ml]
"""

# --- ES pipeline (numpy only) ---
from .polynomial import PolynomialPredictor
from .es_trainer import ESTrainer, ESTrainerConfig

# --- Legacy pipeline (requires sklearn) ---
try:
    import sklearn
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False

if _HAS_SKLEARN:
    from .features import FeatureExtractor
    from .training import WeightPredictor, collect_training_data, evaluate, evaluate_weights, validate_transfer
    from .adaptation import adaptive_solve, AdaptiveResult

__all__ = [
    "PolynomialPredictor",
    "ESTrainer",
    "ESTrainerConfig",
]

if _HAS_SKLEARN:
    __all__ += [
        "FeatureExtractor",
        "WeightPredictor",
        "collect_training_data",
        "evaluate",
        "evaluate_weights",
        "validate_transfer",
        "adaptive_solve",
        "AdaptiveResult",
    ]
