"""
FastAPI Web API Server & Interactive Web Application for Sentra AI Satellite Audit Platform.
"""
import os
from datetime import date
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
    version="2.0.0"
)

# Ensure directories exist and mount static files
os.makedirs("./data/reports", exist_ok=True)
os.makedirs("./data/raw_tenders", exist_ok=True)
os.makedirs("./data/processed", exist_ok=True)
app.mount("/reports", StaticFiles(directory="./data/reports", html=True), name="reports")

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
    Renders the full interactive Sentra AI Web Application at the root URL.
    Includes community report submission with interactive map and simplified audit results table.
    """
    try:
        audited_records = load_all_records() or []
        total_audited = len(audited_records)
        flagged_count = sum(1 for r in audited_records if r["audit"].classification in [
            "PRIORITY_FIELD_VERIFICATION_RECOMMENDED", "PARTIAL_CHANGE_DETECTED"
        ])
        verified_count = sum(1 for r in audited_records if r["audit"].classification == "HIGH_PHYSICAL_CHANGE_VERIFIED")

        # Get pending tender count
        pending_count = folder_scanner.get_pending_count() if folder_scanner else 0

        rows_html = ""
        for r in sorted(audited_records, key=lambda x: x["audit"].fraud_risk_score, reverse=True):
            t = r["tender"]
            a = r["audit"]
            g = r["geocoding"]
            badge_cls = f"badge-{a.classification}"
            
            # Human-readable verdict labels
            verdict_map = {
                "PRIORITY_FIELD_VERIFICATION_RECOMMENDED": "Flagged",
                "PARTIAL_CHANGE_DETECTED": "Partial",
                "HIGH_PHYSICAL_CHANGE_VERIFIED": "Verified"
            }
            badge_label = verdict_map.get(a.classification, a.classification.replace("_", " "))
            
            # Truncate location for table display
            location_display = g.formatted_address
            if len(location_display) > 50:
                location_display = location_display[:47] + "..."
            
            # Source tag for community vs tender
            source_tag = "👥 Community" if t.tender_id.startswith("CR-") else "📄 Tender"

            rows_html += f"""
            <tr>
                <td>
                    <div class="project-name">{t.project_name}</div>
                    <div class="project-meta">{source_tag} · {t.tender_id}</div>
                </td>
                <td class="location-cell">{location_display}</td>
                <td><span class="badge {badge_cls}">{badge_label}</span></td>
                <td><a class="btn-card" href="/reports/{t.tender_id}/evidence_card.html" target="_blank">View</a></td>
            </tr>
            """

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SENTRA - AI Satellite Audit for Public Infrastructure</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        :root {{
            --bg: #090d16;
            --card-bg: #131b2e;
            --card-border: #1e293b;
            --accent-red: #ef4444;
            --accent-yellow: #f59e0b;
            --accent-green: #10b981;
            --accent-blue: #3b82f6;
            --accent-purple: #8b5cf6;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            padding: 2rem;
            line-height: 1.5;
        }}

        .navbar {{
            max-width: 1200px;
            margin: 0 auto 2rem auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 1.5rem;
            background: rgba(19, 27, 46, 0.7);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            backdrop-filter: blur(10px);
        }}

        .brand-logo {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .logo-icon {{
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, #ef4444, #3b82f6);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 1.2rem;
            color: #fff;
            box-shadow: 0 4px 14px rgba(239, 68, 68, 0.3);
        }}

        .brand-name {{
            font-size: 1.5rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            background: linear-gradient(135deg, #ffffff 0%, #94a3b8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .status-pill {{
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid var(--accent-green);
            color: var(--accent-green);
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 0.8rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .pulse-dot {{
            width: 8px;
            height: 8px;
            background: var(--accent-green);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }}

        @keyframes pulse {{
            0% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }}
            70% {{ transform: scale(1); box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }}
            100% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }}
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1.25rem;
            margin-bottom: 2rem;
        }}

        .stat-card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            padding: 1.25rem 1.5rem;
        }}

        .stat-title {{
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
        }}

        .stat-value {{
            font-size: 1.8rem;
            font-weight: 700;
        }}

        /* ---- Report Panel ---- */
        .report-panel {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.75rem;
            margin-bottom: 2rem;
        }}

        .panel-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.25rem;
        }}

        .panel-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #ffffff;
        }}

        .report-form {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
        }}

        .form-left {{
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }}

        .form-group {{
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
        }}

        .form-group label {{
            font-size: 0.78rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.04em;
            font-weight: 500;
        }}

        .form-group input,
        .form-group textarea {{
            width: 100%;
            background: #0d1322;
            border: 1px solid var(--card-border);
            border-radius: 10px;
            color: #fff;
            padding: 0.7rem 1rem;
            font-family: inherit;
            font-size: 0.9rem;
            transition: border-color 0.2s ease;
        }}

        .form-group input:focus,
        .form-group textarea:focus {{
            outline: none;
            border-color: var(--accent-blue);
        }}

        .form-group textarea {{
            resize: vertical;
            min-height: 70px;
        }}

        .coord-display {{
            display: flex;
            gap: 0.75rem;
            align-items: center;
            padding: 0.6rem 1rem;
            background: rgba(59, 130, 246, 0.08);
            border: 1px solid rgba(59, 130, 246, 0.2);
            border-radius: 10px;
            font-size: 0.85rem;
        }}

        .coord-display span {{
            color: var(--accent-blue);
            font-weight: 600;
            font-family: 'Courier New', monospace;
        }}

        .form-right {{
            display: flex;
            flex-direction: column;
        }}

        #reportMap {{
            flex: 1;
            min-height: 280px;
            border-radius: 12px;
            border: 1px solid var(--card-border);
            z-index: 1;
        }}

        .map-hint {{
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 0.5rem;
            text-align: center;
        }}

        .btn-submit {{
            background: linear-gradient(135deg, #ef4444, #3b82f6);
            color: #ffffff;
            border: none;
            padding: 12px 24px;
            border-radius: 10px;
            font-size: 0.95rem;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(59, 130, 246, 0.4);
            transition: all 0.2s ease;
            margin-top: 0.5rem;
            width: 100%;
        }}

        .btn-submit:hover {{
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(59, 130, 246, 0.6);
        }}

        .btn-submit:disabled {{
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }}

        /* ---- Scan Section ---- */
        .scan-section {{
            display: flex;
            align-items: center;
            gap: 1rem;
            padding: 1rem 1.25rem;
            background: rgba(139, 92, 246, 0.08);
            border: 1px dashed var(--accent-purple);
            border-radius: 12px;
            margin-bottom: 2rem;
        }}

        .scan-info {{
            flex: 1;
        }}

        .scan-info .label {{
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--accent-purple);
        }}

        .scan-info .hint {{
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 2px;
        }}

        .pending-badge {{
            background: var(--accent-purple);
            color: #fff;
            padding: 3px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
        }}

        .btn-scan {{
            background: linear-gradient(135deg, #8b5cf6, #6d28d9);
            color: #ffffff;
            border: none;
            padding: 10px 20px;
            border-radius: 10px;
            font-size: 0.88rem;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(139, 92, 246, 0.4);
            transition: all 0.2s ease;
            white-space: nowrap;
        }}

        .btn-scan:hover {{
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(139, 92, 246, 0.6);
        }}

        .btn-scan:disabled {{
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }}

        .btn-clear {{
            background: transparent;
            border: 1px solid rgba(239, 68, 68, 0.4);
            color: var(--accent-red);
            padding: 10px 16px;
            border-radius: 10px;
            font-size: 0.82rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            white-space: nowrap;
        }}

        .btn-clear:hover {{
            background: rgba(239, 68, 68, 0.1);
            border-color: var(--accent-red);
        }}

        /* ---- Status Messages ---- */
        .status-msg {{
            margin-top: 0.75rem;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            font-size: 0.82rem;
            display: none;
        }}

        .status-msg.processing {{
            display: block;
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid var(--accent-blue);
            color: var(--accent-blue);
        }}

        .status-msg.success {{
            display: block;
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid var(--accent-green);
            color: var(--accent-green);
        }}

        .status-msg.error {{
            display: block;
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid var(--accent-red);
            color: var(--accent-red);
        }}

        /* ---- Table ---- */
        .table-panel {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            overflow: hidden;
        }}

        .table-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.25rem 1.5rem 0.75rem 1.5rem;
        }}

        .table-header h2 {{
            font-size: 1rem;
            font-weight: 600;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }}

        th {{
            background: rgba(15, 23, 42, 0.9);
            padding: 0.85rem 1.25rem;
            font-size: 0.72rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 1px solid var(--card-border);
        }}

        td {{
            padding: 1rem 1.25rem;
            border-bottom: 1px solid var(--card-border);
            font-size: 0.88rem;
        }}

        tr:hover {{ background: rgba(30, 41, 59, 0.4); }}
        tr:last-child td {{ border-bottom: none; }}

        .project-name {{
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 2px;
        }}

        .project-meta {{
            font-size: 0.72rem;
            color: var(--text-muted);
        }}

        .location-cell {{
            color: var(--text-muted);
            font-size: 0.82rem;
        }}

        .badge {{
            padding: 4px 12px;
            border-radius: 9999px;
            font-weight: 600;
            font-size: 0.72rem;
            display: inline-block;
        }}

        .badge-PRIORITY_FIELD_VERIFICATION_RECOMMENDED {{ background: rgba(239, 68, 68, 0.2); color: var(--accent-red); border: 1px solid var(--accent-red); }}
        .badge-PARTIAL_CHANGE_DETECTED {{ background: rgba(245, 158, 11, 0.2); color: var(--accent-yellow); border: 1px solid var(--accent-yellow); }}
        .badge-HIGH_PHYSICAL_CHANGE_VERIFIED {{ background: rgba(16, 185, 129, 0.2); color: var(--accent-green); border: 1px solid var(--accent-green); }}

        .btn-card {{
            background: var(--accent-blue);
            color: #ffffff;
            text-decoration: none;
            padding: 5px 14px;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 600;
            display: inline-block;
            transition: opacity 0.2s;
        }}
        .btn-card:hover {{ opacity: 0.85; }}

        .empty-state {{
            text-align: center;
            padding: 3rem 2rem;
            color: var(--text-muted);
        }}

        .empty-state .icon {{
            font-size: 2.5rem;
            margin-bottom: 0.75rem;
        }}

        @media (max-width: 768px) {{
            body {{ padding: 1rem; }}
            .stats-grid {{ grid-template-columns: 1fr; }}
            .report-form {{ grid-template-columns: 1fr; }}
            .scan-section {{ flex-direction: column; text-align: center; }}
        }}
    </style>
</head>
<body>
    <div class="navbar">
        <div class="brand-logo">
            <div class="logo-icon">S</div>
            <div>
                <div class="brand-name">SENTRA</div>
                <div style="font-size: 0.75rem; color: var(--text-muted);">AI-Powered Satellite Audit Engine</div>
            </div>
        </div>
        <div class="status-pill">
            <div class="pulse-dot"></div>
            Esri World Imagery Wayback Active
        </div>
    </div>

    <div class="container">
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-title">Audited Projects</div>
                <div class="stat-value" style="color:var(--accent-blue);">{total_audited}</div>
            </div>
            <div class="stat-card">
                <div class="stat-title">Flagged for Verification</div>
                <div class="stat-value" style="color:var(--accent-red);">{flagged_count}</div>
            </div>
            <div class="stat-card">
                <div class="stat-title">Verified</div>
                <div class="stat-value" style="color:var(--accent-green);">{verified_count}</div>
            </div>
        </div>

        <div class="report-panel">
            <div class="panel-header">
                <div class="panel-title">📍 Report Infrastructure Work</div>
            </div>

            <div class="report-form">
                <div class="form-left">
                    <div class="form-group">
                        <label>Work Title</label>
                        <input type="text" id="reportTitle" placeholder="e.g. Road resurfacing near Silk Board" />
                    </div>
                    <div class="form-group">
                        <label>Description (optional)</label>
                        <textarea id="reportDesc" placeholder="Any details about the infrastructure work..."></textarea>
                    </div>
                    <div class="form-group">
                        <label>Estimated Start Date</label>
                        <input type="date" id="reportDate" />
                    </div>
                    <div class="coord-display">
                        📌 Pin: <span id="coordLat">—</span>, <span id="coordLon">—</span>
                    </div>
                    <button class="btn-submit" id="submitBtn" onclick="submitReport()">Run Satellite Audit</button>
                </div>
                <div class="form-right">
                    <div id="reportMap"></div>
                    <div class="map-hint">Drag the pin to the work location · Scroll to zoom</div>
                </div>
            </div>
            <div id="reportStatus" class="status-msg"></div>
        </div>

        <div class="scan-section">
            <div class="scan-info">
                <div class="label">📂 Scan Tender Folder</div>
                <div class="hint">Drop PDF, image, or text files into <code>data/raw_tenders/</code> and click scan</div>
            </div>
            <span class="pending-badge">{pending_count} pending</span>
            <div style="display: flex; gap: 8px;">
                <button class="btn-scan" id="scanBtn" onclick="scanFolder()">Scan & Audit</button>
                <button class="btn-clear" onclick="clearHistory()">Clear All</button>
            </div>
        </div>
        <div id="scanStatus" class="status-msg"></div>

        <div class="table-panel">
            <div class="table-header">
                <h2>Audit Results</h2>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Project</th>
                        <th>Location</th>
                        <th>Verdict</th>
                        <th>Evidence</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html if rows_html else '<tr><td colspan="4"><div class="empty-state"><div class="icon">🛰️</div><div>No audits yet. Report a work site above or scan tender documents.</div></div></td></tr>'}
                </tbody>
            </table>
        </div>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        // ---- Map Initialization ----
        const defaultLat = 12.9716;
        const defaultLon = 77.5946;
        let pinLat = defaultLat;
        let pinLon = defaultLon;

        const map = L.map('reportMap').setView([defaultLat, defaultLon], 13);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            maxZoom: 19,
            attribution: '© OpenStreetMap'
        }}).addTo(map);

        const marker = L.marker([defaultLat, defaultLon], {{ draggable: true }}).addTo(map);

        function updateCoordDisplay(lat, lon) {{
            pinLat = lat;
            pinLon = lon;
            document.getElementById('coordLat').textContent = lat.toFixed(6);
            document.getElementById('coordLon').textContent = lon.toFixed(6);
        }}

        marker.on('dragend', function(e) {{
            const pos = marker.getLatLng();
            updateCoordDisplay(pos.lat, pos.lng);
        }});

        map.on('click', function(e) {{
            marker.setLatLng(e.latlng);
            updateCoordDisplay(e.latlng.lat, e.latlng.lng);
        }});

        // Attempt to use the user's current location
        if (navigator.geolocation) {{
            navigator.geolocation.getCurrentPosition(function(pos) {{
                const lat = pos.coords.latitude;
                const lon = pos.coords.longitude;
                map.setView([lat, lon], 15);
                marker.setLatLng([lat, lon]);
                updateCoordDisplay(lat, lon);
            }}, function(err) {{
                // Geolocation denied or unavailable, use default
                updateCoordDisplay(defaultLat, defaultLon);
            }});
        }} else {{
            updateCoordDisplay(defaultLat, defaultLon);
        }}

        // Default date to today
        document.getElementById('reportDate').valueAsDate = new Date();

        // Fix Leaflet map rendering in initially hidden or flexbox containers
        setTimeout(() => map.invalidateSize(), 200);

        // ---- Submit Community Report ----
        async function submitReport() {{
            const title = document.getElementById('reportTitle').value.trim();
            const desc = document.getElementById('reportDesc').value.trim();
            const dateVal = document.getElementById('reportDate').value;
            const btn = document.getElementById('submitBtn');
            const statusEl = document.getElementById('reportStatus');

            if (!title) {{
                alert('Please enter a work title.');
                return;
            }}

            btn.disabled = true;
            btn.textContent = 'Analyzing satellite imagery...';
            statusEl.className = 'status-msg processing';
            statusEl.textContent = '⏳ Fetching satellite imagery and running change detection analysis...';

            try {{
                const body = {{
                    title: title,
                    description: desc,
                    latitude: pinLat,
                    longitude: pinLon
                }};
                if (dateVal) {{
                    body.estimated_start_date = dateVal;
                }}

                const resp = await fetch('/api/community/report', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(body)
                }});
                const data = await resp.json();

                if (data.status === 'success') {{
                    statusEl.className = 'status-msg success';
                    statusEl.textContent = '✅ Audit complete — Verdict: ' + data.verdict;
                    window.open(data.evidence_card_url, '_blank');
                    setTimeout(() => window.location.reload(), 2500);
                }} else {{
                    statusEl.className = 'status-msg error';
                    statusEl.textContent = '❌ ' + (data.detail || JSON.stringify(data));
                }}
            }} catch (err) {{
                statusEl.className = 'status-msg error';
                statusEl.textContent = '❌ Request failed: ' + err.message;
            }} finally {{
                btn.disabled = false;
                btn.textContent = 'Run Satellite Audit';
            }}
        }}

        // ---- Scan Tender Folder ----
        async function scanFolder() {{
            const btn = document.getElementById('scanBtn');
            const statusEl = document.getElementById('scanStatus');

            btn.disabled = true;
            btn.textContent = 'Scanning...';
            statusEl.className = 'status-msg processing';
            statusEl.textContent = '⏳ Scanning tender folder and running satellite audits...';

            try {{
                const resp = await fetch('/api/audit/scan-folder', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }}
                }});
                const data = await resp.json();

                if (data.status === 'success') {{
                    statusEl.className = 'status-msg success';
                    statusEl.textContent = '✅ ' + data.message;
                    setTimeout(() => window.location.reload(), 2000);
                }} else {{
                    statusEl.className = 'status-msg error';
                    statusEl.textContent = '❌ ' + (data.message || JSON.stringify(data));
                }}
            }} catch (err) {{
                statusEl.className = 'status-msg error';
                statusEl.textContent = '❌ Scan failed: ' + err.message;
            }} finally {{
                btn.disabled = false;
                btn.textContent = 'Scan & Audit';
            }}
        }}

        // ---- Clear History ----
        async function clearHistory() {{
            if (!confirm('Clear all audited project records?')) return;
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
            estimated_start_date=request.estimated_start_date
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
