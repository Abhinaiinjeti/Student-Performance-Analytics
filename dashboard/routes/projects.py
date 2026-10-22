"""
EduPulse Analytics - Academic Batch Projects & Cohort Workspace Routes
"""
import logging
from flask import Blueprint, request, jsonify, redirect, url_for, session, flash
from services.project_service import ProjectService
from src.auth_service import login_required, role_required

projects_bp = Blueprint("projects", __name__, url_prefix="/projects")
logger = logging.getLogger(__name__)


def get_project_service() -> ProjectService:
    return ProjectService()


@projects_bp.route("/api/list", methods=["GET"])
@login_required
def list_projects():
    """Returns all registered academic batch projects."""
    service = get_project_service()
    projects = service.get_all_projects()
    active = service.get_active_project()
    return jsonify({
        "status": "success",
        "projects": projects,
        "active_project": active
    })


@projects_bp.route("/api/create", methods=["POST"])
@role_required("admin", "faculty")
def create_project():
    """Creates a new batch project (e.g. 2023 - 2027 Batch)."""
    service = get_project_service()
    data = request.get_json(silent=True) or request.form.to_dict()

    name = data.get("name", "").strip()
    start_year_raw = data.get("start_year")
    end_year_raw = data.get("end_year")
    department = data.get("department", "Computer Science & Engineering").strip()
    department_code = data.get("department_code", "CSE").strip()
    degree = data.get("degree", "B.Tech").strip()
    regulation = data.get("regulation", "R20 / Autonomous").strip()
    description = data.get("description", "").strip()
    set_active = data.get("set_active", True) in [True, "true", "True", "1", 1]

    if not name or not start_year_raw or not end_year_raw:
        return jsonify({
            "status": "error",
            "message": "Project name, start year, and end year are required."
        }), 400

    try:
        start_year = int(start_year_raw)
        end_year = int(end_year_raw)
        if end_year <= start_year:
            return jsonify({
                "status": "error",
                "message": "Graduation year must be greater than start year."
            }), 400

        project = service.create_project(
            name=name,
            start_year=start_year,
            end_year=end_year,
            department=department,
            department_code=department_code,
            degree=degree,
            regulation=regulation,
            description=description,
            set_active=set_active
        )

        session["active_project_id"] = project["project_id"]

        if request.is_json:
            return jsonify({
                "status": "success",
                "message": f"Successfully created project '{name}'!",
                "project": project
            }), 201
        else:
            flash(f"Created cohort project '{name}' successfully!", "success")
            return redirect(request.referrer or url_for("core.landing"))

    except Exception as e:
        logger.error(f"Failed to create project: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": f"Failed to create project: {str(e)}"
        }), 500


@projects_bp.route("/api/select", methods=["POST"])
@login_required
def select_active_project():
    """Switches the active academic batch project."""
    service = get_project_service()
    data = request.get_json(silent=True) or request.form.to_dict()
    project_id = data.get("project_id", "").strip()

    if not project_id:
        return jsonify({"status": "error", "message": "project_id is required"}), 400

    success = service.set_active_project(project_id)
    if success:
        session["active_project_id"] = project_id
        if request.is_json:
            return jsonify({
                "status": "success",
                "message": "Active project updated",
                "active_project": service.get_project_by_id(project_id)
            })
        else:
            return redirect(request.referrer or url_for("core.landing"))
    else:
        return jsonify({"status": "error", "message": "Project not found"}), 404


@projects_bp.route("/api/delete/<project_id>", methods=["POST", "DELETE"])
@role_required("admin", "faculty")
def delete_project(project_id: str):
    """Deletes an academic batch project."""
    service = get_project_service()
    success = service.delete_project(project_id)
    if success:
        if session.get("active_project_id") == project_id:
            active = service.get_active_project()
            session["active_project_id"] = active.get("project_id", active.get("id")) if active else None
        return jsonify({
            "status": "success",
            "message": f"Batch project {project_id} deleted."
        })
    return jsonify({"status": "error", "message": "Project not found"}), 404
