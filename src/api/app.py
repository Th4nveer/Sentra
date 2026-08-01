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
    version="2.2.0"
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
    Renders the interactive Sentra AI Web Dashboard.
    Supports community reporting, interactive map, direct tender document file uploads (PDF, images, TXT),
    and satellite audit evidence cards.
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
        logo_html = '<div class="brand-icon">S</div>'
        for ext in ["png", "svg", "jpg", "jpeg", "webp"]:
            logo_path = f"./static/logo.{ext}"
            if os.path.exists(logo_path):
                logo_html = f'<img src="/static/logo.{ext}" alt="Logo" class="brand-logo-img" style="height: 56px; width: auto; max-width: 260px; object-fit: contain; border-radius: 8px;" />'
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
            
            source_tag = "👥 Citizen Report" if t.tender_id.startswith("CR-") else "📄 Tender Doc"

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
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        :root {{
            --bg: #090d16;
            --surface: #111827;
            --surface-subtle: #1f2937;
            --border: rgba(255, 255, 255, 0.08);
            --border-hover: rgba(255, 255, 255, 0.16);
            --accent: #6366f1;
            --accent-glow: rgba(99, 102, 241, 0.25);
            --accent-cyan: #06b6d4;
            --accent-green: #10b981;
            --accent-red: #f43f5e;
            --accent-amber: #f59e0b;
            --text-primary: #f9fafb;
            --text-secondary: #9ca3af;
            --text-tertiary: #6b7280;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg);
            color: var(--text-primary);
            padding: 2.5rem 1.5rem;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }}

        .container {{
            max-width: 1140px;
            margin: 0 auto;
        }}

        /* ---- Header Bar ---- */
        .navbar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1.25rem;
            border-bottom: 1px solid var(--border);
        }}

        .brand-group {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .brand-icon {{
            width: 38px;
            height: 38px;
            background: linear-gradient(135deg, #6366f1 0%, #06b6d4 100%);
            border-radius: 9px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 1.1rem;
            color: #ffffff;
            box-shadow: 0 0 20px var(--accent-glow);
        }}

        .brand-title {{
            font-size: 1.35rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: #ffffff;
        }}

        .brand-sub {{
            font-size: 0.75rem;
            color: var(--text-secondary);
            font-weight: 400;
        }}

        .status-badge {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 14px;
            background: rgba(16, 185, 129, 0.08);
            border: 1px solid rgba(16, 185, 129, 0.25);
            border-radius: 9999px;
            font-size: 0.78rem;
            font-weight: 500;
            color: var(--accent-green);
        }}

        .status-dot {{
            width: 6px;
            height: 6px;
            background: var(--accent-green);
            border-radius: 50%;
            box-shadow: 0 0 8px var(--accent-green);
        }}

        /* ---- Metrics Overview ---- */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1rem;
            margin-bottom: 2rem;
        }}

        .stat-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.25rem 1.5rem;
            transition: border-color 0.2s ease;
        }}

        .stat-card:hover {{
            border-color: var(--border-hover);
        }}

        .stat-label {{
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--text-tertiary);
            font-weight: 600;
            margin-bottom: 0.35rem;
        }}

        .stat-val {{
            font-size: 1.9rem;
            font-weight: 700;
            letter-spacing: -0.02em;
        }}

        /* ---- Audit Form Section ---- */
        .card-panel {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.75rem;
            margin-bottom: 2rem;
        }}

        .section-title {{
            font-size: 1.05rem;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 1.25rem;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .audit-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
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
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
        }}

        .field-group input[type="text"],
        .field-group input[type="number"],
        .field-group input[type="date"],
        .field-group textarea {{
            width: 100%;
            background: #0d121f;
            border: 1px solid var(--border);
            border-radius: 8px;
            color: #ffffff;
            padding: 0.65rem 0.9rem;
            font-family: inherit;
            font-size: 0.88rem;
            transition: all 0.2s ease;
        }}

        .field-group input:focus,
        .field-group textarea:focus {{
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }}

        .field-group textarea {{
            resize: vertical;
            min-height: 65px;
        }}

        .inline-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.85rem;
        }}

        .field-hint {{
            font-size: 0.7rem;
            color: var(--text-tertiary);
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
            min-height: 290px;
            border-radius: 10px;
            border: 1px solid var(--border);
            z-index: 1;
        }}

        .map-caption {{
            font-size: 0.72rem;
            color: var(--text-tertiary);
            margin-top: 0.5rem;
            text-align: center;
        }}

        /* Buttons */
        .btn-primary {{
            background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
            color: #ffffff;
            border: none;
            padding: 0.8rem 1.5rem;
            border-radius: 9px;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 14px var(--accent-glow);
            transition: all 0.2s ease;
            margin-top: 0.5rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }}

        .btn-primary:hover {{
            transform: translateY(-1px);
            box-shadow: 0 6px 20px var(--accent-glow);
        }}

        .btn-primary:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }}

        /* ---- Folder Scan & File Upload Section ---- */
        .scan-bar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 1.25rem 1.5rem;
            background: var(--surface);
            border: 1px dashed var(--border-hover);
            border-radius: 14px;
            margin-bottom: 2rem;
            transition: all 0.2s ease;
        }}

        .scan-bar.drag-over {{
            border-color: var(--accent);
            background: rgba(99, 102, 241, 0.05);
        }}

        .scan-left {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}

        .scan-icon {{
            font-size: 1.5rem;
            background: rgba(99, 102, 241, 0.1);
            padding: 8px;
            border-radius: 10px;
        }}

        .scan-title {{
            font-size: 0.92rem;
            font-weight: 600;
            color: #ffffff;
        }}

        .scan-sub {{
            font-size: 0.75rem;
            color: var(--text-tertiary);
        }}

        .scan-actions {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .badge-pending {{
            background: rgba(99, 102, 241, 0.15);
            color: var(--accent);
            border: 1px solid rgba(99, 102, 241, 0.3);
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.72rem;
            font-weight: 600;
        }}

        .btn-secondary {{
            background: var(--surface-subtle);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 0.82rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .btn-secondary:hover {{
            border-color: var(--border-hover);
            background: #2d3748;
        }}

        .btn-danger {{
            background: transparent;
            border: 1px solid rgba(244, 63, 94, 0.3);
            color: var(--accent-red);
            padding: 8px 14px;
            border-radius: 8px;
            font-size: 0.82rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .btn-danger:hover {{
            background: rgba(244, 63, 94, 0.1);
            border-color: var(--accent-red);
        }}

        /* Status banner */
        .status-banner {{
            margin-top: 1rem;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            font-size: 0.82rem;
            display: none;
        }}
        .status-banner.processing {{ display: block; background: rgba(99, 102, 241, 0.1); border: 1px solid var(--accent); color: #a5b4fc; }}
        .status-banner.success {{ display: block; background: rgba(16, 185, 129, 0.1); border: 1px solid var(--accent-green); color: var(--accent-green); }}
        .status-banner.error {{ display: block; background: rgba(244, 63, 94, 0.1); border: 1px solid var(--accent-red); color: var(--accent-red); }}

        /* ---- Table ---- */
        .table-wrap {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 14px;
            overflow: hidden;
        }}

        .table-head-bar {{
            padding: 1.25rem 1.5rem;
            border-bottom: 1px solid var(--border);
        }}

        .table-head-bar h2 {{
            font-size: 0.95rem;
            font-weight: 600;
            color: #ffffff;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }}

        th {{
            background: rgba(15, 23, 42, 0.6);
            padding: 0.8rem 1.5rem;
            font-size: 0.7rem;
            color: var(--text-tertiary);
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-weight: 600;
            border-bottom: 1px solid var(--border);
        }}

        td {{
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border);
            font-size: 0.86rem;
        }}

        tr:hover {{ background: rgba(255, 255, 255, 0.02); }}
        tr:last-child td {{ border-bottom: none; }}

        .project-name {{
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 2px;
        }}

        .project-meta {{
            font-size: 0.72rem;
            color: var(--text-tertiary);
        }}

        .project-meta code {{
            font-family: monospace;
            color: var(--text-secondary);
        }}

        .location-cell {{
            color: var(--text-secondary);
            font-size: 0.82rem;
        }}

        .badge {{
            padding: 3px 10px;
            border-radius: 9999px;
            font-weight: 600;
            font-size: 0.72rem;
            display: inline-block;
        }}

        .badge-PRIORITY_FIELD_VERIFICATION_RECOMMENDED {{ background: rgba(244, 63, 94, 0.15); color: var(--accent-red); border: 1px solid rgba(244, 63, 94, 0.3); }}
        .badge-PARTIAL_CHANGE_DETECTED {{ background: rgba(245, 158, 11, 0.15); color: var(--accent-amber); border: 1px solid rgba(245, 158, 11, 0.3); }}
        .badge-HIGH_PHYSICAL_CHANGE_VERIFIED {{ background: rgba(16, 185, 129, 0.15); color: var(--accent-green); border: 1px solid rgba(16, 185, 129, 0.3); }}

        .btn-card {{
            color: var(--accent-cyan);
            text-decoration: none;
            font-size: 0.82rem;
            font-weight: 600;
            transition: opacity 0.2s;
        }}
        .btn-card:hover {{ opacity: 0.8; text-decoration: underline; }}

        .empty-box {{
            text-align: center;
            padding: 3rem 2rem;
            color: var(--text-tertiary);
        }}

        @media (max-width: 768px) {{
            body {{ padding: 1.5rem 1rem; }}
            .stats-grid {{ grid-template-columns: 1fr; }}
            .audit-grid {{ grid-template-columns: 1fr; }}
            .scan-bar {{ flex-direction: column; gap: 1rem; text-align: center; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Navbar -->
        <div class="navbar">
            <div class="brand-group">
                {logo_html}
                <div>
                    <div class="brand-title">SENTRA</div>
                    <div class="brand-sub">AI Satellite Audit Platform for Public Infrastructure</div>
                </div>
            </div>
            <div class="status-badge">
                <div class="status-dot"></div>
                Esri Wayback API Active
            </div>
        </div>

        <!-- Metrics Overview -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Audited Projects</div>
                <div class="stat-val" style="color: var(--accent-cyan);">{total_audited}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Flagged for Verification</div>
                <div class="stat-val" style="color: var(--accent-red);">{flagged_count}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Verified Physical Work</div>
                <div class="stat-val" style="color: var(--accent-green);">{verified_count}</div>
            </div>
        </div>

        <!-- Main Audit Form -->
        <div class="card-panel">
            <div class="section-title">📍 Report Infrastructure Site for Satellite Audit</div>

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

                    <button class="btn-primary" id="submitBtn" onclick="submitReport()">Run Space-Borne Satellite Audit</button>
                    <div id="reportStatus" class="status-banner"></div>
                </div>

                <!-- Interactive Map -->
                <div class="map-wrap">
                    <div id="auditMap"></div>
                    <div class="map-caption">💡 Drag pin or click map to pick coordinates · Or type Lat/Lon manually</div>
                </div>
            </div>
        </div>

        <!-- Interactive File Upload & Tender Scan Zone -->
        <div class="scan-bar" id="dropZone" ondragover="handleDragOver(event)" ondragleave="handleDragLeave(event)" ondrop="handleDrop(event)">
            <div class="scan-left">
                <span class="scan-icon">📄</span>
                <div>
                    <div class="scan-title">Upload Tender Documents (PDF, Image, Text)</div>
                    <div class="scan-sub">Upload tender files directly from your browser to run automated satellite audits</div>
                </div>
            </div>
            <div class="scan-actions">
                <input type="file" id="tenderFileInput" multiple accept=".pdf,.png,.jpg,.jpeg,.txt,.doc,.docx" onchange="uploadTenders(this.files)" style="display:none;" />
                <label for="tenderFileInput" class="btn-primary" style="margin:0; font-size:0.82rem; padding: 8px 16px; cursor:pointer;">📁 Upload Files</label>
                <button class="btn-secondary" id="scanBtn" onclick="scanFolder()">Scan Server ({pending_count})</button>
                <button class="btn-danger" onclick="clearHistory()">Clear History</button>
            </div>
        </div>
        <div id="scanStatus" class="status-banner"></div>

        <!-- Audit Results Table -->
        <div class="table-wrap">
            <div class="table-head-bar">
                <h2>Audit Results Log</h2>
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
        </div>
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
            document.getElementById('dropZone').classList.add('drag-over');
        }}
        function handleDragLeave(e) {{
            e.preventDefault();
            document.getElementById('dropZone').classList.remove('drag-over');
        }}
        function handleDrop(e) {{
            e.preventDefault();
            document.getElementById('dropZone').classList.remove('drag-over');
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
        return HTMLResponse(content=f"<html><body style='background:#090d16;color:#ffffff;font-family:sans-serif;padding:2rem;'><h2>Sentra AI Audit Platform</h2><p>Server initialized cleanly. Reload to refresh dashboard.</p><script>setTimeout(() => window.location.reload(), 1500);</script></body></html>")


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
