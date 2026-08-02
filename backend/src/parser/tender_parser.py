"""
Tender & Work Order Parser using LLM (Groq) with deterministic regex fallback.
"""
import os
import re
import json
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from src.parser.models import TenderData

load_dotenv()


class TenderParser:
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")

    def parse_text(self, text: str) -> TenderData:
        """
        Parses raw tender circular text into structured TenderData model.
        Attempts Groq LLM API if key is present, otherwise falls back to deterministic regex.
        """
        if self.api_key and self.api_key.strip():
            try:
                return self._parse_with_groq(text)
            except Exception as e:
                print(f"[TenderParser] Groq API call failed: {e}. Falling back to rule parser.")
                return self._parse_with_rules(text)
        else:
            print("[TenderParser] No GROQ_API_KEY set. Using regex fallback parser.")
            return self._parse_with_rules(text)

    def _parse_with_groq(self, text: str) -> TenderData:
        from groq import Groq

        client = Groq(api_key=self.api_key)

        prompt = f"""Extract the following structured parameters from this government tender document / work order.
If exact dates are not stated, infer approximate dates from context clues (e.g., fiscal year mentions, season references, "6 months from date of order", etc.).
If a location is mentioned but no coordinates, extract the most specific location text possible (street, ward, area, city, state, pincode).

Return ONLY valid JSON matching this exact schema (no markdown, no explanation):
{{
    "tender_id": "string — tender reference number or work order ID",
    "project_name": "string — name or title of the infrastructure project",
    "department": "string — issuing government body or municipal corporation",
    "project_type": "road_resurfacing | park_development | canal_construction | building | land_clearing | bridge | water_supply | sewerage",
    "budget_inr": number — total sanctioned budget in INR (convert lakhs/crores to raw number),
    "start_date": "YYYY-MM-DD — work commencement date (approximate if not exact)",
    "completion_date": "YYYY-MM-DD — reported or stipulated completion date (approximate if not exact)",
    "contractor_name": "string — awarded contractor name or 'Unknown'",
    "location_text": "string — most specific location description from the document",
    "expected_alteration_type": "asphalt_laying | vegetation_clearing | excavation | building_construction | pipe_laying | bridge_construction"
}}

Tender Document Text:
\"\"\"
{text[:6000]}
\"\"\"
"""
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise data extraction assistant for Indian government tender documents. Extract structured fields and return only valid JSON. Always infer approximate dates if exact ones aren't available."
                },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.1,
            max_tokens=1024,
        )

        raw_content = response.choices[0].message.content.strip()

        # Clean potential markdown formatting
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:]
        if raw_content.startswith("```"):
            raw_content = raw_content[3:]
        if raw_content.endswith("```"):
            raw_content = raw_content[:-3]

        data = json.loads(raw_content.strip())

        # Ensure budget_inr is a number
        if isinstance(data.get("budget_inr"), str):
            data["budget_inr"] = float(re.sub(r'[^\d.]', '', data["budget_inr"]) or "0")

        return TenderData(**data)

    def _parse_with_rules(self, text: str) -> TenderData:
        """
        Deterministic regex and rule-based parser for offline/fallback operation.
        """
        # Tender ID
        id_match = re.search(r'(TND-[A-Z0-9\-]+|WO-[A-Z0-9\-]+|REF[:\s]+[A-Z0-9\-]+)', text, re.IGNORECASE)
        tender_id = id_match.group(1).replace("REF:", "").strip() if id_match else "TND-2024-DEF-001"

        # Budget
        budget_match = re.search(r'(?:Budget|Sanctioned|Cost|Amount)[:\s]+(?:Rs\.?|INR|₹)?\s*([0-9,]+(?:\.[0-9]+)?)', text, re.IGNORECASE)
        if budget_match:
            raw_b = budget_match.group(1).replace(",", "")
            try:
                budget_inr = float(raw_b)
                if budget_inr < 1000 and "lakh" in text.lower():
                    budget_inr *= 100000
                elif budget_inr < 1000 and "crore" in text.lower():
                    budget_inr *= 10000000
            except ValueError:
                budget_inr = 25000000.0
        else:
            budget_inr = 25000000.0

        # Dates
        dates = re.findall(r'\b(202[3-6]-\d{2}-\d{2})\b', text)
        if len(dates) >= 2:
            start_date, completion_date = dates[0], dates[1]
        elif len(dates) == 1:
            start_date, completion_date = dates[0], "2024-12-31"
        else:
            # Try DD/MM/YYYY or DD-MM-YYYY format
            alt_dates = re.findall(r'\b(\d{2}[/-]\d{2}[/-]202[3-6])\b', text)
            if len(alt_dates) >= 2:
                start_date = self._normalize_date(alt_dates[0])
                completion_date = self._normalize_date(alt_dates[1])
            elif len(alt_dates) == 1:
                start_date = self._normalize_date(alt_dates[0])
                completion_date = "2024-12-31"
            else:
                start_date, completion_date = "2024-01-01", "2024-06-30"

        # Department
        dept_match = re.search(r'(Department|Corporation|Authority|BBMP|CPWD|PWD)[:\s]+([^\n\.,]+)', text, re.IGNORECASE)
        department = dept_match.group(0).strip() if dept_match else "Municipal Public Works Department"

        # Project Name & Type
        text_lower = text.lower()
        if "road" in text_lower or "resurfac" in text_lower or "asphalt" in text_lower or "paving" in text_lower:
            project_type = "road_resurfacing"
            expected_alteration = "asphalt_laying"
            default_name = "Road Resurfacing and Asphalt Paving Project"
        elif "park" in text_lower or "greenery" in text_lower or "plantation" in text_lower:
            project_type = "park_development"
            expected_alteration = "vegetation_clearing"
            default_name = "Civic Park Development and Landscaping"
        elif "drain" in text_lower or "canal" in text_lower or "stormwater" in text_lower:
            project_type = "canal_construction"
            expected_alteration = "excavation"
            default_name = "Stormwater Drainage Canal Construction"
        elif "building" in text_lower or "community hall" in text_lower or "center" in text_lower:
            project_type = "building"
            expected_alteration = "building_construction"
            default_name = "Civic Community Center Construction"
        elif "bridge" in text_lower or "flyover" in text_lower:
            project_type = "bridge"
            expected_alteration = "bridge_construction"
            default_name = "Bridge / Flyover Construction"
        elif "water" in text_lower or "pipeline" in text_lower or "sewerage" in text_lower:
            project_type = "water_supply"
            expected_alteration = "pipe_laying"
            default_name = "Water Supply / Sewerage Pipeline"
        else:
            project_type = "road_resurfacing"
            expected_alteration = "asphalt_laying"
            default_name = "Infrastructure Maintenance Project"

        proj_name_match = re.search(r'(?:Project Title|Project Name|Title)[:\s]+([^\n\.]+)', text, re.IGNORECASE)
        if not proj_name_match:
            proj_name_match = re.search(r'(?:Work Order|Work)[:\s]+([^\n\.]+)', text, re.IGNORECASE)
        project_name = proj_name_match.group(1).strip() if proj_name_match else default_name

        # Contractor
        contractor_match = re.search(r'(?:Contractor|Awarded to|Vendor)[:\s]+([^\n\.,]+)', text, re.IGNORECASE)
        contractor = contractor_match.group(1).strip() if contractor_match else "Unknown Contractor"

        # Location text extraction using multi-pattern heuristic
        location_text = self._extract_location_from_text(text)

        return TenderData(
            tender_id=tender_id,
            project_name=project_name,
            department=department,
            project_type=project_type,
            budget_inr=budget_inr,
            start_date=start_date,
            completion_date=completion_date,
            contractor_name=contractor,
            location_text=location_text,
            expected_alteration_type=expected_alteration
        )

    def _extract_location_from_text(self, text: str) -> str:
        """Extracts the cleanest location description from document text without header clutter."""
        # 1. Search for explicit Location / Site / Address / Ward labels
        loc_match = re.search(r'(?:Location|Site|Ward|Address|Place|Stretch)[:\s]+([^\n\.;]+)', text, re.IGNORECASE)
        if loc_match:
            cand = loc_match.group(1).strip()
            if len(cand) >= 5 and not cand.lower().startswith("of"):
                return cand

        # 2. Search for Highway / Stretch / Landmark mentions (e.g. NH 16, Puintola to Tangi, Silk Board, etc.)
        highway_match = re.search(r'\b(NH[- ]?\d+|National Highway \d+|[A-Z][a-z]+ to [A-Z][a-z]+|Ward \d+|Sector \d+)\b[^\n\.;]*', text)
        if highway_match:
            return highway_match.group(0).strip()

        # 3. Search for City / State / Pincode mentions
        city_state_match = re.search(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*,\s*([A-Z][a-z]+|\d{6})\b', text)
        if city_state_match:
            return city_state_match.group(0).strip()

        # 4. Search for known city landmarks in text
        known_cities = ["Bengaluru", "Bangalore", "Odisha", "Mumbai", "Noida", "Delhi", "Hyderabad", "Chennai", "Kolkata", "Pune"]
        for city in known_cities:
            if city.lower() in text.lower():
                # Extract sentence containing city
                lines = [line.strip() for line in text.split('\n') if city.lower() in line.lower()]
                if lines:
                    return lines[0][:100]

        return "Bellandur Lake, Bengaluru, Karnataka"

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """Convert DD/MM/YYYY or DD-MM-YYYY to YYYY-MM-DD."""
        parts = re.split(r'[/-]', date_str)
        if len(parts) == 3 and len(parts[2]) == 4:
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
        return date_str
