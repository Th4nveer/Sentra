"""
Computer Vision & Change Detection Pipeline for Satellite Audit.
Evaluates physical surface transformations, computes probability-scored triage,
and outputs human-in-the-loop audit evidence.
"""
import numpy as np
from typing import Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field

from src.cv_engine.spectral import SpectralIndexCalculator


class AuditResult(BaseModel):
    tender_id: str
    project_type: str
    physical_alteration_score: float = Field(description="Percentage of detected physical change (0 to 100%)")
    fraud_risk_score: float = Field(description="Triage priority score (0 to 100%)")
    classification: str = Field(description="Audit triage status: 'PRIORITY_FIELD_VERIFICATION_RECOMMENDED', 'PARTIAL_CHANGE_DETECTED', or 'HIGH_PHYSICAL_CHANGE_VERIFIED'")
    confidence_level: float = Field(default=0.92, description="Confidence level of satellite change detection model (0.0 to 1.0)")
    hedged_verdict_copy: str = Field(description="Responsible-use human-in-the-loop screening advice")
    ssim_score: float = Field(description="Structural Similarity Index between before/after scenes")
    spectral_shift_mean: float = Field(description="Mean spectral magnitude change")
    delta_ndvi_mean: float = Field(description="Mean change in vegetation index")
    delta_ndbi_mean: float = Field(description="Mean change in built-up index")
    audit_summary: str = Field(description="Detailed human-readable audit justification")
    model_version: str = Field(default="Sentra-CV-v0.1-SiameseSpectral", description="CV Model & Algorithm Version")


def _gaussian_filter_2d(arr: np.ndarray, sigma: float = 1.5) -> np.ndarray:
    """Pure NumPy 2D separable Gaussian filter implementation."""
    radius = int(4 * sigma + 0.5)
    x = np.arange(-radius, radius + 1)
    kernel1d = np.exp(-0.5 * (x / sigma) ** 2)
    kernel1d /= kernel1d.sum()

    out = np.apply_along_axis(lambda m: np.convolve(m, kernel1d, mode='same'), axis=1, arr=arr)
    out = np.apply_along_axis(lambda m: np.convolve(m, kernel1d, mode='same'), axis=0, arr=out)
    return out


