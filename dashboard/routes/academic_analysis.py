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

    project_id = request.args.get("project_id") or session.get("active_project_id")
    if project_id and project_id != "ALL":
        ps = ProjectService()
        proj = ps.get_project_by_id(project_id)
        if proj and proj.get("dataset_ids"):
            manifests = [m for m in manifests if m.get("dataset_id") in proj["dataset_ids"]]

    req_dataset_id = request.args.get("dataset_id")
    if not req_dataset_id:
        selected_id = "ALL" if len(manifests) > 1 else (manifests[0]["dataset_id"] if manifests else None)
    else:
        selected_id = req_dataset_id

    dept_filter = request.args.get("department", "ALL")
    sem_filter = int(request.args.get("semester", 0))
    asmt_filter = request.args.get("assessment_type", "ALL")

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
