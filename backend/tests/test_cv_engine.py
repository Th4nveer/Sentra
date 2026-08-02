"""
Unit tests for Computer Vision and Spectral Analysis Engine.
"""
import numpy as np
from src.cv_engine.spectral import SpectralIndexCalculator
from src.cv_engine.detector import ChangeDetectionPipeline


def test_spectral_indices():
    arr = np.zeros((64, 64, 4), dtype=np.float32)
    arr[:, :, 0] = 0.2 # Red
    arr[:, :, 3] = 0.8 # NIR

    calc = SpectralIndexCalculator()
    ndvi = calc.compute_ndvi(arr)
    ndbi = calc.compute_ndbi(arr)

    # NDVI = (0.8 - 0.2) / (0.8 + 0.2) = 0.6
    assert np.allclose(ndvi, 0.6, atol=0.01)
    # NDBI = (0.2 - 0.8) / (0.2 + 0.8) = -0.6
    assert np.allclose(ndbi, -0.6, atol=0.01)


def test_ghost_project_detection():
    detector = ChangeDetectionPipeline()
    arr_before = np.random.rand(128, 128, 4).astype(np.float32)
    # Identical array -> zero real change
    arr_after = arr_before.copy()

    audit = detector.analyze_change("TEST-GHOST", "road_resurfacing", 45000000.0, arr_before, arr_after)

    assert audit.classification == "PRIORITY_FIELD_VERIFICATION_RECOMMENDED"
    assert audit.fraud_risk_score >= 75.0
    assert audit.physical_alteration_score < 15.0
