"""
EduPulse Analytics - Student Performance Longitudinal Routes
"""
import logging
from flask import Blueprint, render_template, request, jsonify
from services.analytics_service import AnalyticsService
from src.auth_service import login_required, role_required

student_bp = Blueprint("student_performance", __name__, url_prefix="/student-performance")
logger = logging.getLogger(__name__)


def get_service() -> AnalyticsService:
    return AnalyticsService()


@student_bp.route("/")
@login_required
def index():
    """Renders the individual student longitudinal performance trajectory."""
    from flask import session
    from services.project_service import ProjectService

    service = get_service()
    ps = ProjectService()
    project_id = request.args.get("project_id") or session.get("active_project_id")
    if not project_id:
        active_p = ps.get_active_project()
        if active_p:
            project_id = active_p.get("project_id")

    student_id = request.args.get("student_id", "").strip()
    student_record = None

    if student_id:
        student_record = service.get_student_longitudinal_record(student_id, project_id=project_id)

    # Fetch sample students and full ID list for datalist autocomplete
    sample_students = service.get_sample_students(limit=10, project_id=project_id)
    all_sample_entries = service.get_sample_students(limit=500, project_id=project_id)
    all_student_ids = [s["student_id"] for s in all_sample_entries]

    return render_template(
        "student_performance.html",
        searched_id=student_id,
        record=student_record,
        sample_students=sample_students,
        all_student_ids=all_student_ids
    )


@student_bp.route("/api/clear-backlog", methods=["POST"])
@role_required("admin", "faculty")
def clear_backlog():
    """Endpoint to update and clear a student's backlog record."""
    service = get_service()
    data = request.get_json(silent=True) or request.form.to_dict()

    student_id = data.get("student_id", "").strip()
    subject_code = data.get("subject_code", "").strip()
    letter_grade = data.get("letter_grade", "").strip().upper()

    if not student_id or not subject_code or not letter_grade:
        return jsonify({
            "status": "error",
            "message": "Missing required fields: student_id, subject_code, letter_grade."
        }), 400

    grade_points_raw = data.get("grade_points")
    grade_points_map = {
        "O": 10.0, "A+": 9.0, "A": 8.0, "B+": 7.0, "B": 6.0, "C": 5.0, "P": 4.0
    }
    try:
        if grade_points_raw is not None and str(grade_points_raw).strip() != "":
            grade_points = float(grade_points_raw)
        else:
            grade_points = grade_points_map.get(letter_grade, 6.0)
    except (ValueError, TypeError):
        grade_points = grade_points_map.get(letter_grade, 6.0)

    semester_raw = data.get("semester")
    semester = None
    if semester_raw is not None and str(semester_raw).strip() != "":
        try:
            semester = int(semester_raw)
        except (ValueError, TypeError):
            semester = None

    updated_sgpa_raw = data.get("updated_sgpa")
    updated_sgpa = None
    if updated_sgpa_raw is not None and str(updated_sgpa_raw).strip() != "":
        try:
            updated_sgpa = float(updated_sgpa_raw)
        except (ValueError, TypeError):
            updated_sgpa = None

    remarks = data.get("remarks")

    try:
        result = service.clear_student_backlog(
            student_id=student_id,
            subject_code=subject_code,
            new_letter_grade=letter_grade,
            new_grade_points=grade_points,
            semester=semester,
            updated_sgpa=updated_sgpa,
            remarks=remarks
        )
        return jsonify({
            "status": "success",
            "message": f"Successfully cleared backlog in course {subject_code} with Grade {letter_grade}.",
            "result": result
        }), 200
    except ValueError as ve:
        return jsonify({
            "status": "error",
            "message": str(ve)
        }), 404
    except Exception as e:
        logger.error(f"Failed to clear backlog for student {student_id}: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": f"Server error while clearing backlog: {str(e)}"
        }), 500

