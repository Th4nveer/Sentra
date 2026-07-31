"""
Community Report Model for citizen-submitted infrastructure work reports.
Converts user-submitted location pins + descriptions into TenderData objects
that flow through the existing Sentra satellite audit pipeline.
"""
import hashlib
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field

from src.parser.models import TenderData


class CommunityReport(BaseModel):
    title: str = Field(description="Short title of the reported infrastructure work")
    description: Optional[str] = Field(default="", description="Optional detailed description of the work")
    latitude: float = Field(description="Latitude from the map pin placement")
    longitude: float = Field(description="Longitude from the map pin placement")
    estimated_start_date: Optional[str] = Field(
        default=None,
        description="User-provided estimated start date (YYYY-MM-DD). Falls back to submission_date if not provided."
    )
    submission_date: str = Field(
        default_factory=lambda: date.today().isoformat(),
        description="Date the report was submitted (auto-filled)"
    )

    def generate_report_id(self) -> str:
        """Generates a unique CR-XXXXXXXX ID from a hash of the report details."""
        raw = f"{self.title}|{self.latitude}|{self.longitude}|{self.submission_date}"
        hash_hex = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8].upper()
        return f"CR-{hash_hex}"

    def get_start_date(self) -> str:
        """Returns the effective start date: estimated_start_date if provided, else submission_date."""
        if self.estimated_start_date:
            # Validate the date format
            try:
                datetime.strptime(self.estimated_start_date, "%Y-%m-%d")
                return self.estimated_start_date
            except ValueError:
                pass
        return self.submission_date

    def get_completion_date(self) -> str:
        """Returns today's date as the completion date (check progress up to now)."""
        return date.today().isoformat()

    def to_tender_data(self) -> TenderData:
        """
        Converts this community report into a TenderData object so it flows
        through the existing Sentra audit pipeline unchanged.
        """
        report_id = self.generate_report_id()
        location_text = f"{self.latitude}, {self.longitude}"

        return TenderData(
            tender_id=report_id,
            project_name=self.title,
            department="Community Report",
            project_type="general",
            budget_inr=0.0,
            start_date=self.get_start_date(),
            completion_date=self.get_completion_date(),
            contractor_name="Reported by Citizen",
            location_text=location_text,
            expected_alteration_type="general_surface_change"
        )
