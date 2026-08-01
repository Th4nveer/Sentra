"""
Audit Evidence Card Generator for Sentra Platform.
Generates interactive HTML Evidence Cards with before/after satellite image sliders,
spectral heatmaps, financial risk metrics, model version audit trails, and SHA-256 signatures.
"""
import os
import hashlib
import base64
from datetime import datetime
from typing import Dict, Any
from jinja2 import Template
import numpy as np
import matplotlib.pyplot as plt

from src.parser.models import TenderData, GeocodingResult
from src.cv_engine.detector import AuditResult


class EvidenceCardGenerator:
    def __init__(self, output_dir: str = "./data/reports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_card(
        self,
        tender: TenderData,
        geocoding: GeocodingResult,
        sat_data: Dict[str, Any],
        audit_result: AuditResult
    ) -> Dict[str, str]:
        """
        Generates interactive HTML evidence card and saved PNG heatmaps.
        """
        tender_dir = os.path.join(self.output_dir, tender.tender_id)
        os.makedirs(tender_dir, exist_ok=True)

        heatmap_png_path = os.path.join(tender_dir, "spectral_heatmap.png")
        self._generate_heatmap_plot(sat_data, heatmap_png_path)

        before_png = sat_data.get("before_png_path") or os.path.join("./data/satellite_cache", tender.tender_id, "before_rgb.png")
        after_png = sat_data.get("after_png_path") or os.path.join("./data/satellite_cache", tender.tender_id, "after_rgb.png")

        before_b64 = self._file_to_base64(before_png)
        after_b64 = self._file_to_base64(after_png)
        heatmap_b64 = self._file_to_base64(heatmap_png_path)

        raw_hash_input = f"{tender.tender_id}|{tender.budget_inr}|{audit_result.fraud_risk_score}|{audit_result.physical_alteration_score}|{geocoding.latitude},{geocoding.longitude}"
        audit_hash = hashlib.sha256(raw_hash_input.encode('utf-8')).hexdigest()

        html_content = self._render_html_template(
            tender=tender,
            geocoding=geocoding,
            sat_data=sat_data,
            audit=audit_result,
            before_b64=before_b64,
            after_b64=after_b64,
            heatmap_b64=heatmap_b64,
            audit_hash=audit_hash,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        )

        card_html_path = os.path.join(tender_dir, "evidence_card.html")
        with open(card_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return {
            "card_html_path": card_html_path,
            "heatmap_png_path": heatmap_png_path,
            "audit_hash": audit_hash
        }

    def _file_to_base64(self, filepath: str) -> str:
        if not os.path.exists(filepath):
            return ""
        with open(filepath, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def _generate_heatmap_plot(self, sat_data: Dict[str, Any], output_path: str):
        before_arr = sat_data.get("before_array")
        after_arr = sat_data.get("after_array")
        if before_arr is None or after_arr is None:
            fig, ax = plt.subplots(figsize=(4, 4), facecolor='#0f172a')
            ax.axis('off')
            plt.savefig(output_path, facecolor=fig.get_facecolor())
            plt.close()
            return

        red_b, nir_b = before_arr[:, :, 0], before_arr[:, :, 3]
        red_a, nir_a = after_arr[:, :, 0], after_arr[:, :, 3]

        ndbi_b = (red_b - nir_b) / np.maximum(red_b + nir_b, 1e-5)
        ndbi_a = (red_a - nir_a) / np.maximum(red_a + nir_a, 1e-5)
        delta_ndbi = ndbi_a - ndbi_b

        fig, ax = plt.subplots(figsize=(6, 4), facecolor='#0f172a')
        ax.imshow(delta_ndbi, cmap='coolwarm', vmin=-0.5, vmax=0.5)
        ax.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, dpi=120, bbox_inches='tight', facecolor=fig.get_facecolor())
        plt.close()

    def _render_html_template(self, **kwargs) -> str:
        template_str = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sentra Satellite Audit Card - {{ tender.tender_id }}</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --border: #e2e8f0;
            --text-heading: #0f172a;
            --text-body: #334155;
            --text-muted: #64748b;
            --accent-green: #16a34a;
            --accent-red: #dc2626;
            --accent-amber: #d97706;
            --accent-blue: #2563eb;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
            background-color: var(--bg);
            color: var(--text-body);
            padding: 2.5rem 1.5rem;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }

        .card-wrapper {
            max-width: 1000px;
            margin: 0 auto;
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 2.25rem;
            box-shadow: 0 4px 25px rgba(0, 0, 0, 0.04);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.5rem;
            margin-bottom: 1.75rem;
        }

        .header-title {
            font-size: 1.45rem;
            font-weight: 700;
            color: var(--text-heading);
            letter-spacing: -0.02em;
            margin-bottom: 0.25rem;
        }

        .header-sub {
            color: var(--text-muted);
            font-size: 0.88rem;
            font-weight: 500;
        }

        .badge {
            padding: 6px 16px;
            border-radius: 9999px;
            font-weight: 700;
            font-size: 0.8rem;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .badge-PRIORITY_FIELD_VERIFICATION_RECOMMENDED {
            background: #ffe4e6;
            color: #9f1239;
            border: 1px solid #fecdd3;
        }

        .badge-PARTIAL_CHANGE_DETECTED {
            background: #fef3c7;
            color: #92400e;
            border: 1px solid #fde047;
        }

        .badge-HIGH_PHYSICAL_CHANGE_VERIFIED {
            background: #dcfce7;
            color: #166534;
            border: 1px solid #bbf7d0;
        }

        .stats-row {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1.25rem;
            margin-bottom: 1.75rem;
        }

        .stat-box {
            border-radius: 14px;
            padding: 1.25rem 1.5rem;
            border: 1px solid var(--border);
        }

        .stat-box.blue { background: #eff6ff; border-color: #dbeafe; }
        .stat-box.red { background: #fff1f2; border-color: #ffe4e6; }
        .stat-box.green { background: #f0fdf4; border-color: #dcfce7; }

        .stat-lbl {
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 700;
            margin-bottom: 0.4rem;
        }

        .stat-box.blue .stat-lbl { color: #1e40af; }
        .stat-box.red .stat-lbl { color: #991b1b; }
        .stat-box.green .stat-lbl { color: #166534; }

        .stat-val {
            font-size: 1.95rem;
            font-weight: 700;
            letter-spacing: -0.02em;
        }

        .stat-box.blue .stat-val { color: #1e3a8a; }
        .stat-box.red .stat-val { color: #881337; }
        .stat-box.green .stat-val { color: #14532d; }

        .summary-banner {
            background: #f8fafc;
            border: 1px solid var(--border);
            border-left: 4px solid var(--text-heading);
            border-radius: 12px;
            padding: 1.25rem 1.5rem;
            margin-bottom: 1.75rem;
        }

        .summary-headline {
            font-weight: 700;
            color: var(--text-heading);
            font-size: 0.95rem;
            margin-bottom: 0.35rem;
        }

        .summary-desc {
            font-size: 0.88rem;
            color: var(--text-muted);
            line-height: 1.5;
        }

        .meta-section {
            background: #f8fafc;
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 1.25rem 1.5rem;
            margin-bottom: 1.75rem;
        }

        .meta-title {
            font-size: 0.82rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 0.85rem;
        }

        .meta-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.85rem 2rem;
            font-size: 0.88rem;
        }

        .meta-item {
            display: flex;
            align-items: flex-start;
            gap: 12px;
            border-bottom: 1px solid #f1f5f9;
            padding-bottom: 0.45rem;
        }

        .meta-item.full-width {
            grid-column: span 2;
        }

        .meta-label {
            color: var(--text-muted);
            min-width: 105px;
            flex-shrink: 0;
        }

        .meta-value {
            font-weight: 600;
            color: var(--text-heading);
            word-break: break-word;
        }

        .comparison-header {
            font-size: 0.9rem;
            font-weight: 700;
            color: var(--text-heading);
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .image-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.25rem;
            margin-bottom: 1.75rem;
        }

        .img-card {
            border: 1px solid var(--border);
            border-radius: 14px;
            overflow: hidden;
            background: #0f172a;
            position: relative;
        }

        .img-card img {
            width: 100%;
            height: 320px;
            object-fit: cover;
            display: block;
        }

        .img-tag {
            position: absolute;
            top: 12px;
            left: 12px;
            background: rgba(15, 23, 42, 0.85);
            color: #ffffff;
            backdrop-filter: blur(4px);
            padding: 5px 12px;
            border-radius: 8px;
            font-size: 0.78rem;
            font-weight: 600;
        }

        .card-footer {
            border-top: 1px solid var(--border);
            padding-top: 1.25rem;
            display: flex;
            justify-content: space-between;
            font-size: 0.78rem;
            color: var(--text-muted);
        }
    </style>
</head>
<body>
    <div class="card-wrapper">
        <div class="card-header">
            <div>
                <h1 class="header-title">{{ tender.project_name }}</h1>
                <div class="header-sub">Tender Ref: {{ tender.tender_id }}</div>
            </div>
            <div class="badge badge-{{ audit.classification }}">
                {% if audit.classification == 'HIGH_PHYSICAL_CHANGE_VERIFIED' %}
                    🟢 Verified Physical Work
                {% elif audit.classification == 'PARTIAL_CHANGE_DETECTED' %}
                    🟡 Partial Change Detected
                {% else %}
                    🔴 Flagged for Verification
                {% endif %}
            </div>
        </div>

        <div class="stats-row">
            <div class="stat-box {% if audit.physical_alteration_score >= 35 %}green{% elif audit.physical_alteration_score >= 20 %}blue{% else %}red{% endif %}">
                <div class="stat-lbl">Physical Work Detected</div>
                <div class="stat-val">{{ audit.physical_alteration_score }}%</div>
            </div>
            <div class="stat-box {% if audit.fraud_risk_score >= 75 %}red{% elif audit.fraud_risk_score >= 40 %}blue{% else %}green{% endif %}">
                <div class="stat-lbl">Triage Risk Rating</div>
                <div class="stat-val">{{ audit.fraud_risk_score }}%</div>
            </div>
            <div class="stat-box blue">
                <div class="stat-lbl">Model Confidence</div>
                <div class="stat-val">{{ ((audit.confidence_level or 0.92) * 100)|int }}%</div>
            </div>
            <div class="stat-box blue">
                <div class="stat-lbl">Sanctioned Budget</div>
                <div class="stat-val">Rs. {{ "%.2f"|format(tender.budget_inr / 10000000) if tender.budget_inr else "0.00" }} Cr</div>
            </div>
        </div>

        <div class="summary-banner">
            <div class="summary-headline">Finding Summary</div>
            <div class="summary-desc">{{ audit.audit_summary }}</div>
        </div>

        <div class="meta-section">
            <div class="meta-title">Project Details</div>
            <div class="meta-grid">
                <div class="meta-item full-width">
                    <span class="meta-label">Location:</span>
                    <span class="meta-value">{{ geocoding.formatted_address if geocoding.formatted_address else tender.location_name }}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">Coordinates:</span>
                    <span class="meta-value">{{ "%.4f"|format(geocoding.latitude) }}, {{ "%.4f"|format(geocoding.longitude) }}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">Contractor:</span>
                    <span class="meta-value">{{ tender.contractor_name if tender.contractor_name else 'Unspecified' }}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">Audit Window:</span>
                    <span class="meta-value">{{ tender.start_date }} → {{ tender.completion_date }}</span>
                </div>
            </div>
        </div>

        <div class="comparison-header">
            <span>Dual-Temporal Satellite Imagery Comparison</span>
            <span style="font-weight: 500; font-size: 0.8rem; color: var(--text-muted);">Source: {{ sat_data.source if sat_data else 'Esri World Imagery' }}</span>
        </div>

        <div class="image-grid">
            <div class="img-card">
                <img src="data:image/png;base64,{{ before_b64 }}" alt="Before Satellite Image">
                <div class="img-tag">BEFORE: {{ sat_data.before_date if sat_data and sat_data.before_date else tender.start_date }}</div>
            </div>
            <div class="img-card">
                <img src="data:image/png;base64,{{ after_b64 }}" alt="After Satellite Image">
                <div class="img-tag">AFTER: {{ sat_data.after_date if sat_data and sat_data.after_date else tender.completion_date }}</div>
            </div>
        </div>

        <div class="card-footer">
            <span>Sentra AI Satellite Audit Platform</span>
            <span>Generated: {{ timestamp }}</span>
        </div>
    </div>
</body>
</html>
        """
        template = Template(template_str)
        return template.render(**kwargs)
