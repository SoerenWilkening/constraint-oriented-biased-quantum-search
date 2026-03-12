"""
TrainingLog -- Structured JSON logging for CBQS ML training pipeline.

Logs training events at three granularity levels (strategy, model, refit)
plus incremental retrain events. Provides querying, display, and file I/O
interfaces.

Three granularity levels:
  - Per-Strategy (finest): every parameter vector tried and its result.
  - Per-Model (medium): summary per training model.
  - Per-Refit (coarsest): predictor quality after each refit.
  - Per-Retrain: incremental training episodes.
"""

import json
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Optional


# ------------------------------------------------------------------
# Event dataclasses
# ------------------------------------------------------------------

@dataclass
class StrategyEvent:
    """A single strategy evaluation within a model."""
    model_idx: int
    phase: str
    strategy_idx: int
    parameters: dict
    result: dict  # objective, feasible, time, auc, history


@dataclass
class ModelEvent:
    """Summary of all strategies tried for a single training model."""
    model_idx: int
    n_strategies_tried: int
    best_signal: float
    best_parameters: dict
    trivially_feasible: bool


@dataclass
class RefitEvent:
    """Predictor quality snapshot after a refit."""
    n_training_models: int
    validation_score: float
    timestamp: str
    annealing_a: Optional[float] = None


@dataclass
class RetrainEvent:
    """Incremental training episode record."""
    episode: int
    new_instances: list
    total_instances: int
    trees_before: int
    trees_after: int
    score_before: float
    score_after: float
    timestamp: str


# Map from type name string to dataclass for deserialization
_EVENT_TYPES = {
    "StrategyEvent": StrategyEvent,
    "ModelEvent": ModelEvent,
    "RefitEvent": RefitEvent,
    "RetrainEvent": RetrainEvent,
}


# ------------------------------------------------------------------
# Numpy-safe JSON serialization
# ------------------------------------------------------------------

def _numpy_safe(obj):
    """Convert numpy types to Python-native types for JSON serialization."""
    try:
        import numpy as np
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
    except ImportError:
        pass
    return obj


