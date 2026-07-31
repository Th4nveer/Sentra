"""
JSON Persistence Store for Audited Tender Records.
Ensures audited projects persist across CLI runs, web server restarts, and scans.
"""
import os
import json
from typing import List, Dict, Any

from src.parser.models import TenderData, GeocodingResult
from src.cv_engine.detector import AuditResult

DB_FILE_PATH = "./data/audited_records.json"


def save_record(record: Dict[str, Any]) -> None:
    """
    Saves or updates an audited record in ./data/audited_records.json.
    """
    os.makedirs(os.path.dirname(DB_FILE_PATH), exist_ok=True)
    existing_records = _read_raw_db()

    tender = record["tender"]
    tender_id = tender.tender_id if hasattr(tender, "tender_id") else tender.get("tender_id")

    serialized = {
        "tender": tender.model_dump() if hasattr(tender, "model_dump") else tender,
        "geocoding": record["geocoding"].model_dump() if hasattr(record["geocoding"], "model_dump") else record["geocoding"],
        "audit": record["audit"].model_dump() if hasattr(record["audit"], "model_dump") else record["audit"],
        "card_path": record.get("card_path") or record.get("card_info", {}).get("card_html_path", "")
    }

    # Filter out existing record with same tender_id and append updated
    updated = [r for r in existing_records if r.get("tender", {}).get("tender_id") != tender_id]
    updated.append(serialized)

    with open(DB_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2)


def load_all_records() -> List[Dict[str, Any]]:
    """
    Loads all saved records from ./data/audited_records.json and reconstructs Pydantic objects.
    """
    raw_records = _read_raw_db()
    reconstructed = []

    for item in raw_records:
        try:
            t_obj = TenderData(**item["tender"])
            g_obj = GeocodingResult(**item["geocoding"])
            a_obj = AuditResult(**item["audit"])

            reconstructed.append({
                "tender": t_obj,
                "geocoding": g_obj,
                "audit": a_obj,
                "card_path": item.get("card_path", "")
            })
        except Exception as e:
            print(f"[RecordStore] Failed to reconstruct record: {e}")

    return reconstructed


def _read_raw_db() -> List[Dict[str, Any]]:
    if not os.path.exists(DB_FILE_PATH):
        return []
    try:
        with open(DB_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[RecordStore] Error reading JSON store: {e}")
        return []
