"""
Unit tests for Satellite Fetcher and Synthetic Provider.
"""
import os
import numpy as np
from src.satellite.synthetic_provider import SyntheticSatelliteProvider
from src.satellite.fetcher import SatelliteFetcher


def test_synthetic_provider():
    provider = SyntheticSatelliteProvider()
    before, after = provider.generate_pair("road_resurfacing", scenario="ghost_project", image_size=(128, 128))

    assert before.shape == (128, 128, 4)
    assert after.shape == (128, 128, 4)
    assert before.dtype == np.float32
    assert after.dtype == np.float32


def test_satellite_fetcher(tmp_path):
    fetcher = SatelliteFetcher(cache_dir=str(tmp_path))
    res = fetcher.fetch_dual_temporal_imagery(
        tender_id="TEST-TND-01",
        bounding_box=[12.9, 77.6, 12.95, 77.65],
        start_date="2024-01-01",
        completion_date="2024-06-30",
        project_type="park_development",
        scenario_override="genuine_completed"
    )

    assert os.path.exists(res["before_png_path"])
    assert os.path.exists(res["after_png_path"])
    assert os.path.exists(res["before_npy_path"])
    assert os.path.exists(res["after_npy_path"])
