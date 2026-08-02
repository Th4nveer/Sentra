"""
High-Resolution Synthetic Multispectral Satellite Scene Generator.
Generates sub-5m resolution RGB + NIR 4-band multispectral satellite arrays
for testing and offline audit verification.
"""
import numpy as np
from typing import Tuple, Dict, Any


class SyntheticSatelliteProvider:
    """
    Generates realistic 4-band multispectral crops (Red, Green, Blue, NIR)
    for pre-project (Before) and post-project (After) dates.
    """

    def generate_pair(
        self,
        project_type: str,
        scenario: str = "ghost_project",
        image_size: Tuple[int, int] = (256, 256),
        seed: int = 42
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generates (before_image, after_image) as float32 numpy arrays of shape (H, W, 4).
        Bands: [0: Red, 1: Green, 2: Blue, 3: NIR]. Values in [0.0, 1.0].
        """
        np.random.seed(seed)
        h, w = image_size

        # Create base terrain according to project_type
        if project_type == "road_resurfacing":
            before_arr, after_arr = self._generate_road_pair(h, w, scenario)
        elif project_type == "park_development":
            before_arr, after_arr = self._generate_park_pair(h, w, scenario)
        elif project_type == "canal_construction":
            before_arr, after_arr = self._generate_canal_pair(h, w, scenario)
        else:
            before_arr, after_arr = self._generate_building_pair(h, w, scenario)

        return before_arr.astype(np.float32), after_arr.astype(np.float32)

    def _generate_road_pair(self, h: int, w: int, scenario: str) -> Tuple[np.ndarray, np.ndarray]:
        # Pre-project: Soil background + faded cracked gray road (high reflectance, low NIR)
        before = np.zeros((h, w, 4), dtype=np.float32)
        # Background: dry soil / light vegetation
        before[:, :, 0] = 0.45 + np.random.normal(0, 0.03, (h, w))  # Red
        before[:, :, 1] = 0.48 + np.random.normal(0, 0.03, (h, w))  # Green
        before[:, :, 2] = 0.35 + np.random.normal(0, 0.03, (h, w))  # Blue
        before[:, :, 3] = 0.55 + np.random.normal(0, 0.04, (h, w))  # NIR

        # Old faded road corridor down the center (y: 100 to 156)
        road_mask = np.zeros((h, w), dtype=bool)
        road_mask[100:156, :] = True
        before[road_mask, 0] = 0.55 + np.random.normal(0, 0.02, road_mask.sum())
        before[road_mask, 1] = 0.55 + np.random.normal(0, 0.02, road_mask.sum())
        before[road_mask, 2] = 0.52 + np.random.normal(0, 0.02, road_mask.sum())
        before[road_mask, 3] = 0.30 + np.random.normal(0, 0.02, road_mask.sum())

        after = before.copy()

        if scenario == "ghost_project":
            # Zero real change: only minor seasonal lighting variation & noise
            noise = np.random.normal(0, 0.015, (h, w, 4))
            after = np.clip(after + noise, 0.0, 1.0)

        elif scenario == "genuine_completed":
            # Fresh dark asphalt overlay on road corridor (low RGB reflectance, high NDBI signal)
            after[road_mask, 0] = 0.18 + np.random.normal(0, 0.01, road_mask.sum()) # Dark Red
            after[road_mask, 1] = 0.19 + np.random.normal(0, 0.01, road_mask.sum()) # Dark Green
            after[road_mask, 2] = 0.20 + np.random.normal(0, 0.01, road_mask.sum()) # Dark Blue
            after[road_mask, 3] = 0.15 + np.random.normal(0, 0.01, road_mask.sum()) # Low NIR for asphalt
            # Add bright yellow center line paint for high resolution realism
            after[126:130, :, 0] = 0.85
            after[126:130, :, 1] = 0.80
            after[126:130, :, 2] = 0.10

        elif scenario == "partial_work":
            # Only first 25% of road length resurfaced with asphalt
            partial_mask = np.zeros((h, w), dtype=bool)
            partial_mask[100:156, :w//4] = True
            after[partial_mask, 0] = 0.18 + np.random.normal(0, 0.01, partial_mask.sum())
            after[partial_mask, 1] = 0.19 + np.random.normal(0, 0.01, partial_mask.sum())
            after[partial_mask, 2] = 0.20 + np.random.normal(0, 0.01, partial_mask.sum())
            after[partial_mask, 3] = 0.15 + np.random.normal(0, 0.01, partial_mask.sum())

        return np.clip(before, 0.0, 1.0), np.clip(after, 0.0, 1.0)

    def _generate_park_pair(self, h: int, w: int, scenario: str) -> Tuple[np.ndarray, np.ndarray]:
        # Pre-project: Dry barren land (high Red, low NIR)
        before = np.zeros((h, w, 4), dtype=np.float32)
        before[:, :, 0] = 0.50 + np.random.normal(0, 0.03, (h, w)) # Dry red/brown soil
        before[:, :, 1] = 0.42 + np.random.normal(0, 0.03, (h, w))
        before[:, :, 2] = 0.32 + np.random.normal(0, 0.03, (h, w))
        before[:, :, 3] = 0.35 + np.random.normal(0, 0.03, (h, w)) # Low vegetation NIR

        after = before.copy()

        if scenario == "ghost_project":
            noise = np.random.normal(0, 0.015, (h, w, 4))
            after = np.clip(after + noise, 0.0, 1.0)

        elif scenario == "genuine_completed":
            # Lush green turf lawn & trees added (High NIR, High Green, low Red)
            park_mask = np.zeros((h, w), dtype=bool)
            park_mask[30:226, 30:226] = True
            after[park_mask, 0] = 0.15 + np.random.normal(0, 0.02, park_mask.sum())
            after[park_mask, 1] = 0.55 + np.random.normal(0, 0.03, park_mask.sum()) # Green
            after[park_mask, 2] = 0.15 + np.random.normal(0, 0.02, park_mask.sum())
            after[park_mask, 3] = 0.85 + np.random.normal(0, 0.03, park_mask.sum()) # High NIR

        elif scenario == "partial_work":
            # Only top-left patch planted
            park_mask = np.zeros((h, w), dtype=bool)
            park_mask[30:110, 30:110] = True
            after[park_mask, 0] = 0.15 + np.random.normal(0, 0.02, park_mask.sum())
            after[park_mask, 1] = 0.55 + np.random.normal(0, 0.03, park_mask.sum())
            after[park_mask, 2] = 0.15 + np.random.normal(0, 0.02, park_mask.sum())
            after[park_mask, 3] = 0.85 + np.random.normal(0, 0.03, park_mask.sum())

        return np.clip(before, 0.0, 1.0), np.clip(after, 0.0, 1.0)

    def _generate_canal_pair(self, h: int, w: int, scenario: str) -> Tuple[np.ndarray, np.ndarray]:
        # Pre-project: Open field
        before = np.zeros((h, w, 4), dtype=np.float32)
        before[:, :, 0] = 0.40 + np.random.normal(0, 0.02, (h, w))
        before[:, :, 1] = 0.45 + np.random.normal(0, 0.02, (h, w))
        before[:, :, 2] = 0.30 + np.random.normal(0, 0.02, (h, w))
        before[:, :, 3] = 0.50 + np.random.normal(0, 0.03, (h, w))

        after = before.copy()

        if scenario == "ghost_project":
            noise = np.random.normal(0, 0.015, (h, w, 4))
            after = np.clip(after + noise, 0.0, 1.0)

        elif scenario == "genuine_completed":
            # Excavated concrete lining + water stream (High NDWI, smooth concrete borders)
            canal_mask = np.zeros((h, w), dtype=bool)
            canal_mask[:, 115:141] = True # Concrete banks & water channel
            after[canal_mask, 0] = 0.20 + np.random.normal(0, 0.01, canal_mask.sum())
            after[canal_mask, 1] = 0.35 + np.random.normal(0, 0.01, canal_mask.sum())
            after[canal_mask, 2] = 0.50 + np.random.normal(0, 0.02, canal_mask.sum()) # Water/Concrete Blue
            after[canal_mask, 3] = 0.10 + np.random.normal(0, 0.01, canal_mask.sum()) # Low NIR for water

        elif scenario == "partial_work":
            canal_mask = np.zeros((h, w), dtype=bool)
            canal_mask[:w//3, 115:141] = True
            after[canal_mask, 0] = 0.20 + np.random.normal(0, 0.01, canal_mask.sum())
            after[canal_mask, 1] = 0.35 + np.random.normal(0, 0.01, canal_mask.sum())
            after[canal_mask, 2] = 0.50 + np.random.normal(0, 0.02, canal_mask.sum())
            after[canal_mask, 3] = 0.10 + np.random.normal(0, 0.01, canal_mask.sum())

        return np.clip(before, 0.0, 1.0), np.clip(after, 0.0, 1.0)

    def _generate_building_pair(self, h: int, w: int, scenario: str) -> Tuple[np.ndarray, np.ndarray]:
        # Pre-project: Vacant plot
        before = np.zeros((h, w, 4), dtype=np.float32)
        before[:, :, 0] = 0.48 + np.random.normal(0, 0.03, (h, w))
        before[:, :, 1] = 0.44 + np.random.normal(0, 0.03, (h, w))
        before[:, :, 2] = 0.35 + np.random.normal(0, 0.03, (h, w))
        before[:, :, 3] = 0.42 + np.random.normal(0, 0.03, (h, w))

        after = before.copy()

        if scenario == "ghost_project":
            noise = np.random.normal(0, 0.015, (h, w, 4))
            after = np.clip(after + noise, 0.0, 1.0)

        elif scenario == "genuine_completed":
            # New bright concrete roof structure (High RGB reflectance, sharp edges)
            building_mask = np.zeros((h, w), dtype=bool)
            building_mask[60:196, 60:196] = True
            after[building_mask, 0] = 0.85 + np.random.normal(0, 0.01, building_mask.sum()) # Bright roof
            after[building_mask, 1] = 0.85 + np.random.normal(0, 0.01, building_mask.sum())
            after[building_mask, 2] = 0.88 + np.random.normal(0, 0.01, building_mask.sum())
            after[building_mask, 3] = 0.25 + np.random.normal(0, 0.01, building_mask.sum())

        elif scenario == "partial_work":
            # Concrete foundation slab only
            building_mask = np.zeros((h, w), dtype=bool)
            building_mask[60:120, 60:196] = True
            after[building_mask, 0] = 0.65 + np.random.normal(0, 0.01, building_mask.sum())
            after[building_mask, 1] = 0.65 + np.random.normal(0, 0.01, building_mask.sum())
            after[building_mask, 2] = 0.68 + np.random.normal(0, 0.01, building_mask.sum())
            after[building_mask, 3] = 0.30 + np.random.normal(0, 0.01, building_mask.sum())

        return np.clip(before, 0.0, 1.0), np.clip(after, 0.0, 1.0)
