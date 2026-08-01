"""
FastAPI Web API Server & Interactive Web Application for Sentra AI Satellite Audit Platform.
"""
import os
from datetime import date, datetime, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
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

app = FastAPI(
    title="Sentra AI Satellite Audit API & Dashboard",
    description="Automated space-borne AI satellite audit platform for public infrastructure",
    version="2.3.0"
)

# Ensure directories exist and mount static files
os.makedirs("./data/reports", exist_ok=True)
os.makedirs("./data/raw_tenders", exist_ok=True)
os.makedirs("./data/processed", exist_ok=True)
os.makedirs("./static", exist_ok=True)
app.mount("/reports", StaticFiles(directory="./data/reports", html=True), name="reports")
app.mount("/static", StaticFiles(directory="./static"), name="static")

# Initialize audit services
parser_service = TenderParser()
geocoder_service = Geocoder()
satellite_service = SatelliteFetcher()
cv_pipeline = ChangeDetectionPipeline()
evidence_generator = EvidenceCardGenerator()
dashboard_generator = TriageDashboardGenerator()
folder_scanner = FolderScanner()

# In-memory store for audited records
AUDITED_RECORDS = []


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    for ext in ["ico", "png", "svg", "jpeg", "jpg", "webp"]:
        logo_path = f"./static/logo.{ext}"
        if os.path.exists(logo_path):
            media_type = "image/x-icon" if ext == "ico" else f"image/{ext}"
            return FileResponse(logo_path, media_type=media_type)
    from fastapi.responses import Response
    return Response(status_code=204)


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


from src.report.record_store import save_record, load_all_records, clear_all_records

def run_full_audit(
    tender_text: str,
    scenario_override: Optional[str] = None
):
    tender = parser_service.parse_text(tender_text)
    scenario = scenario_override
    geocoding = geocoder_service.geocode(tender.location_text)

    sat_data = satellite_service.fetch_dual_temporal_imagery(
        tender_id=tender.tender_id,
        bounding_box=geocoding.bounding_box,
        start_date=tender.start_date,
        completion_date=tender.completion_date,
        project_type=tender.project_type,
        scenario_override=scenario
    )

    audit_res = cv_pipeline.analyze_change(
        tender_id=tender.tender_id,
        project_type=tender.project_type,
        budget_inr=tender.budget_inr,
        before_arr=sat_data["before_array"],
        after_arr=sat_data["after_array"]
    )

    card_res = evidence_generator.generate_card(
        tender=tender,
        geocoding=geocoding,
        sat_data=sat_data,
        audit_result=audit_res
    )

    record = {
        "tender": tender,
        "geocoding": geocoding,
        "audit": audit_res,
        "card_path": card_res["card_html_path"]
    }
    
    save_record(record)

    all_records = load_all_records()
    dashboard_generator.generate_dashboard(all_records)
    
    return record, card_res


def run_community_report_audit(report: CommunityReport):
    """
    Runs the full satellite audit pipeline for a community-submitted report.
    Converts the report into TenderData and uses direct coordinates for geocoding.
    """
    tender = report.to_tender_data()
    geocoding = geocoder_service.geocode_coordinates(report.latitude, report.longitude)

    sat_data = satellite_service.fetch_dual_temporal_imagery(
        tender_id=tender.tender_id,
        bounding_box=geocoding.bounding_box,
        start_date=tender.start_date,
        completion_date=tender.completion_date,
        project_type=tender.project_type
    )

    audit_res = cv_pipeline.analyze_change(
        tender_id=tender.tender_id,
        project_type=tender.project_type,
        budget_inr=tender.budget_inr,
        before_arr=sat_data["before_array"],
        after_arr=sat_data["after_array"]
    )

    card_res = evidence_generator.generate_card(
        tender=tender,
        geocoding=geocoding,
        sat_data=sat_data,
        audit_result=audit_res
    )

    record = {
        "tender": tender,
        "geocoding": geocoding,
        "audit": audit_res,
        "card_path": card_res["card_html_path"]
    }

    save_record(record)

    all_records = load_all_records()
    dashboard_generator.generate_dashboard(all_records)

    return record, card_res


