import logging
import pandas as pd
from flask import Blueprint, render_template, request, jsonify
from services.analytics_service import AnalyticsService
from storage.local_storage import LocalStorage

analysis_bp = Blueprint("academic_analysis", __name__, url_prefix="/academic-analysis")
logger = logging.getLogger(__name__)


def get_service() -> AnalyticsService:
    return AnalyticsService()


@analysis_bp.route("/")
def index():
    """Renders the subject, semester, and department academic analysis view."""
    service = get_service()
    storage = LocalStorage()
    from flask import session
    from services.project_service import ProjectService

    manifests = storage.list_manifests()

    ps = ProjectService()
    project_id = request.args.get("project_id") or session.get("active_project_id")
    if not project_id:
        active_p = ps.get_active_project()
        if active_p:
            project_id = active_p.get("project_id")

    if project_id and project_id != "ALL":
        p_dataset_ids = set(ps.get_project_dataset_ids(project_id))
        manifests = [m for m in manifests if m.get("dataset_id") in p_dataset_ids]

    req_dataset_id = request.args.get("dataset_id")
    dept_filter = request.args.get("department", "ALL")
    sem_filter = int(request.args.get("semester", 0))
    asmt_filter = request.args.get("assessment_type", "ALL")

    if not manifests:
        selected_id = None
        analytics = None
        effective_id = None
        filter_options = {
            "departments": [],
            "semesters": [],
            "all_semesters": [],
            "all_departments": [],
            "assessment_types": service.get_available_filter_options(None).get("assessment_types", [])
        }
    else:
        if not req_dataset_id or (req_dataset_id != "ALL" and req_dataset_id not in [m["dataset_id"] for m in manifests]):
            selected_id = "ALL" if len(manifests) > 1 else (manifests[0]["dataset_id"] if manifests else None)
        else:
            selected_id = req_dataset_id

        analytics = service.get_filtered_analytics(
            dataset_id=selected_id,
            department=dept_filter,
            semester=sem_filter,
            project_id=project_id,
            assessment_type=asmt_filter
        )
        effective_id = analytics.get("dataset_id", selected_id) if analytics else selected_id
        filter_options = service.get_available_filter_options(selected_id, project_id=project_id)

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

    # Sort manifests chronologically by semester if detected
    augmented_manifests.sort(key=lambda x: (x.get("detected_semester") or 99, x.get("dataset_id", "")))

    return render_template(
        "academic_analysis.html",
        manifests=augmented_manifests,
        selected_id=effective_id,
        requested_id=selected_id,
        dept_filter=dept_filter,
        sem_filter=sem_filter,
        asmt_filter=asmt_filter,
        departments=filter_options["departments"],
        available_semesters=filter_options["all_semesters"],
        assessment_types=filter_options.get("assessment_types", []),
        analytics=analytics
    )
