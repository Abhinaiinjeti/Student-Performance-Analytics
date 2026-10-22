"""
EduPulse Analytics - Reports & Export Web Routes
Provides endpoints for downloading executive briefings and analytical CSV exports
with support for cohort batch scoping, multi-semester consolidated reports, and theory/lab filtering.
"""
import io
import logging
from flask import Blueprint, render_template, request, Response, jsonify, send_file, session
import pandas as pd
from storage.local_storage import LocalStorage
from services.analytics_service import AnalyticsService
from services.project_service import ProjectService
from src.report_generator import ReportGenerator

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")
logger = logging.getLogger(__name__)


def get_generator() -> ReportGenerator:
    return ReportGenerator()


@reports_bp.route("/")
def index():
    """Renders the reports dashboard with export options, assessment filter, and dataset selector."""
    storage = LocalStorage()
    manifests = storage.list_manifests()

    project_id = request.args.get("project_id") or session.get("active_project_id")
    if project_id and project_id != "ALL":
        ps = ProjectService()
        proj = ps.get_project_by_id(project_id)
        if proj and proj.get("dataset_ids"):
            manifests = [m for m in manifests if m.get("dataset_id") in proj["dataset_ids"]]

    selected_id = request.args.get("dataset_id")
    if not selected_id:
        selected_id = "ALL" if len(manifests) > 1 else (manifests[0]["dataset_id"] if manifests else None)

    assessment_type = request.args.get("assessment_type", "ALL")

    # Augment manifests with detected semester for dropdown display
    augmented_manifests = []
    for m in manifests:
        m_copy = dict(m)
        val_file = storage.config.validated_dir / f"VAL_{m['dataset_id']}.csv"
        detected_sem = None
        if val_file.exists():
            try:
                df_head = pd.read_csv(val_file, nrows=10)
                if "semester" in df_head and not df_head["semester"].empty:
                    detected_sem = int(df_head["semester"].iloc[0])
            except Exception:
                pass
        m_copy["detected_semester"] = detected_sem
        augmented_manifests.append(m_copy)

    augmented_manifests.sort(key=lambda x: (x.get("detected_semester") or 99, x.get("dataset_id", "")))

    return render_template(
        "reports.html",
        manifests=augmented_manifests,
        selected_id=selected_id,
        selected_assessment_type=assessment_type,
        project_id=project_id
    )


@reports_bp.route("/download/html")
def download_html():
    """Renders or downloads the standalone printable executive HTML briefing."""
    dataset_id = request.args.get("dataset_id")
    if not dataset_id:
        return "Dataset ID is required", 400

    project_id = request.args.get("project_id") or session.get("active_project_id")
    assessment_type = request.args.get("assessment_type", "ALL")

    generator = get_generator()
    html_content = generator.generate_executive_html(
        dataset_id,
        project_id=project_id,
        assessment_type=assessment_type
    )

    as_attachment = request.args.get("download", "0") == "1"
    headers = {}
    if as_attachment:
        slug = f"Cohort_{project_id}" if dataset_id == "ALL" and project_id else f"Dataset_{dataset_id}"
        headers["Content-Disposition"] = f'attachment; filename="Executive_Briefing_{slug}.html"'

    return Response(html_content, mimetype="text/html", headers=headers)


@reports_bp.route("/download/csv")
def download_csv():
    """Streams institutional CSV reports."""
    dataset_id = request.args.get("dataset_id")
    if not dataset_id:
        return jsonify({"status": "error", "message": "dataset_id is required"}), 400

    report_type = request.args.get("type", "subject")
    project_id = request.args.get("project_id") or session.get("active_project_id")
    assessment_type = request.args.get("assessment_type", "ALL")

    generator = get_generator()
    slug = f"Cohort_{project_id}" if dataset_id == "ALL" and project_id else dataset_id

    if report_type == "subject":
        csv_data = generator.generate_subject_summary_csv(
            dataset_id,
            project_id=project_id,
            assessment_type=assessment_type
        )
        filename = f"Subject_Summary_{slug}.csv"
    elif report_type == "ledger":
        csv_data = generator.generate_consolidated_student_ledger_csv(
            dataset_id,
            project_id=project_id,
            assessment_type=assessment_type
        )
        filename = f"Student_Consolidated_Ledger_{slug}.csv"
    elif report_type == "remedial":
        csv_data = generator.generate_backlogs_remedial_csv(
            dataset_id,
            project_id=project_id,
            assessment_type=assessment_type
        )
        filename = f"Backlog_Remedial_Action_List_{slug}.csv"
    elif report_type == "support":
        csv_data = generator.generate_support_indicators_csv(
            dataset_id,
            project_id=project_id,
            assessment_type=assessment_type
        )
        filename = f"Student_Support_Indicators_{slug}.csv"
    elif report_type == "audit":
        csv_data = generator.generate_validated_export_csv(dataset_id, project_id=project_id)
        filename = f"Validated_Dataset_{slug}.csv"
    else:
        return jsonify({"status": "error", "message": f"Unknown report type: {report_type}"}), 400

    if not csv_data:
        return jsonify({"status": "error", "message": "No data found for this report scope"}), 404

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
