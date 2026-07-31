"""
Sentra: AI-Powered Satellite Audit for Public Infrastructure.
CLI & Main Orchestrator.
"""
import os
import sys
import argparse
from typing import List, Dict, Any

from src.parser.tender_parser import TenderParser
from src.parser.geocoder import Geocoder
from src.parser.folder_scanner import FolderScanner
from src.satellite.fetcher import SatelliteFetcher
from src.cv_engine.detector import ChangeDetectionPipeline
from src.report.evidence_card import EvidenceCardGenerator
from src.report.triage_dashboard import TriageDashboardGenerator
from src.report.record_store import save_record, load_all_records


def run_audit_on_text(tender_text: str, scenario_override: str = None) -> Dict[str, Any]:
    parser = TenderParser()
    geocoder = Geocoder()
    satellite_fetcher = SatelliteFetcher()
    cv_detector = ChangeDetectionPipeline()
    card_generator = EvidenceCardGenerator()

    # 1. Parse tender circular
    tender = parser.parse_text(tender_text)

    # Automatically set scenario for sample files if not specified
    if not scenario_override:
        if "0912" in tender.tender_id or "ghost" in tender_text.lower():
            scenario_override = "ghost_project"
        elif "0441" in tender.tender_id or "park" in tender.project_type:
            scenario_override = "genuine_completed"
        elif "0883" in tender.tender_id or "canal" in tender.project_type:
            scenario_override = "partial_work"
        else:
            scenario_override = "ghost_project"

    # 2. Geocode site
    geocoding = geocoder.geocode(tender.location_text)

    # 3. Fetch satellite imagery (RGB + NIR)
    sat_data = satellite_fetcher.fetch_dual_temporal_imagery(
        tender_id=tender.tender_id,
        bounding_box=geocoding.bounding_box,
        start_date=tender.start_date,
        completion_date=tender.completion_date,
        project_type=tender.project_type,
        scenario_override=scenario_override
    )

    # 4. Computer Vision Change Detection
    audit_res = cv_detector.analyze_change(
        tender_id=tender.tender_id,
        project_type=tender.project_type,
        budget_inr=tender.budget_inr,
        before_arr=sat_data["before_array"],
        after_arr=sat_data["after_array"]
    )

    # 5. Generate Evidence Card
    card_info = card_generator.generate_card(
        tender=tender,
        geocoding=geocoding,
        sat_data=sat_data,
        audit_result=audit_res
    )

    res = {
        "tender": tender,
        "geocoding": geocoding,
        "sat_data": sat_data,
        "audit": audit_res,
        "card_info": card_info
    }
    save_record(res)
    return res


def run_demo():
    print("=" * 80)
    print("      SENTRA: AI-POWERED SATELLITE AUDIT FOR PUBLIC INFRASTRUCTURE      ")
    print("=" * 80)

    sample_dir = "./data/sample_tenders"
    sample_files = [
        ("tender_001_ghost_road.txt", "ghost_project"),
        ("tender_002_verified_park.txt", "genuine_completed"),
        ("tender_003_partial_canal.txt", "partial_work")
    ]

    records = []
    dashboard_gen = TriageDashboardGenerator()

    for filename, scenario in sample_files:
        filepath = os.path.join(sample_dir, filename)
        if os.path.exists(filepath):
            print(f"\n[+] Processing Tender Document: {filename}...")
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
            res = run_audit_on_text(text, scenario_override=scenario)
            records.append(res)
            
            t = res["tender"]
            a = res["audit"]
            print(f"    Tender ID       : {t.tender_id}")
            print(f"    Project Name    : {t.project_name}")
            print(f"    Sanctioned Cost : Rs. {t.budget_inr:,.2f}")
            print(f"    Physical Change : {a.physical_alteration_score}%")
            print(f"    Fraud Risk Score: {a.fraud_risk_score}%")
            print(f"    Verdict Badge   : {a.classification}")
            print(f"    Evidence Card   : {res['card_info']['card_html_path']}")
        else:
            print(f"[-] Sample file not found: {filepath}")

    dash_path = dashboard_gen.generate_dashboard(records)
    print("\n" + "=" * 80)
    print(f"[SUCCESS] Audit completed for {len(records)} projects.")
    print(f"[SUMMARY DASHBOARD GENERATED]: {os.path.abspath(dash_path)}")
    print("=" * 80)


