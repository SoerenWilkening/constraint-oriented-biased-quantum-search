"""
Unit tests for cbqs.ml.training_log.TrainingLog.

Tests structured JSON logging at three granularity levels (strategy, model,
refit) plus querying, display, and file I/O.
"""

import json
import os
import tempfile

import pytest

from cbqs.ml.training_log import (
    TrainingLog,
    StrategyEvent,
    ModelEvent,
    RefitEvent,
    RetrainEvent,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_log():
    """Create a TrainingLog with a few events at each level."""
    log = TrainingLog()
    log.log_strategy(
        model_idx=0,
        phase="sat",
        strategy_idx=0,
        parameters={"branching_bias": 0.5},
        result={"objective": 10.0, "feasible": True, "time": 1.2,
                "auc": 0.8, "history": [(10.0, 0.5)]},
    )
    log.log_strategy(
        model_idx=0,
        phase="opt",
        strategy_idx=1,
        parameters={"branching_bias": 0.7},
        result={"objective": 8.0, "feasible": True, "time": 0.9,
                "auc": 0.9, "history": [(8.0, 0.3)]},
    )
    log.log_model(
        model_idx=0,
        n_strategies_tried=2,
        best_signal=0.9,
        best_parameters={"branching_bias": 0.7},
        trivially_feasible=False,
    )
    log.log_strategy(
        model_idx=1,
        phase="sat",
        strategy_idx=0,
        parameters={"branching_bias": 0.3},
        result={"objective": 12.0, "feasible": False, "time": 2.0,
                "auc": 0.6, "history": []},
    )
    log.log_model(
        model_idx=1,
        n_strategies_tried=1,
        best_signal=0.6,
        best_parameters={"branching_bias": 0.3},
        trivially_feasible=True,
    )
    log.log_refit(
        n_training_models=2,
        validation_score=0.85,
        timestamp="2026-01-01T00:00:00",
    )
    return log


# ===================================================================
# Writing events
# ===================================================================


class TestWritingEvents:
    """Tests for logging events at each granularity level."""

    def test_log_strategy_event(self):
        log = TrainingLog()
        log.log_strategy(
            model_idx=0,
            phase="sat",
            strategy_idx=0,
            parameters={"branching_bias": 0.5},
            result={"objective": 10.0, "feasible": True, "time": 1.0,
                    "auc": 0.8, "history": []},
        )
        assert len(log._events) == 1
        evt = log._events[0]
        assert isinstance(evt, StrategyEvent)
        assert evt.model_idx == 0
        assert evt.phase == "sat"
        assert evt.strategy_idx == 0
        assert evt.parameters == {"branching_bias": 0.5}
        assert evt.result["objective"] == 10.0

    def test_log_model_event(self):
        log = TrainingLog()
        log.log_model(
            model_idx=0,
            n_strategies_tried=3,
            best_signal=0.95,
            best_parameters={"branching_bias": 0.8},
            trivially_feasible=False,
        )
        assert len(log._events) == 1
        evt = log._events[0]
        assert isinstance(evt, ModelEvent)
        assert evt.model_idx == 0
        assert evt.n_strategies_tried == 3
        assert evt.best_signal == 0.95
        assert evt.trivially_feasible is False

    def test_log_refit_event(self):
        log = TrainingLog()
        log.log_refit(
            n_training_models=10,
            validation_score=0.92,
            timestamp="2026-01-01T12:00:00",
        )
        assert len(log._events) == 1
        evt = log._events[0]
        assert isinstance(evt, RefitEvent)
        assert evt.n_training_models == 10
        assert evt.validation_score == 0.92
        assert evt.timestamp == "2026-01-01T12:00:00"

    def test_log_retrain_event(self):
        log = TrainingLog()
        log.log_retrain(
            episode=1,
            new_instances=["inst_a", "inst_b"],
            total_instances=10,
            trees_before=50,
            trees_after=60,
            score_before=0.80,
            score_after=0.85,
            timestamp="2026-01-02T00:00:00",
        )
        assert len(log._events) == 1
        evt = log._events[0]
        assert isinstance(evt, RetrainEvent)
        assert evt.episode == 1
        assert evt.new_instances == ["inst_a", "inst_b"]
        assert evt.total_instances == 10
        assert evt.trees_before == 50
        assert evt.trees_after == 60
        assert evt.score_before == 0.80
        assert evt.score_after == 0.85

    def test_log_preserves_order(self):
        log = _make_log()
        types = [type(e).__name__ for e in log._events]
        assert types == [
            "StrategyEvent",
            "StrategyEvent",
            "ModelEvent",
            "StrategyEvent",
            "ModelEvent",
            "RefitEvent",
        ]


# ===================================================================
# Reading / querying
# ===================================================================


class TestQuerying:
    """Tests for querying logged events."""

    def test_summary_returns_learning_curve(self):
        log = _make_log()
        curve = log.summary()
        assert isinstance(curve, list)
        assert len(curve) == 1  # one refit event
        assert curve[0]["n_training_models"] == 2
        assert curve[0]["validation_score"] == 0.85

    def test_model_details_returns_strategies(self):
        log = _make_log()
        details = log.model_details(0)
        assert details["model_idx"] == 0
        assert details["n_strategies_tried"] == 2
        assert details["best_signal"] == 0.9
        assert len(details["strategies"]) == 2

    def test_strategies_filters_by_phase(self):
        log = _make_log()
        sat_strats = log.strategies(0, phase="sat")
        assert len(sat_strats) == 1
        assert sat_strats[0]["phase"] == "sat"

        opt_strats = log.strategies(0, phase="opt")
        assert len(opt_strats) == 1
        assert opt_strats[0]["phase"] == "opt"

    def test_refit_history(self):
        log = _make_log()
        history = log.refit_history()
        assert isinstance(history, list)
        assert len(history) == 1
        assert history[0]["n_training_models"] == 2
        assert history[0]["validation_score"] == 0.85


# ===================================================================
# File I/O
# ===================================================================


class TestFileIO:
    """Tests for save/load and file operations."""

    def test_save_creates_json_file(self, tmp_path):
        log = _make_log()
        path = tmp_path / "training.json"
        log.save(path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert isinstance(data, list)
        assert len(data) == 6

    def test_load_reads_back_events(self, tmp_path):
        log = _make_log()
        path = tmp_path / "training.json"
        log.save(path)

        log2 = TrainingLog()
        log2.load(path)
        assert len(log2._events) == 6
        # Check types are reconstructed
        assert isinstance(log2._events[0], StrategyEvent)
        assert isinstance(log2._events[2], ModelEvent)
        assert isinstance(log2._events[5], RefitEvent)

    def test_append_to_existing_file(self, tmp_path):
        path = tmp_path / "training.json"
        log1 = TrainingLog(path=path)
        log1.log_refit(
            n_training_models=5,
            validation_score=0.80,
            timestamp="2026-01-01T00:00:00",
        )
        log1.save()

        log2 = TrainingLog(path=path)
        log2.load(path)
        log2.log_refit(
            n_training_models=10,
            validation_score=0.90,
            timestamp="2026-01-02T00:00:00",
        )
        log2.save()

        log3 = TrainingLog()
        log3.load(path)
        assert len(log3._events) == 2

    def test_empty_log_summary(self):
        log = TrainingLog()
        assert log.summary() == []


# ===================================================================
# Display
# ===================================================================


class TestDisplay:
    """Tests for display and comparison methods."""

    def test_summary_as_dataframe(self):
        pd = pytest.importorskip("pandas")
        log = _make_log()
        df = log.to_dataframe(level="model")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2  # two model events
        assert "model_idx" in df.columns

    def test_compare_two_logs(self):
        log1 = _make_log()
        log2 = _make_log()
        # Add an extra refit to log2
        log2.log_refit(
            n_training_models=5,
            validation_score=0.90,
            timestamp="2026-01-03T00:00:00",
        )
        result = log1.compare(log2)
        assert isinstance(result, dict)
        assert "log1" in result
        assert "log2" in result
        assert result["log1"]["n_refits"] == 1
        assert result["log2"]["n_refits"] == 2

    def test_plot_learning_curve_returns_figure(self):
        mpl = pytest.importorskip("matplotlib")
        log = _make_log()
        fig = log.plot_learning_curve()
        assert fig is not None
        import matplotlib.figure
        assert isinstance(fig, matplotlib.figure.Figure)
        mpl.pyplot.close(fig)


# ===================================================================
# Edge cases
# ===================================================================


class TestEdgeCases:
    """Tests for error handling and edge cases."""

    def test_model_details_invalid_idx(self):
        log = _make_log()
        with pytest.raises(KeyError):
            log.model_details(999)

    def test_strategies_no_matching_phase(self):
        log = _make_log()
        result = log.strategies(0, phase="nonexistent")
        assert result == []

    def test_log_with_numpy_arrays_serialized(self, tmp_path):
        np = pytest.importorskip("numpy")
        log = TrainingLog()
        log.log_strategy(
            model_idx=0,
            phase="sat",
            strategy_idx=0,
            parameters={"weights": np.array([0.1, 0.2, 0.3])},
            result={"objective": np.float64(10.0), "feasible": True,
                    "time": np.float64(1.0), "auc": np.float64(0.8),
                    "history": [np.array([1.0, 2.0])]},
        )
        path = tmp_path / "numpy_log.json"
        log.save(path)
        # Must not raise -- numpy types are serialized
        data = json.loads(path.read_text())
        assert len(data) == 1
        assert data[0]["data"]["parameters"]["weights"] == [0.1, 0.2, 0.3]
