"""ES checkpoint save/load/resume support.

Provides functions to save and load ES training state (theta, optimizer
state, training pool, config, etc.) using .npz for numpy arrays and a
.json sidecar for scalar/string/dict metadata. No pickle is used.

Provides:
- save_checkpoint: Save full training state to disk.
- load_checkpoint: Load training state from disk.
- add_instances: Extend the training pool in an existing checkpoint.
"""

import json
import os

import numpy as np


def save_checkpoint(path, theta, optimizer_state, training_pool, step,
                    config, log_path, best_theta, best_validation_signal):
    """Save ES training checkpoint to disk.

    Creates two files: ``<path>.npz`` for numpy arrays and ``<path>.json``
    for scalar/string/dict metadata.

    Args:
        path: Base path (without extension). Two files are created:
            ``<path>.npz`` and ``<path>.json``.
        theta: Current coefficient vector, shape (THETA_SIZE,).
        optimizer_state: Dict from Adam.state_dict() with keys
            'm' (array), 'v' (array), 't' (int).
        training_pool: List of paths to training instance files.
        step: Current training step (int).
        config: Dict of training hyperparameters.
        log_path: Path to the training log file.
        best_theta: Best theta by validation signal (array or None).
        best_validation_signal: Best validation signal value (float).
    """
    # Save numpy arrays
    arrays = {
        'theta': np.asarray(theta, dtype=np.float64),
        'optimizer_m': np.asarray(optimizer_state['m'], dtype=np.float64),
        'optimizer_v': np.asarray(optimizer_state['v'], dtype=np.float64),
    }
    if best_theta is not None:
        arrays['best_theta'] = np.asarray(best_theta, dtype=np.float64)
    np.savez(path + '.npz', **arrays)

    # Save metadata as JSON sidecar
    metadata = {
        'optimizer_t': optimizer_state['t'],
        'training_pool': list(training_pool),
        'step': int(step),
        'config': dict(config),
        'log_path': str(log_path),
        'best_validation_signal': float(best_validation_signal),
    }
    with open(path + '.json', 'w') as f:
        json.dump(metadata, f, indent=2)


def load_checkpoint(path):
    """Load ES training checkpoint from disk.

    Args:
        path: Base path (without extension). Expects ``<path>.npz``
            and ``<path>.json`` to exist.

    Returns:
        Dict with keys: theta, optimizer_state, training_pool, step,
        config, log_path, best_theta, best_validation_signal.

    Raises:
        FileNotFoundError: If either the .npz or .json file is missing.
    """
    npz_path = path + '.npz'
    json_path = path + '.json'

    if not os.path.isfile(npz_path):
        raise FileNotFoundError(f"Checkpoint array file not found: {npz_path}")
    if not os.path.isfile(json_path):
        raise FileNotFoundError(f"Checkpoint metadata file not found: {json_path}")

    # Load arrays
    try:
        npz = np.load(npz_path)
    except Exception as e:
        raise ValueError(f"Corrupt checkpoint array file: {npz_path}") from e
    try:
        theta = npz['theta']
        optimizer_m = npz['optimizer_m']
        optimizer_v = npz['optimizer_v']
        has_best = 'best_theta' in npz
        best_theta = npz['best_theta'] if has_best else None
    finally:
        npz.close()

    # Load metadata
    try:
        with open(json_path, 'r') as f:
            metadata = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Corrupt checkpoint metadata file: {json_path}") from e

    optimizer_state = {
        'm': optimizer_m,
        'v': optimizer_v,
        't': metadata.get('optimizer_t', 0),
    }

    return {
        'theta': theta,
        'optimizer_state': optimizer_state,
        'training_pool': metadata.get('training_pool', []),
        'step': metadata.get('step', 0),
        'config': metadata.get('config', {}),
        'log_path': metadata.get('log_path', ''),
        'best_theta': best_theta,
        'best_validation_signal': metadata.get('best_validation_signal', float('-inf')),
    }


def add_instances(checkpoint_path, new_instances):
    """Extend the training pool in an existing checkpoint.

    Adds new instance paths to the training pool, skipping any that
    are already present (no duplicates).

    Args:
        checkpoint_path: Base path of the checkpoint (without extension).
        new_instances: List of new instance file paths to add.
    """
    json_path = checkpoint_path + '.json'

    with open(json_path, 'r') as f:
        metadata = json.load(f)

    existing = set(metadata['training_pool'])
    for inst in new_instances:
        if inst not in existing:
            metadata['training_pool'].append(inst)
            existing.add(inst)

    with open(json_path, 'w') as f:
        json.dump(metadata, f, indent=2)
