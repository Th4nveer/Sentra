"""
Triage Dashboard Generator for Sentra Audit Platform.
Renders executive dashboard displaying probability-ranked triage queue for auditors.
"""
import os
from typing import List, Dict, Any
from jinja2 import Template


class TriageDashboardGenerator:
    def __init__(self, output_dir: str = "./data/reports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_dashboard(self, audit_records: List[Dict[str, Any]]) -> str:
        """
        Generates index.html triage queue dashboard following PRD specifications.
        """
        # Sort records by fraud risk score descending (highest budget x lowest change first)
        sorted_records = sorted(audit_records, key=lambda x: x["audit"].fraud_risk_score, reverse=True)

        total_audited = len(sorted_records)
        ghost_projects_count = sum(1 for r in sorted_records if r["audit"].classification == "PRIORITY_FIELD_VERIFICATION_RECOMMENDED")
        partial_count = sum(1 for r in sorted_records if r["audit"].classification == "PARTIAL_CHANGE_DETECTED")
        verified_count = sum(1 for r in sorted_records if r["audit"].classification == "HIGH_PHYSICAL_CHANGE_VERIFIED")
        
        flagged_leakage_inr = sum(
            r["tender"].budget_inr for r in sorted_records 
            if r["audit"].classification in ["PRIORITY_FIELD_VERIFICATION_RECOMMENDED", "PARTIAL_CHANGE_DETECTED"]
        )

        template_str = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SENTRA - AI Satellite Audit Triage Queue</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0b0f19;
            --card-bg: #151d30;
            --border: #1e293b;
            --accent-red: #ef4444;
            --accent-yellow: #f59e0b;
            --accent-green: #10b981;
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
        }

        .header {
            max-width: 1200px;
            margin: 0 auto 1.5rem auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .brand h1 {
            font-size: 1.8rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            background: linear-gradient(135deg, #ef4444 0%, #f59e0b 50%, #3b82f6 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .brand p { color: var(--muted); font-size: 0.88rem; }

        .disclaimer-banner {
            max-width: 1200px;
            margin: 0 auto 1.5rem auto;
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 10px;
            padding: 0.75rem 1.25rem;
            font-size: 0.82rem;
            color: #cbd5e1;
        }

        .stats-grid {
            max-width: 1200px;
            margin: 0 auto 2rem auto;
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1.25rem;
        }

        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.25rem;
        }

        .stat-title { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; margin-bottom: 0.4rem; }
        .stat-val { font-size: 1.75rem; font-weight: 700; }

        .table-container {
            max-width: 1200px;
            margin: 0 auto;
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            overflow: hidden;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }

        th {
            background: rgba(15, 23, 42, 0.8);
            padding: 1rem;
            font-size: 0.75rem;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 1px solid var(--border);
        }

        td {
            padding: 1rem;
            border-bottom: 1px solid var(--border);
            font-size: 0.88rem;
        }

        tr:hover { background: rgba(30, 41, 59, 0.4); }

        .badge {
            padding: 0.35rem 0.75rem;
            border-radius: 9999px;
            font-weight: 600;
            font-size: 0.72rem;
            display: inline-block;
        }

        .badge-PRIORITY_FIELD_VERIFICATION_RECOMMENDED { background: rgba(239, 68, 68, 0.2); color: var(--accent-red); border: 1px solid var(--accent-red); }
        .badge-PARTIAL_CHANGE_DETECTED { background: rgba(245, 158, 11, 0.2); color: var(--accent-yellow); border: 1px solid var(--accent-yellow); }
        .badge-HIGH_PHYSICAL_CHANGE_VERIFIED { background: rgba(16, 185, 129, 0.2); color: var(--accent-green); border: 1px solid var(--accent-green); }

        .btn-card {
            background: var(--accent-blue);
            color: #ffffff;
            text-decoration: none;
            padding: 0.4rem 0.8rem;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 600;
            display: inline-block;
        }
        .btn-card:hover { opacity: 0.9; }
    </style>
</head>
<body>
    <div class="header">
        <div class="brand">
            <h1>SENTRA AUDIT PLATFORM</h1>
            <p>Space-Borne AI Satellite Triage Queue for Human Auditors</p>
        </div>
    </div>

    <div class="disclaimer-banner">
        <strong style="color:var(--accent-blue);">HUMAN-IN-THE-LOOP SCREENING AID:</strong> Sentra produces a probability-scored triage queue ranking highest-budget, lowest-physical-change projects for priority field inspection. It never issues automated final verdicts of fraud.
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-title">Total Audited Projects</div>
            <div class="stat-val" style="color:var(--accent-blue);">{{ total_audited }}</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Priority Verification Flags</div>
            <div class="stat-val" style="color:var(--accent-red);">{{ ghost_projects_count }}</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Partial Work Alerts</div>
            <div class="stat-val" style="color:var(--accent-yellow);">{{ partial_count }}</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Flagged Budget Risk</div>
            <div class="stat-val" style="color:var(--accent-red);">Rs. {{ "%.2f"|format(flagged_leakage_inr / 10000000) }} Cr</div>
        </div>
    </div>

    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th>Tender ID</th>
                    <th>Project Name</th>
                    <th>Department</th>
                    <th>Budget</th>
                    <th>Physical Alteration</th>
                    <th>Triage Risk</th>
                    <th>Audit Status</th>
                    <th>Evidence Card</th>
                </tr>
            </thead>
            <tbody>
                {% for item in records %}
                <tr>
                    <td><strong>{{ item.tender.tender_id }}</strong></td>
                    <td>{{ item.tender.project_name }}</td>
                    <td>{{ item.tender.department }}</td>
                    <td>Rs. {{ "%.2f"|format(item.tender.budget_inr / 10000000) }} Cr</td>
                    <td>
                        <strong style="color:{% if item.audit.physical_alteration_score < 20 %}var(--accent-red){% else %}var(--accent-green){% endif %};">
                            {{ item.audit.physical_alteration_score }}%
                        </strong>
                    </td>
                    <td>
                        <strong style="color:{% if item.audit.fraud_risk_score >= 75 %}var(--accent-red){% elif item.audit.fraud_risk_score >= 40 %}var(--accent-yellow){% else %}var(--accent-green){% endif %};">
                            {{ item.audit.fraud_risk_score }}%
                        </strong>
                    </td>
                    <td>
                        <span class="badge badge-{{ item.audit.classification }}">
                            {{ item.audit.classification.replace('_', ' ') }}
                        </span>
                    </td>
                    <td>
                        <a class="btn-card" href="./{{ item.tender.tender_id }}/evidence_card.html" target="_blank">View Card</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
        """
        template = Template(template_str)
        rendered_html = template.render(
            total_audited=total_audited,
            ghost_projects_count=ghost_projects_count,
            partial_count=partial_count,
            verified_count=verified_count,
            flagged_leakage_inr=flagged_leakage_inr,
            records=sorted_records
        )

        dash_path = os.path.join(self.output_dir, "index.html")
        with open(dash_path, "w", encoding="utf-8") as f:
            f.write(rendered_html)

        return dash_path
