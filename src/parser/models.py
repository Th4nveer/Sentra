"""
Sentra Data Models for Tender Parsing & Geocoding.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class TenderData(BaseModel):
    tender_id: str = Field(description="Unique tender or work order ID")
    project_name: str = Field(description="Name or title of the infrastructure project")
    department: str = Field(description="Issuing government body or municipal corporation")
    project_type: str = Field(
        description="Type of work: 'road_resurfacing', 'park_development', 'canal_construction', 'building', 'land_clearing'"
    )
    budget_inr: float = Field(description="Total sanctioned budget in INR")
    start_date: str = Field(description="Sanctioned work start date (YYYY-MM-DD)")
    completion_date: str = Field(description="Reported completion date (YYYY-MM-DD)")
    contractor_name: Optional[str] = Field(default="Unknown Contractor", description="Awarded contractor name")
    location_text: str = Field(description="Vague or detailed location description from tender circular")
    expected_alteration_type: str = Field(
        default="asphalt_laying",
        description="Expected physical change: 'asphalt_laying', 'vegetation_clearing', 'excavation', 'building_construction'"
    )


class GeocodingResult(BaseModel):
    latitude: float = Field(description="Center latitude")
    longitude: float = Field(description="Center longitude")
    bounding_box: List[float] = Field(
        description="Bounding box [min_lat, min_lon, max_lat, max_lon] covering ROI"
    )
    confidence: float = Field(default=0.9, description="Confidence score of geocoding (0.0 to 1.0)")
    formatted_address: str = Field(description="Normalized geocoded address")
    geocoding_source: str = Field(default="nominatim", description="Source: 'nominatim', 'local_registry', 'llm'")