def run_scan():
    """
    Scans data/raw_tenders/ for uploaded tender documents, parses them,
    fetches satellite imagery, runs CV analysis, and generates evidence cards.
    """
    print("=" * 80)
    print("      SENTRA: SCANNING TENDER FOLDER FOR NEW DOCUMENTS      ")
    print("=" * 80)

    scanner = FolderScanner()
    geocoder = Geocoder()
    satellite_fetcher = SatelliteFetcher()
    cv_detector = ChangeDetectionPipeline()
    card_generator = EvidenceCardGenerator()
    dashboard_gen = TriageDashboardGenerator()

    pending = scanner.get_pending_count()
    print(f"\n[*] Found {pending} file(s) in data/raw_tenders/\n")

    if pending == 0:
        print("[!] No tender documents found. Drop PDFs, images, or text files into data/raw_tenders/")
        return

    results = scanner.scan()
    records = []

    for filepath, text, tender_data in results:
        try:
            print(f"\n[AUDIT] Running satellite audit for: {tender_data.tender_id} - {tender_data.project_name}".encode('ascii', errors='replace').decode('ascii'))
            print(f"        Location: {tender_data.location_text}".encode('ascii', errors='replace').decode('ascii'))
            print(f"        Dates: {tender_data.start_date} to {tender_data.completion_date}")

            geocoding = geocoder.geocode(tender_data.location_text)
            print(f"        Geocoded: ({geocoding.latitude}, {geocoding.longitude}) via {geocoding.geocoding_source}")

            sat_data = satellite_fetcher.fetch_dual_temporal_imagery(
                tender_id=tender_data.tender_id,
                bounding_box=geocoding.bounding_box,
                start_date=tender_data.start_date,
                completion_date=tender_data.completion_date,
                project_type=tender_data.project_type
            )

            audit_res = cv_detector.analyze_change(
                tender_id=tender_data.tender_id,
                project_type=tender_data.project_type,
                budget_inr=tender_data.budget_inr,
                before_arr=sat_data["before_array"],
                after_arr=sat_data["after_array"]
            )

            card_info = card_generator.generate_card(
                tender=tender_data,
                geocoding=geocoding,
                sat_data=sat_data,
                audit_result=audit_res
            )

            rec_item = {
                "tender": tender_data,
                "geocoding": geocoding,
                "sat_data": sat_data,
                "audit": audit_res,
                "card_info": card_info
            }
            records.append(rec_item)
            save_record(rec_item)

            print(f"        Physical Change : {audit_res.physical_alteration_score}%")
            print(f"        Fraud Risk      : {audit_res.fraud_risk_score}%")
            print(f"        Verdict         : {audit_res.classification}")
            print(f"        Evidence Card   : {card_info['card_html_path']}")

        except Exception as e:
            print(f"  [ERROR] Audit failed for {tender_data.tender_id}: {e}")

    all_records = load_all_records()
    if all_records:
        dash_path = dashboard_gen.generate_dashboard(all_records)
        print("\n" + "=" * 80)
        print(f"[SUCCESS] Audit completed for {len(records)} tender(s). Total database records: {len(all_records)}")
        print(f"[DASHBOARD]: {os.path.abspath(dash_path)}")
        print("=" * 80)
    else:
        print("\n[!] No tenders were successfully audited.")


def main():
    parser = argparse.ArgumentParser(description="Sentra CLI Satellite Audit Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Demo command
    demo_parser = subparsers.add_parser("demo", help="Run satellite audit on realistic demo tender dataset")

    # Single audit command
    audit_cmd = subparsers.add_parser("audit", help="Audit a tender document file")
    audit_cmd.add_argument("--file", type=str, help="Path to tender text file")
    audit_cmd.add_argument("--scenario", type=str, default=None, choices=["ghost_project", "genuine_completed", "partial_work"])

    # Scan command
    scan_cmd = subparsers.add_parser("scan", help="Scan data/raw_tenders/ folder and audit all documents")

    # Serve command
    serve_cmd = subparsers.add_parser("serve", help="Launch FastAPI Web Dashboard Server")
    serve_cmd.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()

    if args.command == "demo" or args.command is None:
        run_demo()
    elif args.command == "audit":
        if not args.file or not os.path.exists(args.file):
            print(f"Error: File '{args.file}' not found.")
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
        res = run_audit_on_text(text, scenario_override=args.scenario)
        print(f"\nAudit complete for {res['tender'].tender_id}. Verdict: {res['audit'].classification}")
        print(f"Evidence Card: {res['card_info']['card_html_path']}")
    elif args.command == "scan":
        run_scan()
    elif args.command == "serve":
        import uvicorn
        import socket

        def is_port_free(host: str, p: int) -> bool:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex((host, p)) != 0

        target_port = args.port
        if not is_port_free("127.0.0.1", target_port):
            if target_port == 8000:
                print(f"[!] Port 8000 is occupied by another service.")
                if is_port_free("127.0.0.1", 8080):
                    target_port = 8080
                else:
                    target_port = 8081
                print(f"[!] Automatically redirecting Sentra to http://127.0.0.1:{target_port}")

        print(f"Starting Sentra Web App on http://127.0.0.1:{target_port}...")
        uvicorn.run("src.api.app:app", host="127.0.0.1", port=target_port, reload=False)


if __name__ == "__main__":
    main()