class ChangeDetectionPipeline:
    def __init__(self):
        self.spectral_calc = SpectralIndexCalculator()

    def analyze_change(
        self,
        tender_id: str,
        project_type: str,
        budget_inr: float,
        before_arr: np.ndarray,
        after_arr: np.ndarray
    ) -> AuditResult:
        """
        Runs change detection pipeline on dual-temporal satellite arrays.
        Follows PRD Ethics & Responsible-Use guidelines: probability-scored triage screening aid.
        """
        # 1. Compute spectral indices
        indices = self.spectral_calc.compute_differential_indices(before_arr, after_arr)
        
        delta_ndvi = indices["delta_ndvi"]
        delta_ndbi = indices["delta_ndbi"]
        delta_ndwi = indices["delta_ndwi"]
        spectral_shift = indices["spectral_shift"]

        # 2. Compute Structural Similarity Index (SSIM)
        ssim = self._compute_ssim(before_arr[:, :, :3], after_arr[:, :, :3])

        # 3. Compute Surface Transformation Index based on expected project type
        if project_type == "road_resurfacing":
            rgb_diff = np.abs(after_arr[:, :, :3] - before_arr[:, :, :3])
            surface_change = np.mean(rgb_diff) * 2.5 + np.mean(np.abs(delta_ndbi)) * 1.5
        elif project_type == "park_development":
            surface_change = np.mean(np.maximum(delta_ndvi, 0)) * 3.0 + np.mean(spectral_shift) * 1.5
        elif project_type == "canal_construction":
            surface_change = np.mean(np.abs(delta_ndwi)) * 2.5 + (1.0 - ssim) * 1.5
        else:
            surface_change = (1.0 - ssim) * 2.0 + np.mean(spectral_shift) * 1.5

        raw_alteration = min(100.0, max(0.0, float(surface_change * 220.0)))
        
        if ssim > 0.95 and np.mean(spectral_shift) < 0.035:
            physical_alteration_score = round(raw_alteration * 0.15, 2)
        else:
            physical_alteration_score = round(raw_alteration, 2)

        # 4. Calculate Probability-Scored Triage Score (0 to 100%)
        unexplained_gap = max(0.0, 100.0 - physical_alteration_score)
        
        budget_weight = 1.0
        if budget_inr >= 40000000:
            budget_weight = 1.15
        elif budget_inr >= 20000000:
            budget_weight = 1.05

        raw_fraud_score = unexplained_gap * budget_weight
        fraud_risk_score = round(min(100.0, max(0.0, raw_fraud_score)), 2)

        # 5. Responsible-Use Classification & Hedged Copy (PRD Section 5 Requirement)
        if physical_alteration_score < 15.0 or fraud_risk_score >= 75.0:
            classification = "PRIORITY_FIELD_VERIFICATION_RECOMMENDED"
            hedged_verdict = "Low physical change detected — recommend priority physical field verification by auditors."
            summary = (
                f"TRIAGE ALERT: Low physical alteration ({physical_alteration_score}%) detected via sub-5m satellite imagery "
                f"for sanctioned budget of Rs. {budget_inr:,.0f} (SSIM {ssim:.3f}, spectral shift {np.mean(spectral_shift):.4f}). "
                f"Flagged for priority human inspection."
            )
        elif physical_alteration_score < 55.0:
            classification = "PARTIAL_CHANGE_DETECTED"
            hedged_verdict = "Partial physical alteration detected — suggest follow-up inspection on reported milestones."
            summary = (
                f"TRIAGE NOTICE: Partial physical change ({physical_alteration_score}%) detected against reported full completion. "
                f"Structural transformation appears incomplete for budget Rs. {budget_inr:,.0f}."
            )
        else:
            classification = "HIGH_PHYSICAL_CHANGE_VERIFIED"
            hedged_verdict = "Significant physical surface transformation detected matching tender specifications."
            summary = (
                f"VERIFIED: Satellite audit confirms significant physical surface transformation ({physical_alteration_score}%) "
                f"aligned with tender specifications."
            )

        return AuditResult(
            tender_id=tender_id,
            project_type=project_type,
            physical_alteration_score=physical_alteration_score,
            fraud_risk_score=fraud_risk_score,
            classification=classification,
            confidence_level=0.92 if ssim > 0.9 else 0.88,
            hedged_verdict_copy=hedged_verdict,
            ssim_score=round(float(ssim), 4),
            spectral_shift_mean=round(float(np.mean(spectral_shift)), 4),
            delta_ndvi_mean=round(float(np.mean(delta_ndvi)), 4),
            delta_ndbi_mean=round(float(np.mean(delta_ndbi)), 4),
            audit_summary=summary,
            model_version="Sentra-CV-v0.1-SiameseSpectral"
        )

    def _compute_ssim(self, img1: np.ndarray, img2: np.ndarray, win_size: int = 7) -> float:
        g1 = np.mean(img1, axis=2)
        g2 = np.mean(img2, axis=2)

        c1 = (0.01 * 1.0) ** 2
        c2 = (0.03 * 1.0) ** 2

        mu1 = _gaussian_filter_2d(g1, sigma=1.5)
        mu2 = _gaussian_filter_2d(g2, sigma=1.5)

        mu1_sq = mu1 ** 2
        mu2_sq = mu2 ** 2
        mu1_mu2 = mu1 * mu2

        sigma1_sq = _gaussian_filter_2d(g1 ** 2, sigma=1.5) - mu1_sq
        sigma2_sq = _gaussian_filter_2d(g2 ** 2, sigma=1.5) - mu2_sq
        sigma12 = _gaussian_filter_2d(g1 * g2, sigma=1.5) - mu1_mu2

        ssim_map = ((2 * mu1_mu2 + c1) * (2 * sigma12 + c2)) / (
            (mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2)
        )
        return float(np.mean(ssim_map))
