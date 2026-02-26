"""Feature extraction from CBQS Model objects for ML-based branching weight prediction.

Provides the FeatureExtractor class which extracts per-variable and instance-level
structural features from closed Model objects. Features follow standard MIP feature
sets from solver ML literature (Khalil et al.).
"""


class FeatureExtractor:
    """Extract structural features from CBQS Model objects.

    Placeholder — will be implemented in Plan 02 (Phase 25).
    """

    def extract_variable_features(self, model):
        """Extract per-variable feature matrix from a closed Model.

        Parameters
        ----------
        model : Model
            A closed CBQS Model instance.

        Returns
        -------
        numpy.ndarray
            Feature matrix of shape (n_vars, n_features).

        Raises
        ------
        NotImplementedError
            Always — not yet implemented.
        """
        raise NotImplementedError("Feature extraction not yet implemented")

    def extract_instance_features(self, model):
        """Extract instance-level feature vector from a closed Model.

        Parameters
        ----------
        model : Model
            A closed CBQS Model instance.

        Returns
        -------
        numpy.ndarray
            Feature vector of shape (n_features,).

        Raises
        ------
        NotImplementedError
            Always — not yet implemented.
        """
        raise NotImplementedError("Feature extraction not yet implemented")
