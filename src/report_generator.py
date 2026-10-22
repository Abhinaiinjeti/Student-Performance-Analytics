"""
EduPulse Analytics - Report Generator Engine
Generates print-ready HTML executive briefings and standardized CSV analytical exports.
Supports cohort project workspaces, multi-semester combined views, theory vs lab filtering,
and institutional verification signature blocks.
"""
import io
import re
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd

from storage.local_storage import LocalStorage
from services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)

SUBJECT_NAME_LOOKUP = {
    "BDA": "Big Data Analytics",
    "ML": "Machine Learning",
    "CC": "Cloud Computing",
    "MAD": "Mobile Application Development",
    "STM": "Software Testing Methodologies",
    "BDA&CC LAB": "Big Data & Cloud Computing Laboratory",
    "MAD LAB": "Mobile Application Development Laboratory",
    "DAA": "Design & Analysis of Algorithms",
    "OS": "Operating Systems",
    "DBMS": "Database Management Systems",
    "CN": "Computer Networks",
    "AI": "Artificial Intelligence",
    "WT": "Web Technologies",
    "FLAT": "Formal Languages & Automata Theory",
    "SE": "Software Engineering",
    "COA": "Computer Organization & Architecture"
}


def resolve_subject_name(code: str, existing_name: Optional[str] = None) -> str:
    """Returns a readable full subject title from code or known abbreviations."""
    if existing_name and existing_name.strip() and existing_name.strip().upper() != str(code).strip().upper():
        return existing_name.strip()
    c_upper = str(code).strip().upper()
    if c_upper in SUBJECT_NAME_LOOKUP:
        return f"{c_upper} ({SUBJECT_NAME_LOOKUP[c_upper]})"
    return str(code).strip()


