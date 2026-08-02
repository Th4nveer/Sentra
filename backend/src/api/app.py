"""
FastAPI REST API for Sentra AI Satellite Audit Platform.
Serves JSON endpoints and static report assets for the separate frontend.
"""
import os
from typing import Optional, List

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.parser.tender_parser import TenderParser
from src.parser.geocoder import Geocoder
from src.parser.folder_scanner import FolderScanner
from src.parser.community_report import CommunityReport
from src.satellite.fetcher import SatelliteFetcher
from src.cv_engine.detector import ChangeDetectionPipeline
from src.report.evidence_card import EvidenceCardGenerator
from src.report.triage_dashboard import TriageDashboardGenerator
from src.report.record_store import save_record, load_all_records, clear_all_records

app = FastAPI(
    title="Sentra AI Satellite Audit API",
    description="REST API for automated space-borne satellite audit of public infrastructure",
    version="3.0.0",
)

_cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("./data/reports", exist_ok=True)
os.makedirs("./data/raw_tenders", exist_ok=True)
os.makedirs("./data/processed", exist_ok=True)
os.makedirs("./static", exist_ok=True)
app.mount("/reports", StaticFiles(directory="./data/reports", html=True), name="reports")
app.mount("/static", StaticFiles(directory="./static"), name="static")

parser_service = TenderParser()
geocoder_service = Geocoder()
satellite_service = SatelliteFetcher()
cv_pipeline = ChangeDetectionPipeline()
evidence_generator = EvidenceCardGenerator()
dashboard_generator = TriageDashboardGenerator()
folder_scanner = FolderScanner()

VERDICT_LABELS = {
    "PRIORITY_FIELD_VERIFICATION_RECOMMENDED": "Flagged",
    "PARTIAL_CHANGE_DETECTED": "Partial Work",
    "HIGH_PHYSICAL_CHANGE_VERIFIED": "Verified",
}

VERDICT_MESSAGES = {
    "PRIORITY_FIELD_VERIFICATION_RECOMMENDED": "Flagged for Verification",
    "PARTIAL_CHANGE_DETECTED": "Partial Change Detected",
    "HIGH_PHYSICAL_CHANGE_VERIFIED": "Verified — Physical Change Confirmed",
}


class AuditRequest(BaseModel):
    tender_text: str
    scenario_override: Optional[str] = None


class CommunityReportRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    latitude: float
    longitude: float
    estimated_start_date: Optional[str] = None
    estimated_end_date: Optional[str] = None


def _serialize_record(record: dict) -> dict:
    tender = record["tender"]
    audit = record["audit"]
    geocoding = record["geocoding"]
    card_path = record.get("card_path", "")
    tender_id = tender.tender_id

    return {
        "tender_id": tender_id,
        "project_name": tender.project_name,
        "department": tender.department,
        "project_type": tender.project_type,
        "budget_inr": tender.budget_inr,
        "start_date": tender.start_date,
        "completion_date": tender.completion_date,
        "location_text": tender.location_text,
        "source": "citizen" if tender_id.startswith("CR-") else "tender",
        "geocoding": geocoding.model_dump(),
        "audit": audit.model_dump(),
        "verdict_label": VERDICT_LABELS.get(audit.classification, audit.classification.replace("_", " ")),
        "evidence_card_url": f"/reports/{tender_id}/evidence_card.html",
        "card_path": card_path,
    }


