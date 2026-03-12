"""
Per-instance normalization and renormalization of objective values.

Provides InstanceNormalizer which:
- Converts all problems to maximization internally (negates minimization).
- Tracks per-instance best and worst objective values.
- Normalizes via (val - worst) / (best - worst), producing values in [0, 1].
- Stores raw values for renormalization when best/worst change on refit.
"""


class InstanceNormalizer:
    """Track per-instance best/worst and normalize objectives.

    All problems converted to maximization internally.
    Normalization: (val - worst) / (best - worst)
    Stores raw values for renormalization on refit.
    """

    def __init__(self):
        self._instance_stats = {}  # instance_id -> {best, worst, is_min}
        self._raw_records = []     # [(instance_id, raw_obj, config_idx), ...]

    def register(self, instance_id, raw_objective, is_minimization=False,
                 config_idx=None):
        """Register a raw objective value, update best/worst.

        Args:
            instance_id: identifier for the problem instance.
            raw_objective: the raw objective value from the solver.
            is_minimization: if True, the objective is negated internally
                so that higher values are always better.
            config_idx: optional index identifying the parameter config
                that produced this value. Stored for renormalization.
        """
        internal = -raw_objective if is_minimization else raw_objective

        if instance_id not in self._instance_stats:
            self._instance_stats[instance_id] = {
                "best": internal,
                "worst": internal,
                "is_min": is_minimization,
            }
        else:
            stats = self._instance_stats[instance_id]
            if internal > stats["best"]:
                stats["best"] = internal
            if internal < stats["worst"]:
                stats["worst"] = internal

        self._raw_records.append((instance_id, raw_objective, config_idx))

    def normalize(self, instance_id, raw_objective):
        """Normalize a value using current best/worst for instance.

        Args:
            instance_id: identifier for the problem instance.
            raw_objective: the raw objective value to normalize.

        Returns:
            Normalized value in [0, 1]. Returns 0.0 if best == worst.
        """
        stats = self._instance_stats[instance_id]
        is_min = stats["is_min"]
        internal = -raw_objective if is_min else raw_objective

        best = stats["best"]
        worst = stats["worst"]

        if best == worst:
            return 0.0

        return (internal - worst) / (best - worst)

    def renormalize_all(self):
        """Recompute all normalized values using current best/worst.

        Returns:
            List of (instance_id, normalized_value, config_idx) tuples
            for every registered record.
        """
        results = []
        for instance_id, raw_obj, config_idx in self._raw_records:
            norm_val = self.normalize(instance_id, raw_obj)
            results.append((instance_id, norm_val, config_idx))
        return results

    def get_stats(self, instance_id):
        """Return current best/worst for an instance.

        Args:
            instance_id: identifier for the problem instance.

        Returns:
            Dict with 'best' and 'worst' keys (in internal maximization
            space).
        """
        stats = self._instance_stats[instance_id]
        return {"best": stats["best"], "worst": stats["worst"]}
