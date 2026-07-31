"""
Unit tests for Evidence Card and Triage Dashboard generators.
"""
import os
import numpy as np
from src.parser.models import TenderData, GeocodingResult
from src.cv_engine.detector import AuditResult
from src.report.evidence_card import EvidenceCardGenerator
from src.report.triage_dashboard import TriageDashboardGenerator


def test_evidence_card_generation(tmp_path):
    tender = TenderData(
        tender_id="TND-REPORT-01",
        project_name="Road Resurfacing Test",
        department="BBMP",
        project_type="road_resurfacing",
        budget_inr=45000000.0,
        start_date="2024-01-01",
        completion_date="2024-06-30",
        location_text="Ward 12 Bengaluru"
    )
    geocoding = GeocodingResult(
        latitude=12.9352,
        longitude=77.6245,
        bounding_box=[12.93, 77.60, 12.94, 77.64],
        confidence=0.9,
        formatted_address="Ward 12 Bellandur Bengaluru"
    )
    audit = AuditResult(
        tender_id="TND-REPORT-01",
        project_type="road_resurfacing",
        physical_alteration_score=2.0,
        fraud_risk_score=98.0,
        classification="PRIORITY_FIELD_VERIFICATION_RECOMMENDED",
        hedged_verdict_copy="Low physical change detected — recommend priority field verification.",
        ssim_score=0.99,
        spectral_shift_mean=0.01,
        delta_ndvi_mean=0.0,
        delta_ndbi_mean=0.0,
        audit_summary="Ghost project alert"
    )

    before_arr = np.random.rand(64, 64, 4).astype(np.float32)
    after_arr = before_arr.copy()

    # Save mock PNGs
    before_png = os.path.join(tmp_path, "before.png")
    after_png = os.path.join(tmp_path, "after.png")
    from PIL import Image
    Image.fromarray((before_arr[:, :, :3] * 255).astype(np.uint8)).save(before_png)
    Image.fromarray((after_arr[:, :, :3] * 255).astype(np.uint8)).save(after_png)

    sat_data = {
        "before_png_path": before_png,
        "after_png_path": after_png,
        "before_array": before_arr,
        "after_array": after_arr
    }

    card_gen = EvidenceCardGenerator(output_dir=str(tmp_path))
    res = card_gen.generate_card(tender, geocoding, sat_data, audit)

    assert os.path.exists(res["card_html_path"])
    assert os.path.exists(res["heatmap_png_path"])
    assert len(res["audit_hash"]) == 64 # SHA-256 length
