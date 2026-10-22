"""
EduPulse Analytics - Executive Dashboard Routes
"""
import json
import logging
from flask import Blueprint, render_template, request, jsonify
from services.analytics_service import AnalyticsService
from storage.local_storage import LocalStorage

dash_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")
logger = logging.getLogger(__name__)


def get_service() -> AnalyticsService:
    return AnalyticsService()


@dash_bp.route("/")
def index():
    """Renders the executive institutional performance dashboard."""
    service = get_service()
    storage = LocalStorage()
    manifests = storage.list_manifests()

    from flask import session
    from services.project_service import ProjectService

    ps = ProjectService()
    project_id = request.args.get("project_id") or session.get("active_project_id")
    if not project_id:
        active_p = ps.get_active_project()
        if active_p:
            project_id = active_p.get("project_id")

    if project_id and project_id != "ALL":
        p_dataset_ids = set(ps.get_project_dataset_ids(project_id))
        manifests = [m for m in manifests if m.get("dataset_id") in p_dataset_ids]

    selected_id = request.args.get("dataset_id")
    assessment_type = request.args.get("assessment_type", "ALL")

    if not manifests:
        selected_id = None
        analytics = None
    else:
        if not selected_id or (selected_id != "ALL" and selected_id not in [m["dataset_id"] for m in manifests]):
            selected_id = "ALL" if len(manifests) > 1 else (manifests[0]["dataset_id"] if manifests else None)
        analytics = service.get_dataset_analytics(selected_id, project_id=project_id, assessment_type=assessment_type)

    # Augment manifests with detected semester for dropdown display
    augmented_manifests = []
    for m in manifests:
        m_copy = dict(m)
        val_file = storage.config.validated_dir / f"VAL_{m['dataset_id']}.csv"
        detected_sem = None
        if val_file.exists():
            try:
                import pandas as pd
                df_head = pd.read_csv(val_file, nrows=10)
                if "semester" in df_head and not df_head["semester"].empty:
                    detected_sem = int(df_head["semester"].iloc[0])
            except Exception:
                pass
        m_copy["detected_semester"] = detected_sem
        augmented_manifests.append(m_copy)

    augmented_manifests.sort(key=lambda x: (x.get("detected_semester") or 99, x.get("dataset_id", "")))

    return render_template(
        "dashboard.html",
        manifests=augmented_manifests,
        selected_id=selected_id,
        selected_assessment_type=assessment_type,
        analytics=analytics
    )