def run_full_audit(tender_text: str, scenario_override: Optional[str] = None):
    tender = parser_service.parse_text(tender_text)
    scenario = scenario_override
    geocoding = geocoder_service.geocode(tender.location_text)

    sat_data = satellite_service.fetch_dual_temporal_imagery(
        tender_id=tender.tender_id,
        bounding_box=geocoding.bounding_box,
        start_date=tender.start_date,
        completion_date=tender.completion_date,
        project_type=tender.project_type,
        scenario_override=scenario,
    )

    audit_res = cv_pipeline.analyze_change(
        tender_id=tender.tender_id,
        project_type=tender.project_type,
        budget_inr=tender.budget_inr,
        before_arr=sat_data["before_array"],
        after_arr=sat_data["after_array"],
    )

    card_res = evidence_generator.generate_card(
        tender=tender,
        geocoding=geocoding,
        sat_data=sat_data,
        audit_result=audit_res,
    )

    record = {
        "tender": tender,
        "geocoding": geocoding,
        "audit": audit_res,
        "card_path": card_res["card_html_path"],
    }

    save_record(record)
    all_records = load_all_records()
    dashboard_generator.generate_dashboard(all_records)

    return record, card_res


def run_community_report_audit(report: CommunityReport):
    tender = report.to_tender_data()
    geocoding = geocoder_service.geocode_coordinates(report.latitude, report.longitude)

    sat_data = satellite_service.fetch_dual_temporal_imagery(
        tender_id=tender.tender_id,
        bounding_box=geocoding.bounding_box,
        start_date=tender.start_date,
        completion_date=tender.completion_date,
        project_type=tender.project_type,
    )

    audit_res = cv_pipeline.analyze_change(
        tender_id=tender.tender_id,
        project_type=tender.project_type,
        budget_inr=tender.budget_inr,
        before_arr=sat_data["before_array"],
        after_arr=sat_data["after_array"],
    )

    card_res = evidence_generator.generate_card(
        tender=tender,
        geocoding=geocoding,
        sat_data=sat_data,
        audit_result=audit_res,
    )

    record = {
        "tender": tender,
        "geocoding": geocoding,
        "audit": audit_res,
        "card_path": card_res["card_html_path"],
    }

    save_record(record)
    all_records = load_all_records()
    dashboard_generator.generate_dashboard(all_records)

    return record, card_res


@app.on_event("startup")
def startup_event():
    try:
        existing = load_all_records()
        if not existing:
            sample_files = [
                ("data/sample_tenders/tender_001_ghost_road.txt", "ghost_project"),
                ("data/sample_tenders/tender_002_verified_park.txt", "genuine_completed"),
                ("data/sample_tenders/tender_003_partial_canal.txt", "partial_work"),
            ]
            for filepath, scenario in sample_files:
                if os.path.exists(filepath):
                    with open(filepath, "r", encoding="utf-8") as f:
                        text = f.read()
                    try:
                        run_full_audit(text, scenario)
                    except Exception as e:
                        print(f"[Startup] Error loading sample {filepath}: {e}")
    except Exception as e:
        print(f"[Startup] Error during app startup: {e}")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    for ext in ["ico", "png", "svg", "jpeg", "jpg", "webp"]:
        logo_path = f"./static/logo.{ext}"
        if os.path.exists(logo_path):
            media_type = "image/x-icon" if ext == "ico" else f"image/{ext}"
            return FileResponse(logo_path, media_type=media_type)
    return JSONResponse(status_code=204, content=None)


@app.get("/")
def root():
    return {
        "name": "Sentra AI Satellite Audit API",
        "version": "3.0.0",
        "docs": "/docs",
        "frontend": os.getenv("FRONTEND_URL", "http://localhost:5173"),
    }


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "sentra-api", "version": "3.0.0"}


@app.get("/api/stats")
def get_stats():
    records = load_all_records() or []
    flagged = sum(
        1
        for r in records
        if r["audit"].classification
        in ("PRIORITY_FIELD_VERIFICATION_RECOMMENDED", "PARTIAL_CHANGE_DETECTED")
    )
    verified = sum(
        1 for r in records if r["audit"].classification == "HIGH_PHYSICAL_CHANGE_VERIFIED"
    )
    return {
        "total_audited": len(records),
        "flagged_count": flagged,
        "verified_count": verified,
        "pending_count": folder_scanner.get_pending_count(),
    }


@app.get("/api/records")
def get_records():
    records = load_all_records() or []
    sorted_records = sorted(records, key=lambda x: x["audit"].fraud_risk_score, reverse=True)
    return {"records": [_serialize_record(r) for r in sorted_records]}


