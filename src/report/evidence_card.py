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

        before_b64 = self._file_to_base64(sat_data["before_png_path"])
        after_b64 = self._file_to_base64(sat_data["after_png_path"])
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
        before_arr = sat_data["before_array"]
        after_arr = sat_data["after_array"]

        red_b, nir_b = before_arr[:, :, 0], before_arr[:, :, 3]
        red_a, nir_a = after_arr[:, :, 0], after_arr[:, :, 3]

        ndbi_b = (red_b - nir_b) / np.maximum(red_b + nir_b, 1e-5)
        ndbi_a = (red_a - nir_a) / np.maximum(red_a + nir_a, 1e-5)
        delta_ndbi = ndbi_a - ndbi_b

        spectral_shift = np.sqrt(np.sum((after_arr - before_arr) ** 2, axis=2))

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5), facecolor='#0f172a')

        im1 = ax1.imshow(delta_ndbi, cmap='coolwarm', vmin=-0.5, vmax=0.5)
        ax1.set_title("Surface Asphalt / Built-Up Shift (Δ NDBI)", color='#f8fafc', fontsize=11, pad=10)
        ax1.axis('off')
        cbar1 = plt.colorbar(im1, ax=ax1, fraction=0.046, pad=0.04)
        cbar1.ax.tick_params(colors='#94a3b8')

        im2 = ax2.imshow(spectral_shift, cmap='inferno', vmin=0, vmax=0.3)
        ax2.set_title("Multispectral Magnitude Shift (|Δ Array|)", color='#f8fafc', fontsize=11, pad=10)
        ax2.axis('off')
        cbar2 = plt.colorbar(im2, ax=ax2, fraction=0.046, pad=0.04)
        cbar2.ax.tick_params(colors='#94a3b8')

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
        plt.close()

    def _render_html_template(self, **kwargs) -> str:
        template_str = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sentra Audit Evidence Card - {{ tender.tender_id }}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #090d16;
            --card-bg: #131b2e;
            --border: #1e293b;
            --accent-red: #ef4444;
            --accent-green: #10b981;
            --accent-yellow: #f59e0b;
            --accent-blue: #3b82f6;
            --text: #f8fafc;
            --muted: #94a3b8;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg);
            color: var(--text);
            padding: 2rem;
            line-height: 1.5;
        }

        .container {
            max-width: 1100px;
            margin: 0 auto;
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 2rem;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.5rem;
            margin-bottom: 1.5rem;
        }

        .title-area h1 {
            font-size: 1.6rem;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 0.25rem;
        }

        .subtitle { color: var(--muted); font-size: 0.88rem; }

        .badge {
            padding: 0.5rem 1rem;
            border-radius: 9999px;
            font-weight: 700;
            font-size: 0.78rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .badge-PRIORITY_FIELD_VERIFICATION_RECOMMENDED {
            background: rgba(239, 68, 68, 0.2);
            color: var(--accent-red);
            border: 1px solid var(--accent-red);
        }

        .badge-PARTIAL_CHANGE_DETECTED {
            background: rgba(245, 158, 11, 0.2);
            color: var(--accent-yellow);
            border: 1px solid var(--accent-yellow);
        }

        .badge-HIGH_PHYSICAL_CHANGE_VERIFIED {
            background: rgba(16, 185, 129, 0.2);
            color: var(--accent-green);
            border: 1px solid var(--accent-green);
        }

        .ethics-disclaimer {
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 10px;
            padding: 0.85rem 1.25rem;
            font-size: 0.82rem;
            color: #cbd5e1;
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1rem;
            margin-bottom: 1.5rem;
        }

        .metric-card {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.25rem;
            text-align: center;
        }

        .metric-label {
            font-size: 0.72rem;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.4rem;
        }

        .metric-value { font-size: 1.75rem; font-weight: 700; }

        .text-red { color: var(--accent-red); }
        .text-green { color: var(--accent-green); }
        .text-yellow { color: var(--accent-yellow); }
        .text-blue { color: var(--accent-blue); }

        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            margin-bottom: 1.5rem;
        }

        .image-box {
            background: #000;
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
            position: relative;
        }

        .image-box img {
            width: 100%;
            height: 270px;
            object-fit: cover;
            display: block;
        }

        .image-box .label {
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(0, 0, 0, 0.8);
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
        }

        .summary-box {
            background: rgba(30, 41, 59, 0.4);
            border-left: 4px solid var(--accent-blue);
            padding: 1.25rem;
            border-radius: 0 12px 12px 0;
            margin-bottom: 1.5rem;
        }

        .hash-footer {
            border-top: 1px solid var(--border);
            padding-top: 1rem;
            display: flex;
            justify-content: space-between;
            font-family: monospace;
            font-size: 0.72rem;
            color: var(--muted);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title-area">
                <h1>SENTRA AUDIT EVIDENCE CARD</h1>
                <div class="subtitle">{{ tender.project_name }} (Tender ID: {{ tender.tender_id }})</div>
            </div>
            <div class="badge badge-{{ audit.classification }}">
                {{ audit.classification.replace('_', ' ') }}
            </div>
        </div>

        <div class="ethics-disclaimer">
            <strong style="color:var(--accent-blue);">RESPONSIBLE-USE NOTICE:</strong>
            This Evidence Card is a probability-scored screening aid for human auditors (CAG / Vigilance). It does not constitute a final legal determination of fraud or non-completion.
        </div>

        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Triage Risk Score</div>
                <div class="metric-value {% if audit.fraud_risk_score >= 75 %}text-red{% elif audit.fraud_risk_score >= 40 %}text-yellow{% else %}text-green{% endif %}">
                    {{ audit.fraud_risk_score }}%
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Physical Alteration</div>
                <div class="metric-value {% if audit.physical_alteration_score < 20 %}text-red{% else %}text-green{% endif %}">
                    {{ audit.physical_alteration_score }}%
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Sanctioned Budget</div>
                <div class="metric-value text-blue">
                    Rs. {{ "%.2f"|format(tender.budget_inr / 10000000) }} Cr
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Model Confidence</div>
                <div class="metric-value text-muted">
                    {{ (audit.confidence_level * 100)|int }}%
                </div>
            </div>
        </div>

        <div class="summary-box">
            <strong style="color:#ffffff;">Hedged Verdict Advice:</strong> {{ audit.hedged_verdict_copy }}<br>
            <span style="color:var(--muted); font-size:0.88rem; margin-top:4px; display:inline-block;">{{ audit.audit_summary }}</span>
        </div>

        <div class="grid-2">
            <div>
                <h3 style="margin-bottom: 0.75rem; font-size:0.9rem; color:var(--muted);">TENDER & LOCATION METADATA</h3>
                <table style="width:100%; font-size:0.85rem; border-collapse:collapse;">
                    <tr><td style="padding:4px 0; color:var(--muted);">Department:</td><td><strong>{{ tender.department }}</strong></td></tr>
                    <tr><td style="padding:4px 0; color:var(--muted);">Project Type:</td><td><strong>{{ tender.project_type }}</strong></td></tr>
                    <tr><td style="padding:4px 0; color:var(--muted);">Contractor:</td><td><strong>{{ tender.contractor_name }}</strong></td></tr>
                    <tr><td style="padding:4px 0; color:var(--muted);">Audit Period:</td><td><strong>{{ tender.start_date }} to {{ tender.completion_date }}</strong></td></tr>
                    <tr><td style="padding:4px 0; color:var(--muted);">Geocoded Address:</td><td><strong>{{ geocoding.formatted_address }}</strong></td></tr>
                    <tr><td style="padding:4px 0; color:var(--muted);">Coordinates:</td><td><strong>{{ "%.4f"|format(geocoding.latitude) }}, {{ "%.4f"|format(geocoding.longitude) }}</strong></td></tr>
                </table>
            </div>
            <div>
                <h3 style="margin-bottom: 0.75rem; font-size:0.9rem; color:var(--muted);">SPECTRAL CHANGE ANALYSIS (RGB+NIR)</h3>
                <div class="image-box">
                    <img src="data:image/png;base64,{{ heatmap_b64 }}" alt="Spectral Shift Heatmap">
                    <div class="label">Multispectral Δ NDBI & Shift Map</div>
                </div>
            </div>
        </div>

        <h3 style="margin-bottom: 0.75rem; font-size:0.9rem; color:var(--muted);">DUAL-TEMPORAL SATELLITE COMPARISON ({{ sat_data.source if sat_data else 'Esri World Imagery' }})</h3>
        <div class="grid-2">
            <div class="image-box">
                <img src="data:image/png;base64,{{ before_b64 }}" alt="Pre-Project Satellite Crop">
                <div class="label">BEFORE: {{ sat_data.before_date if sat_data and sat_data.before_date else tender.start_date }}</div>
            </div>
            <div class="image-box">
                <img src="data:image/png;base64,{{ after_b64 }}" alt="Post-Project Satellite Crop">
                <div class="label">AFTER: {{ sat_data.after_date if sat_data and sat_data.after_date else tender.completion_date }}</div>
            </div>
        </div>

        <div class="hash-footer" style="margin-top:2rem;">
            <div>Audit Trail: <span style="color:#ffffff;">Model {{ audit.model_version }}</span> | SHA-256: <span style="color:#ffffff;">{{ audit_hash[:20] }}...</span></div>
            <div>Generated: {{ timestamp }}</div>
        </div>
    </div>
</body>
</html>
        """
        template = Template(template_str)
        return template.render(**kwargs)