class ReportGenerator:
    """
    Produces executive briefings and analytical CSV exports from processed academic datasets.
    """
    def __init__(self, storage: Optional[LocalStorage] = None, analytics_service: Optional[AnalyticsService] = None):
        self.storage = storage or LocalStorage()
        self.analytics = analytics_service or AnalyticsService(storage=self.storage)

    def generate_executive_html(
        self,
        dataset_id: str,
        project_id: Optional[str] = None,
        assessment_type: Optional[str] = None
    ) -> str:
        """
        Generates a standalone, print-ready HTML briefing document formatted for executive review.
        """
        analytics_data = self.analytics.get_dataset_analytics(
            dataset_id,
            project_id=project_id,
            assessment_type=assessment_type
        )
        if not analytics_data:
            return "<html><body><h1>Error: Dataset not found or not processed</h1></body></html>"

        manifest = analytics_data.get("manifest") or {}
        summary = analytics_data.get("summary") or {}
        subjects = analytics_data.get("subjects") or []
        indicators = analytics_data.get("support_indicators") or []
        model_type = analytics_data.get("model_type", "marks_based")
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Project Cohort Context
        project_name = None
        if project_id and project_id != "ALL":
            try:
                from services.project_service import ProjectService
                ps = ProjectService()
                proj = ps.get_project_by_id(project_id)
                if proj:
                    project_name = proj.get("name")
            except Exception:
                pass

        # Document Title / Header
        filename = (manifest.get("source_file") or {}).get("original_filename") or dataset_id
        if dataset_id == "ALL":
            report_title = f"Consolidated Cohort Academic Performance Briefing"
            scope_desc = f"Institutional Multi-Semester Record ({project_name or 'All Batches Combined'})"
        else:
            report_title = f"Academic Performance Executive Briefing"
            scope_desc = f"Target Evaluation: {filename}"

        filter_label = "All Evaluations"
        if assessment_type and assessment_type != "ALL":
            filter_label = {
                "THEORY": "Theory Courses Only",
                "LABORATORY": "Laboratory / Practical Evaluations",
                "SEMESTER_EXAM": "Semester End Examinations",
                "INTERNAL": "Internal & Mid Evaluations"
            }.get(assessment_type.upper(), assessment_type)

        # Generate subject rows
        subject_rows = []
        for s in subjects:
            pass_rate = s.get("pass_rate", 0.0)
            avg_score = s.get("average_marks", "N/A")
            diff_idx = s.get("difficulty_index", "N/A")
            diff_badge = f"{diff_idx:.2f}" if isinstance(diff_idx, (int, float)) else "N/A"
            raw_code = s.get("subject_code", "")
            raw_name = s.get("subject_name", "")
            full_title = resolve_subject_name(raw_code, raw_name)
            is_lab = bool(re.search(r"\b(LAB|PRACTICAL|PR|WORKSHOP)\b", raw_code, re.IGNORECASE))
            type_badge = '<span style="background:#dcfce7; color:#166534; font-size:10px; padding:2px 6px; border-radius:4px; font-weight:600;">LAB</span>' if is_lab else '<span style="background:#e0f2fe; color:#0369a1; font-size:10px; padding:2px 6px; border-radius:4px; font-weight:600;">THEORY</span>'

            subject_rows.append(f"""
                <tr>
                    <td><strong>{raw_code}</strong></td>
                    <td>{full_title}</td>
                    <td style="text-align: center;">{type_badge}</td>
                    <td style="text-align: right;">{s.get('total_students', 0):,}</td>
                    <td style="text-align: right; color: #059669; font-weight:600;">{s.get('passed', 0):,}</td>
                    <td style="text-align: right; color: #dc2626; font-weight:600;">{s.get('failed', 0):,}</td>
                    <td style="text-align: right;"><strong>{pass_rate:.1f}%</strong></td>
                    <td style="text-align: right;">{avg_score}</td>
                    <td style="text-align: center;"><span class="badge">{diff_badge}</span></td>
                </tr>
            """)
        subjects_html = "\n".join(subject_rows) if subject_rows else "<tr><td colspan='9'>No subjects recorded matching filter.</td></tr>"

        # Generate support indicators rows
        indicator_rows = []
        for ind in indicators[:35]:  # Top 35 diagnostic flags
            sev = ind.get("severity", "MEDIUM")
            sev_color = "#dc2626" if sev == "HIGH" else "#d97706"
            indicator_rows.append(f"""
                <tr>
                    <td><strong>{ind.get('student_id', '')}</strong></td>
                    <td>{ind.get('department', 'General')}</td>
                    <td style="text-align: center;">Sem {ind.get('semester', 1)}</td>
                    <td><span style="color: {sev_color}; font-weight: 700;">{ind.get('flag_type', '')}</span></td>
                    <td>{ind.get('reason', '')}</td>
                    <td><em>{ind.get('action_recommended', '')}</em></td>
                </tr>
            """)
        indicators_html = "\n".join(indicator_rows) if indicator_rows else "<tr><td colspan='6'>No student support alerts triggered.</td></tr>"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{report_title} — {dataset_id}</title>
    <style>
        @page {{ size: A4 portrait; margin: 12mm; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            color: #1e293b;
            line-height: 1.45;
            background-color: #ffffff;
            margin: 0;
            padding: 24px;
        }}
        .header {{
            border-bottom: 3px solid #2563eb;
            padding-bottom: 14px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
        }}
        .header h1 {{ margin: 0; font-size: 22px; color: #0f172a; font-weight: 800; }}
        .header p {{ margin: 4px 0 0 0; color: #64748b; font-size: 13px; }}
        .meta-box {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 20px;
            font-size: 12px;
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
        }}
        .meta-item strong {{ display: block; color: #475569; font-size: 11px; text-transform: uppercase; margin-bottom: 2px; }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 14px;
            margin-bottom: 22px;
        }}
        .kpi-card {{
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 12px 14px;
            background: #ffffff;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        }}
        .kpi-card span {{ font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600; display: block; }}
        .kpi-card h2 {{ margin: 4px 0 0 0; font-size: 22px; font-weight: 700; color: #0f172a; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 11.5px;
            margin-bottom: 24px;
        }}
        th {{
            background: #f1f5f9;
            color: #334155;
            text-align: left;
            padding: 8px 10px;
            font-weight: 600;
            border-bottom: 2px solid #cbd5e1;
            font-size: 11px;
            text-transform: uppercase;
        }}
        td {{
            padding: 8px 10px;
            border-bottom: 1px solid #e2e8f0;
        }}
        .badge {{
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            background: #e2e8f0;
            font-weight: 600;
            font-size: 10.5px;
        }}
        h3 {{
            font-size: 15px;
            margin: 20px 0 10px 0;
            color: #0f172a;
            border-left: 4px solid #2563eb;
            padding-left: 8px;
            font-weight: 700;
        }}
        .footer {{
            border-top: 1px solid #e2e8f0;
            padding-top: 10px;
            margin-top: 30px;
            font-size: 11px;
            color: #94a3b8;
            text-align: center;
        }}
        .signatures {{
            margin-top: 40px;
            padding-top: 16px;
            border-top: 1px dashed #cbd5e1;
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            text-align: center;
            font-size: 11px;
            color: #475569;
            page-break-inside: avoid;
        }}
        @media print {{
            body {{ padding: 0; }}
            .no-print {{ display: none !important; }}
            tr {{ page-break-inside: avoid; }}
        }}
    </style>
</head>
<body>
    <div class="no-print" style="margin-bottom: 16px; display: flex; justify-content: flex-end; gap: 8px;">
        <button onclick="window.print()" style="background: #2563eb; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;">
            🖨️ Print / Save as PDF
        </button>
    </div>

    <div class="header">
        <div>
            <h1>EduPulse Analytics — Executive Academic Briefing</h1>
            <p>{report_title} &bull; {scope_desc}</p>
        </div>
        <div style="text-align: right;">
            <p style="margin: 0; font-size: 12px;"><strong>Security Classification:</strong> Confidential Academic Record</p>
            <p style="margin: 2px 0 0 0; font-size: 11px; color: #64748b;">Generated: {generated_at}</p>
        </div>
    </div>

    <div class="meta-box">
        <div class="meta-item">
            <strong>Cohort Workspace</strong>
            <span style="font-weight: 600; color: #2563eb;">{project_name or 'Default Campus'}</span>
        </div>
        <div class="meta-item">
            <strong>Evaluation Model / Scope</strong>
            <span>{model_type.replace('_', ' ').title()} ({filter_label})</span>
        </div>
        <div class="meta-item">
            <strong>Total Students Evaluated</strong>
            <span>{summary.get('unique_students', 0):,}</span>
        </div>
        <div class="meta-item">
            <strong>Total Courses Evaluated</strong>
            <span>{summary.get('unique_subjects', 0):,} courses</span>
        </div>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <span>Overall Pass Rate</span>
            <h2 style="color: #059669;">{summary.get('pass_percentage', 0.0):.1f}%</h2>
        </div>
        <div class="kpi-card">
            <span>Evaluated Enrollments</span>
            <h2>{summary.get('total_records', 0):,}</h2>
        </div>
        <div class="kpi-card">
            <span>Passed Enrollments</span>
            <h2 style="color: #059669;">{summary.get('passed_count', 0):,}</h2>
        </div>
        <div class="kpi-card">
            <span>Failed / Backlog</span>
            <h2 style="color: #dc2626;">{summary.get('failed_count', 0):,}</h2>
        </div>
    </div>

    <h3>Course-Level Academic Performance & Difficulty Index</h3>
    <table>
        <thead>
            <tr>
                <th style="width: 12%;">Course Code</th>
                <th style="width: 32%;">Subject Title</th>
                <th style="text-align: center; width: 10%;">Type</th>
                <th style="text-align: right; width: 8%;">Enrolled</th>
                <th style="text-align: right; width: 8%;">Passed</th>
                <th style="text-align: right; width: 8%;">Failed</th>
                <th style="text-align: right; width: 8%;">Pass %</th>
                <th style="text-align: right; width: 8%;">Mean Score</th>
                <th style="text-align: center; width: 6%;">Difficulty</th>
            </tr>
        </thead>
        <tbody>
            {subjects_html}
        </tbody>
    </table>

    <h3>Transparent Student Support Indicators (Top Diagnostic Flags)</h3>
    <table>
        <thead>
            <tr>
                <th style="width: 16%;">Student ID</th>
                <th style="width: 12%;">Department</th>
                <th style="text-align: center; width: 8%;">Semester</th>
                <th style="width: 18%;">Diagnostic Flag</th>
                <th style="width: 26%;">Objective Criterion Triggered</th>
                <th style="width: 20%;">Recommended Academic Intervention</th>
            </tr>
        </thead>
        <tbody>
            {indicators_html}
        </tbody>
    </table>

    <div class="signatures">
        <div>
            <div style="height: 38px;"></div>
            <div style="border-top: 1px solid #94a3b8; padding-top: 4px;">
                <strong>Faculty Advisor / Course Coordinator</strong>
            </div>
        </div>
        <div>
            <div style="height: 38px;"></div>
            <div style="border-top: 1px solid #94a3b8; padding-top: 4px;">
                <strong>Head of Department (HOD)</strong>
            </div>
        </div>
        <div>
            <div style="height: 38px;"></div>
            <div style="border-top: 1px solid #94a3b8; padding-top: 4px;">
                <strong>Principal / Controller of Examinations</strong>
            </div>
        </div>
    </div>

    <div class="footer">
        <p>EduPulse Analytics &bull; Cloud-Based Student Performance Analytics &bull; FERPA/DPDP Compliance Verified &bull; Zero PII Leakage</p>
    </div>
</body>
</html>"""
        return html

    def generate_subject_summary_csv(
        self,
        dataset_id: str,
        project_id: Optional[str] = None,
        assessment_type: Optional[str] = None
    ) -> str:
        """
        Exports subject-level statistics as a standard CSV string.
        """
        analytics_data = self.analytics.get_dataset_analytics(
            dataset_id,
            project_id=project_id,
            assessment_type=assessment_type
        )
        if not analytics_data:
            return ""

        subjects = analytics_data.get("subjects", [])
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "subject_code", "subject_name", "subject_type", "total_students",
            "passed", "failed", "absent", "pass_rate", "average_marks",
            "median_marks", "std_dev", "difficulty_index"
        ])

        for s in subjects:
            raw_code = s.get("subject_code", "")
            raw_name = s.get("subject_name", "")
            full_title = resolve_subject_name(raw_code, raw_name)
            is_lab = bool(re.search(r"\b(LAB|PRACTICAL|PR|WORKSHOP)\b", raw_code, re.IGNORECASE))
            stype = "LABORATORY" if is_lab else "THEORY"

            writer.writerow([
                raw_code,
                full_title,
                stype,
                s.get("total_students", 0),
                s.get("passed", 0),
                s.get("failed", 0),
                s.get("absent", 0),
                s.get("pass_rate", 0.0),
                s.get("average_marks", ""),
                s.get("median_marks", ""),
                s.get("std_dev", ""),
                s.get("difficulty_index", "")
            ])

        return output.getvalue()

    def generate_support_indicators_csv(
        self,
        dataset_id: str,
        project_id: Optional[str] = None,
        assessment_type: Optional[str] = None
    ) -> str:
        """
        Exports rule-based student support indicators as a CSV string.
        """
        analytics_data = self.analytics.get_dataset_analytics(
            dataset_id,
            project_id=project_id,
            assessment_type=assessment_type
        )
        if not analytics_data:
            return ""

        indicators = analytics_data.get("support_indicators", [])
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "student_id", "department", "semester", "flag_type",
            "severity", "reason", "action_recommended"
        ])

        for ind in indicators:
            writer.writerow([
                ind.get("student_id", ""),
                ind.get("department", ""),
                ind.get("semester", ""),
                ind.get("flag_type", ""),
                ind.get("severity", ""),
                ind.get("reason", ""),
                ind.get("action_recommended", "")
            ])

        return output.getvalue()

    def generate_consolidated_student_ledger_csv(
        self,
        dataset_id: str,
        project_id: Optional[str] = None,
        assessment_type: Optional[str] = None
    ) -> str:
        """
        Exports a consolidated student roster ledger:
        Roll Number, Department, Courses Evaluated, Passed, Failed, SGPA/Percentage, Result Status.
        """
        manifests = self.storage.list_manifests()
        if project_id and project_id != "ALL":
            try:
                from services.project_service import ProjectService
                ps = ProjectService()
                proj = ps.get_project_by_id(project_id)
                if proj and proj.get("dataset_ids"):
                    manifests = [m for m in manifests if m.get("dataset_id") in proj["dataset_ids"]]
            except Exception:
                pass

        dfs = []
        if dataset_id == "ALL":
            for m in manifests:
                v_path = self.storage.config.validated_dir / f"VAL_{m['dataset_id']}.csv"
                if v_path.exists():
                    try:
                        dfs.append(pd.read_csv(v_path))
                    except Exception:
                        pass
        else:
            v_path = self.storage.config.validated_dir / f"VAL_{dataset_id}.csv"
            if v_path.exists():
                try:
                    dfs.append(pd.read_csv(v_path))
                except Exception:
                    pass

        if not dfs:
            return ""

        df = pd.concat(dfs, ignore_index=True)

        # Apply assessment_type filter if applicable
        if assessment_type and assessment_type != "ALL":
            asmt_upper = str(assessment_type).upper()
            if asmt_upper == "THEORY" and "subject_code" in df:
                df = df[~df["subject_code"].astype(str).str.contains("LAB|PRACTICAL|PR", case=False, na=False)]
            elif asmt_upper in ("LABORATORY", "LAB") and "subject_code" in df:
                df = df[df["subject_code"].astype(str).str.contains("LAB|PRACTICAL|PR", case=False, na=False)]

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "student_id", "department", "total_evaluations",
            "passed_evaluations", "failed_backlogs", "mean_score_or_sgpa", "result_status"
        ])

        if "student_id" not in df:
            return output.getvalue()

        # Group by student
        for stu_id, grp in df.groupby("student_id"):
            dept = grp["department"].iloc[0] if "department" in grp and not grp["department"].empty else "General"
            total = len(grp)
            
            # Count passed / failed
            if "status" in grp:
                passed = (grp["status"].str.upper() == "PASS").sum()
            elif "grade_status" in grp:
                passed = (grp["grade_status"].str.upper() == "PASSED").sum()
            else:
                passed = total
            failed = total - passed

            # Average score or SGPA
            score_val = ""
            if "sgpa" in grp and pd.notna(grp["sgpa"]).any():
                score_val = f"{grp['sgpa'].dropna().mean():.2f}"
            elif "total_marks" in grp and pd.notna(grp["total_marks"]).any():
                score_val = f"{grp['total_marks'].dropna().mean():.1f}"

            result = "PASSED" if failed == 0 else f"BACKLOG ({failed})"

            writer.writerow([
                stu_id,
                dept,
                total,
                passed,
                failed,
                score_val,
                result
            ])

        return output.getvalue()

    def generate_backlogs_remedial_csv(
        self,
        dataset_id: str,
        project_id: Optional[str] = None,
        assessment_type: Optional[str] = None
    ) -> str:
        """
        Exports remedial action sheet for all students with backlogs.
        """
        manifests = self.storage.list_manifests()
        if project_id and project_id != "ALL":
            try:
                from services.project_service import ProjectService
                ps = ProjectService()
                proj = ps.get_project_by_id(project_id)
                if proj and proj.get("dataset_ids"):
                    manifests = [m for m in manifests if m.get("dataset_id") in proj["dataset_ids"]]
            except Exception:
                pass

        dfs = []
        if dataset_id == "ALL":
            for m in manifests:
                v_path = self.storage.config.validated_dir / f"VAL_{m['dataset_id']}.csv"
                if v_path.exists():
                    try:
                        dfs.append(pd.read_csv(v_path))
                    except Exception:
                        pass
        else:
            v_path = self.storage.config.validated_dir / f"VAL_{dataset_id}.csv"
            if v_path.exists():
                try:
                    dfs.append(pd.read_csv(v_path))
                except Exception:
                    pass

        if not dfs:
            return ""

        df = pd.concat(dfs, ignore_index=True)

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "student_id", "department", "semester", "subject_code",
            "subject_name", "letter_grade_or_marks", "remedial_recommendation"
        ])

        # Find failing rows
        fail_mask = pd.Series([False] * len(df))
        if "status" in df:
            fail_mask = fail_mask | (df["status"].str.upper() != "PASS")
        if "grade_status" in df:
            fail_mask = fail_mask | (df["grade_status"].str.upper() != "PASSED")

        failing_df = df[fail_mask]
        for _, row in failing_df.iterrows():
            stu_id = row.get("student_id", "")
            dept = row.get("department", "General")
            sem = row.get("semester", 1)
            code = row.get("subject_code", "")
            name = resolve_subject_name(code, row.get("subject_name", ""))
            score = row.get("letter_grade") or row.get("total_marks") or "F"
            rec = "Remedial tutorial sessions and supplementary examination registration required"

            writer.writerow([stu_id, dept, sem, code, name, score, rec])

        return output.getvalue()

    def generate_validated_export_csv(self, dataset_id: str, project_id: Optional[str] = None) -> str:
        """
        Retrieves the cleaned, sanitized CSV content for this dataset or combines all datasets.
        """
        if dataset_id == "ALL":
            manifests = self.storage.list_manifests()
            if project_id and project_id != "ALL":
                try:
                    from services.project_service import ProjectService
                    ps = ProjectService()
                    proj = ps.get_project_by_id(project_id)
                    if proj and proj.get("dataset_ids"):
                        manifests = [m for m in manifests if m.get("dataset_id") in proj["dataset_ids"]]
                except Exception:
                    pass
            dfs = []
            for m in manifests:
                v_path = self.storage.config.validated_dir / f"VAL_{m['dataset_id']}.csv"
                if v_path.exists():
                    try:
                        dfs.append(pd.read_csv(v_path))
                    except Exception:
                        pass
            if not dfs:
                return ""
            combined_df = pd.concat(dfs, ignore_index=True)
            return combined_df.to_csv(index=False)
        else:
            val_path = self.storage.config.validated_dir / f"VAL_{dataset_id}.csv"
            if not val_path.exists():
                return ""
            return val_path.read_text(encoding="utf-8")
