"""ML subpackage for CBQS — feature extraction and weight prediction.

Requires scikit-learn as an optional dependency.
Install with: pip install cbqs[ml]
"""
try:
    import sklearn
except ImportError:
    raise ImportError(
        "The cbqs.ml module requires scikit-learn. "
        "Install it with: pip install cbqs[ml]"
    ) from None

from .features import FeatureExtractor
from .training import WeightPredictor, collect_training_data, evaluate, evaluate_weights
from .adaptation import adaptive_solve, AdaptiveResult

__all__ = [
    "FeatureExtractor",
    "WeightPredictor",
    "collect_training_data",
    "evaluate",
    "evaluate_weights",
    "adaptive_solve",
    "AdaptiveResult",
]
