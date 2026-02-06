# Optional imports - some dependencies may not be available
try:
    from .Model import Model, set_seed
except ImportError as e:
    # Model requires optional dependencies (gurobipy, etc.)
    Model = None
    set_seed = None

from .Constants import *
from .result import OptimizeResult


__version__ = '1.0.1'