@app.on_event("startup")
def startup_event():
    """Load existing records or pre-load sample tenders on first startup."""
    try:
        existing = load_all_records()
        if not existing:
            sample_files = [
                ("data/sample_tenders/tender_001_ghost_road.txt", "ghost_project"),
                ("data/sample_tenders/tender_002_verified_park.txt", "genuine_completed"),
                ("data/sample_tenders/tender_003_partial_canal.txt", "partial_work")
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


@app.get("/", response_class=HTMLResponse)
def serve_home():
    """
    Renders the EXLM-themed Sentra AI Web Dashboard.
    Light, clean, high-contrast fintech aesthetic with sidebar navigation,
    soft pastel metric cards, interactive map, file upload dropzone, and sleek audit log.
    """
    try:
        audited_records = load_all_records() or []
        total_audited = len(audited_records)
        flagged_count = sum(1 for r in audited_records if r["audit"].classification in [
            "PRIORITY_FIELD_VERIFICATION_RECOMMENDED", "PARTIAL_CHANGE_DETECTED"
        ])
        verified_count = sum(1 for r in audited_records if r["audit"].classification == "HIGH_PHYSICAL_CHANGE_VERIFIED")

        pending_count = folder_scanner.get_pending_count() if folder_scanner else 0

        # Check for custom logo file in ./static/
        logo_html = '<div class="brand-icon" style="width:52px;height:52px;background:#0f172a;color:#fff;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:1.4rem;">S</div>'
        for ext in ["png", "svg", "jpg", "jpeg", "webp"]:
            logo_path = f"./static/logo.{ext}"
            if os.path.exists(logo_path):
                mtime = int(os.path.getmtime(logo_path))
                logo_html = f'<img src="/static/logo.{ext}?v={mtime}" alt="Sentra Logo" class="brand-logo-img" style="height: 68px; width: auto; max-width: 320px; object-fit: contain; border-radius: 8px;" />'
                break

        rows_html = ""
        for r in sorted(audited_records, key=lambda x: x["audit"].fraud_risk_score, reverse=True):
            t = r["tender"]
            a = r["audit"]
            g = r["geocoding"]
            badge_cls = f"badge-{a.classification}"
            
            verdict_map = {
                "PRIORITY_FIELD_VERIFICATION_RECOMMENDED": "Flagged",
                "PARTIAL_CHANGE_DETECTED": "Partial Work",
                "HIGH_PHYSICAL_CHANGE_VERIFIED": "Verified"
            }
            badge_label = verdict_map.get(a.classification, a.classification.replace("_", " "))
            
            location_display = g.formatted_address
            if len(location_display) > 55:
                location_display = location_display[:52] + "..."
            
            source_tag = "👥 Citizen" if t.tender_id.startswith("CR-") else "📄 Tender"

            rows_html += f"""
            <tr>
                <td>
                    <div class="project-name">{t.project_name}</div>
                    <div class="project-meta"><span>{source_tag}</span> · <code>{t.tender_id}</code></div>
                </td>
                <td class="location-cell">{location_display}</td>
                <td><span class="badge {badge_cls}">{badge_label}</span></td>
                <td style="text-align: right;"><a class="btn-card" href="/reports/{t.tender_id}/evidence_card.html" target="_blank">View Card →</a></td>
            </tr>
            """

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SENTRA · Space-Borne Satellite Audit</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        :root {{
            --bg: #f8fafc;
            --sidebar-bg: #ffffff;
            --card-bg: #ffffff;
            --border: #e2e8f0;
            --border-hover: #cbd5e1;
            --text-heading: #0f172a;
            --text-body: #334155;
            --text-muted: #64748b;
            --text-light: #94a3b8;
            --accent-dark: #0f172a;
            --accent-dark-hover: #1e293b;
            --accent-blue: #2563eb;
            --accent-green: #16a34a;
            --accent-red: #dc2626;
            --accent-amber: #d97706;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg);
            color: var(--text-body);
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
            display: flex;
            min-height: 100vh;
          /* ---- Header Navbar ---- */
        .brand-group {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}

        .brand-title {{
            font-size: 1.85rem;
            font-weight: 700;
            letter-spacing: -0.03em;
            color: var(--text-heading);
            line-height: 1.1;
        }}

        .brand-sub {{
            font-size: 0.78rem;
            color: var(--text-muted);
            font-weight: 500;
            margin-top: 2px;
        }}

        .status-badge {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 14px;
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
            border-radius: 9999px;
            font-size: 0.78rem;
            font-weight: 600;
            color: #166534;
        }}

        .status-dot {{
            width: 7px;
            height: 7px;
            background: var(--accent-green);
            border-radius: 50%;
            box-shadow: 0 0 6px rgba(22, 163, 74, 0.4);
        }}

        /* ---- Main Workspace Layout ---- */
        .container {{
            width: 100%;
            max-width: 100%;
            margin: 0;
            padding: 1.5rem 2rem;
        }}

        /* Top Bar Navigation */
        .topbar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1.25rem;
            border-bottom: 1px solid var(--border);
        }}

        .topbar-actions {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}

        /* ---- Metrics Grid ---- */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1.25rem;
            margin-bottom: 2rem;
        }}

        .stat-card {{
            border-radius: 14px;
            padding: 1.35rem 1.5rem;
            border: 1px solid var(--border);
            transition: transform 0.15s ease;
        }}

        .stat-card:hover {{
            transform: translateY(-2px);
        }}

        .stat-card.blue {{ background: #eff6ff; border-color: #dbeafe; }}
        .stat-card.red {{ background: #fff1f2; border-color: #ffe4e6; }}
        .stat-card.green {{ background: #f0fdf4; border-color: #dcfce7; }}

        .stat-label {{
            font-size: 0.74rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 700;
            margin-bottom: 0.4rem;
        }}

        .stat-card.blue .stat-label {{ color: #1e40af; }}
        .stat-card.red .stat-label {{ color: #991b1b; }}
        .stat-card.green .stat-label {{ color: #166534; }}

        .stat-val {{
            font-size: 2.1rem;
            font-weight: 700;
            letter-spacing: -0.03em;
        }}

        .stat-card.blue .stat-val {{ color: #1e3a8a; }}
        .stat-card.red .stat-val {{ color: #881337; }}
        .stat-card.green .stat-val {{ color: #14532d; }}

        /* ---- Main Audit Form Card ---- */
        .card-panel {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.75rem;
            margin-bottom: 2rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
        }}

        .section-title {{
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--text-heading);
            margin-bottom: 1.35rem;
            letter-spacing: -0.01em;
        }}

        .audit-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.75rem;
        }}

        .form-col {{
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }}

        .field-group {{
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
        }}

        .field-group label {{
            font-size: 0.76rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: var(--text-heading);
        }}

        .field-group input[type="text"],
        .field-group input[type="number"],
        .field-group input[type="date"],
        .field-group textarea {{
            width: 100%;
            background: #ffffff;
            border: 1px solid var(--border);
            border-radius: 9px;
            color: var(--text-heading);
            padding: 0.7rem 0.9rem;
            font-family: inherit;
            font-size: 0.88rem;
            transition: all 0.15s ease;
        }}

        .field-group input:focus,
        .field-group textarea:focus {{
            outline: none;
            border-color: var(--accent-dark);
            box-shadow: 0 0 0 3px rgba(15, 23, 42, 0.08);
        }}

        .field-group textarea {{
            resize: vertical;
            min-height: 70px;
        }}

        .inline-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.85rem;
        }}

        .field-hint {{
            font-size: 0.72rem;
            color: var(--text-muted);
            margin-top: 2px;
        }}

        /* Map Container */
        .map-wrap {{
            display: flex;
            flex-direction: column;
            height: 100%;
        }}

        #auditMap {{
            flex: 1;
            min-height: 330px;
            border-radius: 12px;
            border: 1px solid var(--border);
            z-index: 1;
        }}

        .map-caption {{
            font-size: 0.74rem;
            color: var(--text-muted);
            margin-top: 0.5rem;
            text-align: center;
        }}

        /* Buttons */
        .btn-dark {{
            background: var(--accent-dark);
            color: #ffffff;
            border: none;
            padding: 0.85rem 1.5rem;
            border-radius: 10px;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
            margin-top: 0.5rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }}

        .btn-dark:hover {{
            background: var(--accent-dark-hover);
            transform: translateY(-1px);
        }}

        .btn-dark:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }}

        /* ---- Warm Cream Upload Banner ---- */
        .scan-bar {{
            display: flex;
            flex-direction: column;
            padding: 1.35rem 1.6rem;
            background: #fefce8;
            border: 1px dashed #fde047;
            border-radius: 14px;
            margin-bottom: 1.5rem;
            transition: all 0.15s ease;
        }}

        .scan-bar.drag-over {{
            border-color: #ca8a04;
            background: #fef9c3;
        }}

        .scan-left {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}

        .scan-icon {{
            font-size: 1.5rem;
            background: #fef08a;
            padding: 8px 12px;
            border-radius: 10px;
        }}

        .scan-title {{
            font-size: 0.95rem;
            font-weight: 700;
            color: #713f12;
        }}

        .scan-sub {{
            font-size: 0.78rem;
            color: #854d0e;
        }}

        .scan-actions {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .badge-pending {{
            background: #fef08a;
            color: #713f12;
            border: 1px solid #fde047;
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
        }}

        .btn-secondary {{
            background: #ffffff;
            border: 1px solid var(--border);
            color: var(--text-heading);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 0.82rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
        }}

        .btn-secondary:hover {{
            background: #f8fafc;
            border-color: var(--border-hover);
        }}

        .btn-danger {{
            background: transparent;
            border: 1px solid #fecdd3;
            color: var(--accent-red);
            padding: 8px 14px;
            border-radius: 8px;
            font-size: 0.82rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
        }}

        .btn-danger:hover {{
            background: #fff1f2;
        }}

        /* Status banner */
        .status-banner {{
            margin-top: 1rem;
            padding: 0.8rem 1rem;
            border-radius: 9px;
            font-size: 0.84rem;
            display: none;
            font-weight: 500;
        }}
        .status-banner.processing {{ display: block; background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; }}
        .status-banner.success {{ display: block; background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; }}
        .status-banner.error {{ display: block; background: #fff1f2; border: 1px solid #fecdd3; color: #991b1b; }}

        /* ---- Table ---- */
        .table-wrap {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
        }}

        .table-head-bar {{
            padding: 1.25rem 1.6rem;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .table-head-bar h2 {{
            font-size: 1rem;
            font-weight: 700;
            color: var(--text-heading);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }}

        th {{
            background: #f8fafc;
            padding: 0.85rem 1.6rem;
            font-size: 0.72rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 700;
            border-bottom: 1px solid var(--border);
        }}

        td {{
            padding: 1.1rem 1.6rem;
            border-bottom: 1px solid var(--border);
            font-size: 0.88rem;
            color: var(--text-body);
        }}

        tr:hover {{ background: #f8fafc; }}
        tr:last-child td {{ border-bottom: none; }}

        .project-name {{
            font-weight: 700;
            color: var(--text-heading);
            margin-bottom: 2px;
        }}

        .project-meta {{
            font-size: 0.75rem;
            color: var(--text-muted);
        }}

        .project-meta code {{
            font-family: monospace;
            background: #f1f5f9;
            padding: 2px 6px;
            border-radius: 4px;
            color: var(--text-body);
        }}

        .location-cell {{
            color: var(--text-muted);
            font-size: 0.84rem;
        }}

        .badge {{
            padding: 4px 12px;
            border-radius: 9999px;
            font-weight: 700;
            font-size: 0.74rem;
            display: inline-block;
        }}

        .badge-PRIORITY_FIELD_VERIFICATION_RECOMMENDED {{ background: #ffe4e6; color: #9f1239; border: 1px solid #fecdd3; }}
        .badge-PARTIAL_CHANGE_DETECTED {{ background: #fef3c7; color: #92400e; border: 1px solid #fde047; }}
        .badge-HIGH_PHYSICAL_CHANGE_VERIFIED {{ background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }}

        .btn-card {{
            color: var(--text-heading);
            text-decoration: none;
            font-size: 0.84rem;
            font-weight: 700;
            transition: opacity 0.15s;
        }}
        .btn-card:hover {{ opacity: 0.7; }}

        .empty-box {{
            text-align: center;
            padding: 3.5rem 2rem;
            color: var(--text-muted);
        }}

        @media (max-width: 900px) {{
            .sidebar {{ display: none; }}
            .main-wrapper {{ margin-left: 0; width: 100%; padding: 1.5rem 1rem; }}
            .stats-grid {{ grid-template-columns: 1fr; }}
            .audit-grid {{ grid-template-columns: 1fr; }}
            .scan-bar {{ flex-direction: column; gap: 1rem; text-align: center; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Top Navigation Bar -->
        <header class="topbar">
            <div class="brand-group">
                {logo_html}
                <div>
                    <div class="brand-title">Sentra</div>
                    <div class="brand-sub">AI Satellite Audit Platform for Public Infrastructure</div>
                </div>
            </div>

            <div class="topbar-actions">
                <div class="status-badge">
                    <div class="status-dot"></div>
                    Esri Wayback Feed Active
                </div>
            </div>
        </header>

        <!-- Metrics Overview Grid -->
        <section class="stats-grid">
            <div class="stat-card blue">
                <div class="stat-label">Audited Projects</div>
                <div class="stat-val">{total_audited}</div>
            </div>
            <div class="stat-card red">
                <div class="stat-label">Flagged for Verification</div>
                <div class="stat-val">{flagged_count}</div>
            </div>
            <div class="stat-card green">
                <div class="stat-label">Verified Physical Work</div>
                <div class="stat-val">{verified_count}</div>
            </div>
        </section>

        <!-- Infrastructure Audit Form & Map -->
        <section class="card-panel" id="audit-form">
            <h2 class="section-title">📍 Report Infrastructure Site for Satellite Audit</h2>

            <div class="audit-grid">
                <!-- Form Inputs -->
                <div class="form-col">
                    <div class="field-group">
                        <label>Work Title</label>
                        <input type="text" id="reportTitle" placeholder="e.g. Ward 12 Connector Road Asphalt Resurfacing" />
                    </div>

                    <div class="field-group">
                        <label>Description (Optional)</label>
                        <textarea id="reportDesc" placeholder="Brief description of the work going on..."></textarea>
                    </div>

                    <!-- Coordinates: Editable Input Fields with Map Sync -->
                    <div class="inline-row">
                        <div class="field-group">
                            <label>Latitude</label>
                            <input type="number" step="any" id="reportLat" placeholder="12.9333" oninput="onCoordInputChanged()" />
                        </div>
                        <div class="field-group">
                            <label>Longitude</label>
                            <input type="number" step="any" id="reportLon" placeholder="77.6637" oninput="onCoordInputChanged()" />
                        </div>
                    </div>

                    <!-- Date Range: Start & End Date -->
                    <div class="inline-row">
                        <div class="field-group">
                            <label>Estimated Start Date</label>
                            <input type="date" id="reportStartDate" />
                        </div>
                        <div class="field-group">
                            <label>Completion / Check Date</label>
                            <input type="date" id="reportEndDate" />
                            <div class="field-hint">Defaults to today if left blank</div>
                        </div>
                    </div>

                    <button class="btn-dark" id="submitBtn" onclick="submitReport()">Run Space-Borne Satellite Audit</button>
                    <div id="reportStatus" class="status-banner"></div>
                </div>

                <!-- Interactive Map -->
                <div class="map-wrap">
                    <div id="auditMap"></div>
                    <div class="map-caption">💡 Drag pin or click map to pick coordinates · Or type Lat/Lon manually</div>
                </div>
            </div>
        </section>

        <!-- Warm Cream Upload Tender Dropzone -->
        <section class="scan-bar" id="upload-zone" ondragover="handleDragOver(event)" ondragleave="handleDragLeave(event)" ondrop="handleDrop(event)">
            <div style="display:flex; align-items:center; justify-content:space-between; width:100%;">
                <div class="scan-left">
                    <span class="scan-icon">📄</span>
                    <div>
                        <div class="scan-title">Upload Tender Documents (PDF, Image, Text)</div>
                        <div class="scan-sub">Upload tender files directly from your browser to run automated satellite audits</div>
                    </div>
                </div>
                <div class="scan-actions">
                    <input type="file" id="tenderFileInput" multiple accept=".pdf,.png,.jpg,.jpeg,.txt,.doc,.docx" onchange="uploadTenders(this.files)" style="display:none;" />
                    <label for="tenderFileInput" class="btn-dark" style="margin:0; font-size:0.84rem; padding: 8px 18px; cursor:pointer;">📁 Choose Tender Files</label>
                    <button class="btn-secondary" id="scanBtn" onclick="scanFolder()">Scan Server ({pending_count})</button>
                </div>
            </div>
            <div id="scanStatus" class="status-banner" style="margin-top:0.85rem; width:100%;"></div>
        </section>

        <!-- Audit Results Table -->
        <section class="table-wrap" id="audit-log">
            <div class="table-head-bar">
                <h2>Audit Results Log</h2>
                <button class="btn-danger" onclick="clearHistory()">Clear History</button>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Project</th>
                        <th>Location</th>
                        <th>Verdict</th>
                        <th style="text-align: right;">Evidence Card</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html if rows_html else '<tr><td colspan="4"><div class="empty-box">No satellite audits in database yet. Submit a work site above or upload tender documents.</div></td></tr>'}
                </tbody>
            </table>
        </section>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        // ---- Map & Bidirectional Coordinate Sync ----
        const defaultLat = 12.9716;
        const defaultLon = 77.5946;

        const map = L.map('auditMap').setView([defaultLat, defaultLon], 13);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            maxZoom: 19,
            attribution: '© OpenStreetMap'
        }}).addTo(map);

        const marker = L.marker([defaultLat, defaultLon], {{ draggable: true }}).addTo(map);

        function syncInputsFromMarker(lat, lon) {{
            document.getElementById('reportLat').value = parseFloat(lat).toFixed(6);
            document.getElementById('reportLon').value = parseFloat(lon).toFixed(6);
        }}

        marker.on('dragend', function(e) {{
            const pos = marker.getLatLng();
            syncInputsFromMarker(pos.lat, pos.lng);
        }});

        map.on('click', function(e) {{
            marker.setLatLng(e.latlng);
            syncInputsFromMarker(e.latlng.lat, e.latlng.lng);
        }});

        function onCoordInputChanged() {{
            const latVal = parseFloat(document.getElementById('reportLat').value);
            const lonVal = parseFloat(document.getElementById('reportLon').value);
            if (!isNaN(latVal) && !isNaN(lonVal) && latVal >= -90 && latVal <= 90 && lonVal >= -180 && lonVal <= 180) {{
                const newLatLng = new L.LatLng(latVal, lonVal);
                marker.setLatLng(newLatLng);
                map.panTo(newLatLng);
            }}
        }}

        // Geolocation initialization
        if (navigator.geolocation) {{
            navigator.geolocation.getCurrentPosition(function(pos) {{
                const lat = pos.coords.latitude;
                const lon = pos.coords.longitude;
                map.setView([lat, lon], 14);
                marker.setLatLng([lat, lon]);
                syncInputsFromMarker(lat, lon);
            }}, function(err) {{
                syncInputsFromMarker(defaultLat, defaultLon);
            }});
        }} else {{
            syncInputsFromMarker(defaultLat, defaultLon);
        }}

        // Set default dates: Start Date to 6 months ago, End Date to today
        const today = new Date();
        const sixMonthsAgo = new Date();
        sixMonthsAgo.setMonth(today.getMonth() - 6);

        document.getElementById('reportStartDate').valueAsDate = sixMonthsAgo;
        document.getElementById('reportEndDate').valueAsDate = today;

        setTimeout(() => map.invalidateSize(), 250);

        // ---- Submit Citizen Report ----
        async function submitReport() {{
            const title = document.getElementById('reportTitle').value.trim();
            const desc = document.getElementById('reportDesc').value.trim();
            const latVal = parseFloat(document.getElementById('reportLat').value);
            const lonVal = parseFloat(document.getElementById('reportLon').value);
            const startDate = document.getElementById('reportStartDate').value;
            const endDate = document.getElementById('reportEndDate').value;
            const btn = document.getElementById('submitBtn');
            const statusEl = document.getElementById('reportStatus');

            if (!title) {{
                alert('Please enter a project or work title.');
                return;
            }}
            if (isNaN(latVal) || isNaN(lonVal)) {{
                alert('Please enter or pick valid Latitude and Longitude coordinates.');
                return;
            }}

            btn.disabled = true;
            btn.textContent = 'Analyzing satellite imagery...';
            statusEl.className = 'status-banner processing';
            statusEl.textContent = '⏳ Retrieving dual-temporal satellite imagery & computing spectral change...';

            try {{
                const body = {{
                    title: title,
                    description: desc,
                    latitude: latVal,
                    longitude: lonVal
                }};
                if (startDate) body.estimated_start_date = startDate;
                if (endDate) body.estimated_end_date = endDate;

                const resp = await fetch('/api/community/report', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(body)
                }});
                const data = await resp.json();

                if (data.status === 'success') {{
                    statusEl.className = 'status-banner success';
                    statusEl.textContent = '✅ Audit Complete — Verdict: ' + data.verdict;
                    window.open(data.evidence_card_url, '_blank');
                    setTimeout(() => window.location.reload(), 2000);
                }} else {{
                    statusEl.className = 'status-banner error';
                    statusEl.textContent = '❌ ' + (data.detail || JSON.stringify(data));
                }}
            }} catch (err) {{
                statusEl.className = 'status-banner error';
                statusEl.textContent = '❌ Request failed: ' + err.message;
            }} finally {{
                btn.disabled = false;
                btn.textContent = 'Run Space-Borne Satellite Audit';
            }}
        }}

        // ---- Upload Tender Files Directly ----
        async function uploadTenders(fileList) {{
            if (!fileList || fileList.length === 0) return;

            const statusEl = document.getElementById('scanStatus');
            statusEl.className = 'status-banner processing';
            statusEl.textContent = `⏳ Uploading and auditing ${{fileList.length}} tender file(s)...`;

            const formData = new FormData();
            for (let i = 0; i < fileList.length; i++) {{
                formData.append('files', fileList[i]);
            }}

            try {{
                const resp = await fetch('/api/audit/upload-tender', {{
                    method: 'POST',
                    body: formData
                }});
                const data = await resp.json();

                if (data.status === 'success') {{
                    statusEl.className = 'status-banner success';
                    statusEl.textContent = '✅ ' + data.message;
                    if (data.results && data.results.length > 0) {{
                        window.open(data.results[0].evidence_card_url, '_blank');
                    }}
                    setTimeout(() => window.location.reload(), 2000);
                }} else {{
                    statusEl.className = 'status-banner error';
                    statusEl.textContent = '❌ ' + (data.detail || data.message || 'Upload failed');
                }}
            }} catch (err) {{
                statusEl.className = 'status-banner error';
                statusEl.textContent = '❌ Upload failed: ' + err.message;
            }}
        }}

        // Drag & Drop event handlers
        function handleDragOver(e) {{
            e.preventDefault();
            document.getElementById('upload-zone').classList.add('drag-over');
        }}
        function handleDragLeave(e) {{
            e.preventDefault();
            document.getElementById('upload-zone').classList.remove('drag-over');
        }}
        function handleDrop(e) {{
            e.preventDefault();
            document.getElementById('upload-zone').classList.remove('drag-over');
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {{
                uploadTenders(e.dataTransfer.files);
            }}
        }}

        // ---- Scan Folder ----
        async function scanFolder() {{
            const btn = document.getElementById('scanBtn');
            const statusEl = document.getElementById('scanStatus');

            btn.disabled = true;
            btn.textContent = 'Scanning...';
            statusEl.className = 'status-banner processing';
            statusEl.textContent = '⏳ Scanning tender folder...';

            try {{
                const resp = await fetch('/api/audit/scan-folder', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }}
                }});
                const data = await resp.json();

                if (data.status === 'success') {{
                    statusEl.className = 'status-banner success';
                    statusEl.textContent = '✅ ' + data.message;
                    setTimeout(() => window.location.reload(), 2000);
                }} else {{
                    statusEl.className = 'status-banner error';
                    statusEl.textContent = '❌ ' + (data.message || JSON.stringify(data));
                }}
            }} catch (err) {{
                statusEl.className = 'status-banner error';
                statusEl.textContent = '❌ Scan failed: ' + err.message;
            }} finally {{
                btn.disabled = false;
                btn.textContent = 'Scan Server ({pending_count})';
            }}
        }}

        // ---- Clear History ----
        async function clearHistory() {{
            if (!confirm('Are you sure you want to clear all audited records?')) return;
            try {{
                const resp = await fetch('/api/audit/clear-data', {{ method: 'POST' }});
                const data = await resp.json();
                if (data.status === 'success') {{
                    window.location.reload();
                }}
            }} catch (err) {{
                alert('Clear failed: ' + err.message);
            }}
        }}
    </script>
</body>
</html>
    """
        return HTMLResponse(content=html)
    except Exception as e:
        print(f"[App] Error in serve_home: {e}")
        return HTMLResponse(content=f"<html><body style='background:#f8fafc;color:#0f172a;font-family:sans-serif;padding:2rem;'><h2>Sentra AI Audit Platform</h2><p>Server initialized cleanly. Reload to refresh dashboard.</p><script>setTimeout(() => window.location.reload(), 1500);</script></body></html>")


@app.post("/api/community/report")
def community_report_endpoint(request: CommunityReportRequest):
    """
    Accepts a community-submitted infrastructure work report,
    runs the full satellite audit pipeline, and returns the verdict.
    """
    try:
        report = CommunityReport(
            title=request.title,
            description=request.description or "",
            latitude=request.latitude,
            longitude=request.longitude,
            estimated_start_date=request.estimated_start_date,
            estimated_end_date=request.estimated_end_date
        )

        print(f"\n[COMMUNITY REPORT] '{report.title}'")
        print(f"  Location: ({report.latitude}, {report.longitude})")
        print(f"  Start Date: {report.get_start_date()} | Check Date: {report.get_completion_date()}")

        record, card_res = run_community_report_audit(report)
        audit_res = record["audit"]
        tender = record["tender"]

        verdict_map = {
            "PRIORITY_FIELD_VERIFICATION_RECOMMENDED": "Flagged for Verification",
            "PARTIAL_CHANGE_DETECTED": "Partial Change Detected",
            "HIGH_PHYSICAL_CHANGE_VERIFIED": "Verified — Physical Change Confirmed"
        }

        return {
            "status": "success",
            "report_id": tender.tender_id,
            "verdict": verdict_map.get(audit_res.classification, audit_res.classification),
            "classification": audit_res.classification,
            "physical_change": audit_res.physical_alteration_score,
            "evidence_card_url": f"/reports/{tender.tender_id}/evidence_card.html",
            "audit_hash": card_res["audit_hash"]
        }
    except Exception as e:
        print(f"[COMMUNITY REPORT ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/audit/upload-tender")
async def upload_tender_endpoint(files: List[UploadFile] = File(...)):
    """
    Accepts uploaded tender documents (PDF, images, text), saves them to data/raw_tenders/,
    runs the full satellite audit pipeline on each file, and returns results.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    
    saved_paths = []
    for file in files:
        if not file.filename:
            continue
        safe_filename = os.path.basename(file.filename)
        target_path = os.path.join("./data/raw_tenders", safe_filename)
        contents = await file.read()
        with open(target_path, "wb") as f:
            f.write(contents)
        saved_paths.append(target_path)
    
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
                "evidence_card_url": f"/reports/{record['tender'].tender_id}/evidence_card.html"
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
        "errors": errors
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
        record, card_res = run_full_audit(
            request.tender_text,
            request.scenario_override
        )
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
            "audit_hash": card_res["audit_hash"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/audit/scan-folder")
def scan_folder_endpoint():
    """
    Scans data/raw_tenders/ for new tender documents, extracts text,
    parses structured data, fetches satellite imagery, runs CV analysis,
    and generates evidence cards for each.
    """
    try:
        results = folder_scanner.scan()

        if not results:
            return {
                "status": "success",
                "message": "No new tender documents found in data/raw_tenders/",
                "processed": 0
            }

        processed = 0
        errors = []

        for filepath, text, tender_data in results:
            try:
                record, card_res = run_full_audit(text)
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
            "errors": errors
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/audit/clear-data")
def clear_data_endpoint():
    """
    Clears all saved audited project records from the database.
    """
    try:
        clear_all_records()
        global AUDITED_RECORDS
        AUDITED_RECORDS = []
        return {"status": "success", "message": "All audited database records cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
