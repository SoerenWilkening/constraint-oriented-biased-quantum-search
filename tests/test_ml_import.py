"""Tests for cbqs.ml import isolation and optional dependency handling.

Verifies that:
- cbqs core imports work without sklearn
- cbqs.ml imports work with sklearn installed
- cbqs.ml raises clear ImportError when sklearn is missing
- Stub modules exist and are importable
- FeatureExtractor class has expected interface
"""
import importlib
import sys
from unittest.mock import patch

import pytest


def test_cbqs_import_without_ml():
    """cbqs core imports succeed and do not trigger sklearn import."""
    from cbqs import Model
    from cbqs import OptimizeResult

    assert Model is not None
    assert OptimizeResult is not None


def test_ml_import_with_sklearn():
    """cbqs.ml import succeeds when sklearn is installed."""
    from cbqs.ml import FeatureExtractor
    from cbqs.ml.features import FeatureExtractor as FE2

    assert FeatureExtractor is not None
    assert FE2 is not None
    assert FeatureExtractor is FE2


def test_ml_subpackage_structure():
    """Stub modules for training and adaptation are importable."""
    import cbqs.ml.training
    import cbqs.ml.adaptation

    assert cbqs.ml.training is not None
    assert cbqs.ml.adaptation is not None


def test_ml_import_error_message():
    """Importing cbqs.ml without sklearn raises ImportError with install instructions."""
    # Remove cbqs.ml and its submodules from sys.modules to force re-import
    modules_to_remove = [key for key in sys.modules if key.startswith('cbqs.ml')]
    for key in modules_to_remove:
        del sys.modules[key]

    with patch.dict('sys.modules', {'sklearn': None}):
        with pytest.raises(ImportError, match="pip install cbqs\\[ml\\]"):
            importlib.import_module('cbqs.ml')

    # Restore cbqs.ml by re-importing (cleanup)
    modules_to_remove = [key for key in sys.modules if key.startswith('cbqs.ml')]
    for key in modules_to_remove:
        del sys.modules[key]
    importlib.import_module('cbqs.ml')


def test_feature_extractor_has_expected_interface():
    """FeatureExtractor class has extract_variable_features and extract_instance_features."""
    from cbqs.ml.features import FeatureExtractor

    fe = FeatureExtractor()

    assert hasattr(fe, 'extract_variable_features')
    assert hasattr(fe, 'extract_instance_features')
    assert hasattr(fe, 'feature_names')
    assert hasattr(fe, 'instance_feature_names')
    assert callable(fe.extract_variable_features)
    assert callable(fe.extract_instance_features)
