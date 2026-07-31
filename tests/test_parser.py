"""
Unit tests for TenderParser and Geocoder modules.
"""
from src.parser.tender_parser import TenderParser
from src.parser.geocoder import Geocoder


def test_tender_parser_rules():
    sample_text = """
    TENDER REF: TND-2024-BLR-0912
    Project Title: Resurfacing of Ward 12 Main Connector Road
    Department: BBMP
    Sanctioned Budget: Rs 4,50,00,000
    Work Commencement Date: 2024-01-15
    Stipulated Completion Date: 2024-06-30
    Site Location: Ward 12 Main Connector Road, Bellandur, Bengaluru
    """
    parser = TenderParser()
    tender = parser.parse_text(sample_text)

    assert tender.tender_id == "TND-2024-BLR-0912"
    assert "Resurfacing" in tender.project_name
    assert tender.budget_inr == 45000000.0
    assert tender.start_date == "2024-01-15"
    assert tender.completion_date == "2024-06-30"
    assert tender.project_type == "road_resurfacing"


def test_geocoder():
    geocoder = Geocoder()
    res = geocoder.geocode("Ward 12 Main Connector Road, Bellandur, Bengaluru")

    assert res.latitude == 12.9333
    assert res.longitude == 77.6637
    assert len(res.bounding_box) == 4
    assert res.bounding_box[0] < res.bounding_box[2]
    assert res.bounding_box[1] < res.bounding_box[3]