@app.post("/api/community/report")
def community_report_endpoint(request: CommunityReportRequest):
    try:
        report = CommunityReport(
            title=request.title,
            description=request.description or "",
            latitude=request.latitude,
            longitude=request.longitude,
            estimated_start_date=request.estimated_start_date,
            estimated_end_date=request.estimated_end_date,
        )

        record, card_res = run_community_report_audit(report)
        audit_res = record["audit"]
        tender = record["tender"]

        return {
            "status": "success",
            "report_id": tender.tender_id,
            "verdict": VERDICT_MESSAGES.get(audit_res.classification, audit_res.classification),
            "classification": audit_res.classification,
            "physical_change": audit_res.physical_alteration_score,
            "evidence_card_url": f"/reports/{tender.tender_id}/evidence_card.html",
            "audit_hash": card_res["audit_hash"],
        }
    except Exception as e:
        print(f"[COMMUNITY REPORT ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/audit/upload-tender")
async def upload_tender_endpoint(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    for file in files:
        if not file.filename:
            continue
        safe_filename = os.path.basename(file.filename)
        target_path = os.path.join("./data/raw_tenders", safe_filename)
        contents = await file.read()
        with open(target_path, "wb") as f:
            f.write(contents)

    processed = 0
    results_list = []
    errors = []

    scan_results = folder_scanner.scan()
    for filepath, text, tender_data in scan_results:
        try:
            record, card_res = run_full_audit(text)
            processed += 1
            results_list.append({
                "tender_id": record["tender"].tender_id,
                "project_name": record["tender"].project_name,
                "verdict": record["audit"].classification,
                "evidence_card_url": f"/reports/{record['tender'].tender_id}/evidence_card.html",
            })
        except Exception as e:
            errors.append(f"{os.path.basename(filepath)}: {str(e)}")

    message = f"Uploaded and audited {processed} document(s) successfully."
    if errors:
        message += f" {len(errors)} error(s): {'; '.join(errors)}"

    return {
        "status": "success",
        "message": message,
        "processed": processed,
        "results": results_list,
        "errors": errors,
    }


@app.post("/api/audit/parse")
def parse_tender_endpoint(request: AuditRequest):
    try:
        tender = parser_service.parse_text(request.tender_text)
        geocoding = geocoder_service.geocode(tender.location_text)
        return {"tender": tender, "geocoding": geocoding}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/audit/run")
def run_audit_endpoint(request: AuditRequest):
    try:
        record, card_res = run_full_audit(request.tender_text, request.scenario_override)
        audit_res = record["audit"]
        tender = record["tender"]

        return {
            "status": "success",
            "tender_id": tender.tender_id,
            "classification": audit_res.classification,
            "fraud_risk_score": audit_res.fraud_risk_score,
            "physical_alteration_score": audit_res.physical_alteration_score,
            "evidence_card_url": f"/reports/{tender.tender_id}/evidence_card.html",
            "dashboard_url": "/reports/index.html",
            "audit_hash": card_res["audit_hash"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/audit/scan-folder")
def scan_folder_endpoint():
    try:
        results = folder_scanner.scan()

        if not results:
            return {
                "status": "success",
                "message": "No new tender documents found in data/raw_tenders/",
                "processed": 0,
            }

        processed = 0
        errors = []

        for filepath, text, tender_data in results:
            try:
                run_full_audit(text)
                processed += 1
            except Exception as e:
                errors.append(f"{os.path.basename(filepath)}: {str(e)}")

        message = f"Processed {processed} tender(s) successfully."
        if errors:
            message += f" {len(errors)} error(s): {'; '.join(errors)}"

        return {
            "status": "success",
            "message": message,
            "processed": processed,
            "errors": errors,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/audit/clear-data")
def clear_data_endpoint():
    try:
        clear_all_records()
        return {"status": "success", "message": "All audited database records cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