def _deep_convert(obj):
    """Recursively convert numpy types in nested structures."""
    obj = _numpy_safe(obj)
    if isinstance(obj, dict):
        return {k: _deep_convert(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_deep_convert(v) for v in obj]
    return obj


# ------------------------------------------------------------------
# TrainingLog
# ------------------------------------------------------------------

class TrainingLog:
    """Structured training log with three granularity levels.

    Logs strategy, model, refit, and retrain events. Supports querying,
    display (plot, compare, DataFrame), and JSON file I/O.

    Parameters
    ----------
    path : str or Path or None
        Optional default file path for save/load operations.
    """

    def __init__(self, path=None):
        self._events = []
        self._path = Path(path) if path else None

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def log_strategy(self, **kwargs):
        """Log a per-strategy event.

        Parameters
        ----------
        model_idx : int
        phase : str
        strategy_idx : int
        parameters : dict
        result : dict
            Keys: objective, feasible, time, auc, history.
        """
        self._events.append(StrategyEvent(**kwargs))

    def log_model(self, **kwargs):
        """Log a per-model summary event.

        Parameters
        ----------
        model_idx : int
        n_strategies_tried : int
        best_signal : float
        best_parameters : dict
        trivially_feasible : bool
        """
        self._events.append(ModelEvent(**kwargs))

    def log_refit(self, **kwargs):
        """Log a per-refit event.

        Parameters
        ----------
        n_training_models : int
        validation_score : float
        timestamp : str
        """
        self._events.append(RefitEvent(**kwargs))

    def log_retrain(self, **kwargs):
        """Log an incremental retrain event.

        Parameters
        ----------
        episode : int
        new_instances : list
        total_instances : int
        trees_before : int
        trees_after : int
        score_before : float
        score_after : float
        timestamp : str
        """
        self._events.append(RetrainEvent(**kwargs))

    def flush(self):
        """Write events to the default path (set at construction)."""
        if self._path is not None:
            self.save(self._path)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def summary(self):
        """Learning curve: refit events with quality over time.

        Returns
        -------
        list of dict
            Each dict has keys from RefitEvent fields.
        """
        return [
            asdict(e) for e in self._events if isinstance(e, RefitEvent)
        ]

    def model_details(self, model_idx):
        """All strategies and summary for a given model.

        Parameters
        ----------
        model_idx : int
            The model index to look up.

        Returns
        -------
        dict
            Contains model event fields plus a 'strategies' key with the
            list of strategy events for this model.

        Raises
        ------
        KeyError
            If no ModelEvent exists for the given model_idx.
        """
        model_evt = None
        for e in self._events:
            if isinstance(e, ModelEvent) and e.model_idx == model_idx:
                model_evt = e
                break
        if model_evt is None:
            raise KeyError(f"No model event found for model_idx={model_idx}")

        strats = [
            asdict(e) for e in self._events
            if isinstance(e, StrategyEvent) and e.model_idx == model_idx
        ]
        result = asdict(model_evt)
        result["strategies"] = strats
        return result

    def strategies(self, model_idx, phase=None):
        """Per-strategy results, optionally filtered by phase.

        Parameters
        ----------
        model_idx : int
            The model index to filter by.
        phase : str or None
            If given, only return strategies for this phase.

        Returns
        -------
        list of dict
        """
        result = []
        for e in self._events:
            if not isinstance(e, StrategyEvent):
                continue
            if e.model_idx != model_idx:
                continue
            if phase is not None and e.phase != phase:
                continue
            result.append(asdict(e))
        return result

    def refit_history(self):
        """Return all refit events as a list of dicts.

        Returns
        -------
        list of dict
        """
        return [
            asdict(e) for e in self._events if isinstance(e, RefitEvent)
        ]

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def plot_learning_curve(self, ax=None):
        """Plot validation score vs n_training_models.

        Parameters
        ----------
        ax : matplotlib.axes.Axes or None
            If None, a new figure and axes are created.

        Returns
        -------
        matplotlib.figure.Figure
            The figure containing the plot.
        """
        import matplotlib.pyplot as plt

        refits = self.refit_history()
        xs = [r["n_training_models"] for r in refits]
        ys = [r["validation_score"] for r in refits]

        if ax is None:
            fig, ax = plt.subplots()
        else:
            fig = ax.get_figure()

        ax.plot(xs, ys, marker="o")
        ax.set_xlabel("n_training_models")
        ax.set_ylabel("validation_score")
        ax.set_title("Learning Curve")
        return fig

    def compare(self, other):
        """Side-by-side comparison of two training runs.

        Parameters
        ----------
        other : TrainingLog

        Returns
        -------
        dict
            Keys 'log1' and 'log2', each containing summary statistics.
        """
        def _stats(log):
            refits = log.refit_history()
            models = [e for e in log._events if isinstance(e, ModelEvent)]
            strategies = [e for e in log._events if isinstance(e, StrategyEvent)]
            best_score = max(
                (r["validation_score"] for r in refits), default=None
            )
            return {
                "n_refits": len(refits),
                "n_models": len(models),
                "n_strategies": len(strategies),
                "best_validation_score": best_score,
            }

        return {
            "log1": _stats(self),
            "log2": _stats(other),
        }

    def to_dataframe(self, level="model"):
        """Convert events at a given level to a pandas DataFrame.

        Parameters
        ----------
        level : str
            One of 'strategy', 'model', 'refit', 'retrain'.

        Returns
        -------
        pandas.DataFrame
        """
        import pandas as pd

        type_map = {
            "strategy": StrategyEvent,
            "model": ModelEvent,
            "refit": RefitEvent,
            "retrain": RetrainEvent,
        }
        evt_type = type_map.get(level)
        if evt_type is None:
            raise ValueError(
                f"Unknown level {level!r}. "
                f"Choose from: {list(type_map.keys())}"
            )
        rows = [asdict(e) for e in self._events if isinstance(e, evt_type)]
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def save(self, path=None):
        """Write all events to a JSON file.

        Parameters
        ----------
        path : str or Path or None
            File path. If None, uses the path set at construction.
        """
        path = Path(path) if path else self._path
        if path is None:
            raise ValueError("No path specified for save")

        records = []
        for e in self._events:
            record = {
                "type": type(e).__name__,
                "data": _deep_convert(asdict(e)),
            }
            records.append(record)

        path.write_text(json.dumps(records, indent=2))

    def load(self, path):
        """Load events from a JSON file, replacing current events.

        Parameters
        ----------
        path : str or Path
            Path to the JSON file.
        """
        path = Path(path)
        data = json.loads(path.read_text())
        self._events = []
        for record in data:
            type_name = record["type"]
            cls = _EVENT_TYPES.get(type_name)
            if cls is None:
                raise ValueError(f"Unknown event type: {type_name!r}")
            self._events.append(cls(**record["data"]))

    # ------------------------------------------------------------------
    # Serialization helper
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_event(event):
        """Handle numpy arrays and other non-JSON-serializable types.

        Parameters
        ----------
        event : dataclass instance

        Returns
        -------
        dict
        """
        return _deep_convert(asdict(event))
