"""Tests for ES checkpoint save/load/resume support."""

import json
import os
import tempfile

import numpy as np
import pytest

from cbqs.ml.es_checkpoint import save_checkpoint, load_checkpoint, add_instances
from cbqs.ml.polynomial import THETA_SIZE


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory for checkpoint files."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def sample_checkpoint_data():
    """Return a dict of sample checkpoint fields."""
    rng = np.random.RandomState(42)
    theta = rng.randn(THETA_SIZE)
    best_theta = rng.randn(THETA_SIZE)
    optimizer_state = {
        'm': rng.randn(THETA_SIZE),
        'v': np.abs(rng.randn(THETA_SIZE)),
        't': 17,
    }
    training_pool = ['/data/inst_001.lp', '/data/inst_002.lp', '/data/inst_003.lp']
    config = {'lr': 0.001, 'sigma': 0.02, 'K': 50, 'batch_size': 5}
    return dict(
        theta=theta,
        optimizer_state=optimizer_state,
        training_pool=training_pool,
        step=42,
        config=config,
        log_path='/logs/training.jsonl',
        best_theta=best_theta,
        best_validation_signal=3.14,
    )


class TestSaveLoadRoundtrip:
    """save_checkpoint then load_checkpoint preserves all fields."""

    def test_all_fields_roundtrip(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        loaded = load_checkpoint(path)

        np.testing.assert_array_equal(loaded['theta'], sample_checkpoint_data['theta'])
        np.testing.assert_array_equal(loaded['best_theta'], sample_checkpoint_data['best_theta'])
        np.testing.assert_array_equal(
            loaded['optimizer_state']['m'], sample_checkpoint_data['optimizer_state']['m']
        )
        np.testing.assert_array_equal(
            loaded['optimizer_state']['v'], sample_checkpoint_data['optimizer_state']['v']
        )
        assert loaded['optimizer_state']['t'] == 17
        assert loaded['training_pool'] == sample_checkpoint_data['training_pool']
        assert loaded['step'] == 42
        assert loaded['config'] == sample_checkpoint_data['config']
        assert loaded['log_path'] == '/logs/training.jsonl'
        assert loaded['best_validation_signal'] == pytest.approx(3.14)

    def test_theta_array_dtype_and_shape(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        loaded = load_checkpoint(path)
        assert loaded['theta'].shape == (THETA_SIZE,)
        assert loaded['theta'].dtype == np.float64

    def test_best_theta_array_roundtrip(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        loaded = load_checkpoint(path)
        np.testing.assert_array_equal(loaded['best_theta'], sample_checkpoint_data['best_theta'])
        assert loaded['best_theta'].shape == (THETA_SIZE,)

    def test_optimizer_state_roundtrip(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        loaded = load_checkpoint(path)
        orig = sample_checkpoint_data['optimizer_state']
        np.testing.assert_array_equal(loaded['optimizer_state']['m'], orig['m'])
        np.testing.assert_array_equal(loaded['optimizer_state']['v'], orig['v'])
        assert loaded['optimizer_state']['t'] == orig['t']

    def test_training_pool_roundtrip(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        loaded = load_checkpoint(path)
        assert loaded['training_pool'] == sample_checkpoint_data['training_pool']

    def test_config_dict_roundtrip(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        loaded = load_checkpoint(path)
        assert loaded['config'] == sample_checkpoint_data['config']


class TestFileFormat:
    """Checkpoint uses .npz + .json, no pickle."""

    def test_creates_npz_and_json(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        assert os.path.isfile(path + '.npz')
        assert os.path.isfile(path + '.json')

    def test_no_pickle_files(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        files = os.listdir(tmp_dir)
        for f in files:
            assert not f.endswith('.pkl'), f"Pickle file found: {f}"
            assert not f.endswith('.pickle'), f"Pickle file found: {f}"

    def test_json_sidecar_is_valid_json(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        with open(path + '.json', 'r') as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert data['step'] == 42

    def test_npz_contains_expected_arrays(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        with np.load(path + '.npz') as npz:
            assert 'theta' in npz
            assert 'best_theta' in npz
            assert 'optimizer_m' in npz
            assert 'optimizer_v' in npz


class TestAddInstances:
    """add_instances extends the training pool."""

    def test_add_instances_extends_pool(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        new = ['/data/inst_004.lp', '/data/inst_005.lp']
        add_instances(path, new)
        loaded = load_checkpoint(path)
        expected = sample_checkpoint_data['training_pool'] + new
        assert loaded['training_pool'] == expected

    def test_add_instances_no_duplicates(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        # Add one existing and one new
        new = ['/data/inst_002.lp', '/data/inst_004.lp']
        add_instances(path, new)
        loaded = load_checkpoint(path)
        expected = sample_checkpoint_data['training_pool'] + ['/data/inst_004.lp']
        assert loaded['training_pool'] == expected

    def test_add_instances_preserves_other_fields(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        add_instances(path, ['/data/new.lp'])
        loaded = load_checkpoint(path)
        assert loaded['step'] == 42
        np.testing.assert_array_equal(loaded['theta'], sample_checkpoint_data['theta'])


class TestErrorHandling:
    """Error handling for missing/corrupt checkpoints."""

    def test_load_nonexistent_raises(self, tmp_dir):
        path = os.path.join(tmp_dir, 'nonexistent')
        with pytest.raises(FileNotFoundError):
            load_checkpoint(path)

    def test_load_missing_json_raises(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        os.remove(path + '.json')
        with pytest.raises(FileNotFoundError):
            load_checkpoint(path)

    def test_load_missing_npz_raises(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        os.remove(path + '.npz')
        with pytest.raises(FileNotFoundError):
            load_checkpoint(path)

    def test_corrupt_json_raises(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        with open(path + '.json', 'w') as f:
            f.write('not valid json {{{')
        with pytest.raises(ValueError, match="Corrupt checkpoint metadata"):
            load_checkpoint(path)

    def test_corrupt_npz_raises(self, tmp_dir, sample_checkpoint_data):
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        with open(path + '.npz', 'wb') as f:
            f.write(b'garbage data not a zip')
        with pytest.raises(ValueError, match="Corrupt checkpoint array"):
            load_checkpoint(path)


class TestDefaultValues:
    """Optional fields have sensible defaults."""

    def test_missing_optional_json_keys_use_defaults(self, tmp_dir, sample_checkpoint_data):
        """Checkpoint from older version missing optional keys loads with defaults."""
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        # Manually strip optional keys from the JSON sidecar
        with open(path + '.json', 'r') as f:
            metadata = json.load(f)
        for key in ['log_path', 'best_validation_signal', 'config']:
            metadata.pop(key, None)
        with open(path + '.json', 'w') as f:
            json.dump(metadata, f)
        loaded = load_checkpoint(path)
        assert loaded['log_path'] == ''
        assert loaded['best_validation_signal'] == float('-inf')
        assert loaded['config'] == {}

    def test_none_best_theta(self, tmp_dir, sample_checkpoint_data):
        sample_checkpoint_data['best_theta'] = None
        sample_checkpoint_data['best_validation_signal'] = float('-inf')
        path = os.path.join(tmp_dir, 'ckpt')
        save_checkpoint(path, **sample_checkpoint_data)
        loaded = load_checkpoint(path)
        assert loaded['best_theta'] is None
        assert loaded['best_validation_signal'] == float('-inf')
