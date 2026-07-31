"""
Spectral Index Calculator for Satellite Remote Sensing.
Computes NDVI, NDBI, NDWI, and differential index heatmaps.
"""
import numpy as np
from typing import Dict, Tuple


class SpectralIndexCalculator:
    """
    Computes spectral indices on 4-band satellite arrays [Red, Green, Blue, NIR].
    """

    @staticmethod
    def compute_ndvi(array: np.ndarray) -> np.ndarray:
        """
        Normalized Difference Vegetation Index = (NIR - Red) / (NIR + Red)
        """
        red = array[:, :, 0]
        nir = array[:, :, 3]
        denom = np.maximum(nir + red, 1e-6)
        ndvi = (nir - red) / denom
        return np.clip(ndvi, -1.0, 1.0)

    @staticmethod
    def compute_ndbi(array: np.ndarray) -> np.ndarray:
        """
        Normalized Difference Built-up Index = (Red - NIR) / (Red + NIR)
        High values indicate paved asphalt, concrete, or bare built surface.
        """
        red = array[:, :, 0]
        nir = array[:, :, 3]
        denom = np.maximum(red + nir, 1e-6)
        ndbi = (red - nir) / denom
        return np.clip(ndbi, -1.0, 1.0)

    @staticmethod
    def compute_ndwi(array: np.ndarray) -> np.ndarray:
        """
        Normalized Difference Water Index = (Green - NIR) / (Green + NIR)
        """
        green = array[:, :, 1]
        nir = array[:, :, 3]
        denom = np.maximum(green + nir, 1e-6)
        ndwi = (green - nir) / denom
        return np.clip(ndwi, -1.0, 1.0)

    def compute_differential_indices(
        self,
        before_arr: np.ndarray,
        after_arr: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """
        Computes delta index heatmaps (After - Before).
        """
        before_ndvi = self.compute_ndvi(before_arr)
        after_ndvi = self.compute_ndvi(after_arr)
        delta_ndvi = after_ndvi - before_ndvi

        before_ndbi = self.compute_ndbi(before_arr)
        after_ndbi = self.compute_ndbi(after_arr)
        delta_ndbi = after_ndbi - before_ndbi

        before_ndwi = self.compute_ndwi(before_arr)
        after_ndwi = self.compute_ndwi(after_arr)
        delta_ndwi = after_ndwi - before_ndwi

        # Overall spectral magnitude shift across all 4 bands
        spectral_shift = np.sqrt(np.sum((after_arr - before_arr) ** 2, axis=2))

        return {
            "before_ndvi": before_ndvi,
            "after_ndvi": after_ndvi,
            "delta_ndvi": delta_ndvi,
            "before_ndbi": before_ndbi,
            "after_ndbi": after_ndbi,
            "delta_ndbi": delta_ndbi,
            "before_ndwi": before_ndwi,
            "after_ndwi": after_ndwi,
            "delta_ndwi": delta_ndwi,
            "spectral_shift": spectral_shift
        }
