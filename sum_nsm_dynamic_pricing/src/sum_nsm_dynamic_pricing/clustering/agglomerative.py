# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/Codes/map_and_hub_creator_complete_link.py
import numpy as np
from sklearn.cluster import AgglomerativeClustering

from .strategy import ClusteringStrategy


class AgglomClustering(ClusteringStrategy):
    def _cluster(self, coords: np.ndarray) -> np.ndarray:
        model = AgglomerativeClustering(
            n_clusters=None,
            linkage="complete",
            distance_threshold=self.threshold,
            compute_full_tree=True,
        )
        return model.fit_predict(coords)
