"""
EduPulse Analytics - Class Marks Entry Routes
"""
import uuid
import json
import logging
from flask import Blueprint, render_template, request, jsonify, Response, current_app, redirect, url_for
from storage.local_storage import LocalStorage
from services.class_entry_service import ClassEntryService

class_bp = Blueprint("class_entry", __name__, url_prefix="/class-entry")
logger = logging.getLogger(__name__)


def get_service() -> ClassEntryService:
    storage = LocalStorage()
    return ClassEntryService(storage=storage)


@class_bp.route("/")
def index():
    """Renders the editable class marks spreadsheet grid."""
    return render_template("class_entry.html")


@class_bp.route("/api/drafts", methods=["GET"])
def list_drafts():
    """API endpoint: Lists existing saved drafts."""
    storage = LocalStorage()
    drafts = storage.list_drafts()
    return jsonify({"status": "success", "drafts": drafts})


@class_bp.route("/api/draft/save", methods=["POST"])
def save_draft():
    """API endpoint: Saves in-progress class marks entry draft."""
    data = request.get_json() or {}
    draft_id = data.get("draft_id") or str(uuid.uuid4())
    data["draft_id"] = draft_id
    data["updated_at"] = data.get("updated_at") or ""

    storage = LocalStorage()
    storage.save_draft(draft_id, data)
    return jsonify({
        "status": "success",
        "draft_id": draft_id,
        "message": "Draft saved successfully"
    })


@class_bp.route("/api/draft/<draft_id>", methods=["GET"])
def load_draft(draft_id: str):
    """API endpoint: Loads an existing draft."""
    storage = LocalStorage()
    draft = storage.get_draft(draft_id)
    if not draft:
        return jsonify({"error": "Draft not found"}), 404
    return jsonify({"status": "success", "draft": draft})


@class_bp.route("/api/draft/<draft_id>", methods=["DELETE"])
def delete_draft(draft_id: str):
    """API endpoint: Deletes a draft."""
    storage = LocalStorage()
    success = storage.delete_draft(draft_id)
    if not success:
        return jsonify({"error": "Failed to delete draft"}), 400
    return jsonify({"status": "success", "message": "Draft deleted"})


@class_bp.route("/api/validate", methods=["POST"])
def validate_entry():
    """API endpoint: Pre-commit validation and pass/fail summary calculation."""
    data = request.get_json() or {}
    class_meta = data.get("metadata", {})
    subjects = data.get("subjects", [])
    student_rows = data.get("students", [])

    service = get_service()
    try:
        _, tally, summary = service.unpivot_and_validate(
            class_metadata=class_meta,
            subjects=subjects,
            student_rows=student_rows
        )
        return jsonify({
            "status": "success",
            "tally": tally.to_dict(),
            "summary": summary
        })
    except Exception as e:
        logger.error(f"Error validating class entry: {e}")
        return jsonify({"error": str(e)}), 400


@class_bp.route("/api/commit", methods=["POST"])
def commit_entry():
    """API endpoint: Commits class entry to lakehouse with manifest."""
    data = request.get_json() or {}
    class_meta = data.get("metadata", {})
    subjects = data.get("subjects", [])
    student_rows = data.get("students", [])
    draft_id = data.get("draft_id")
    comments = data.get("comments", "")

    service = get_service()
    try:
        manifest = service.commit_class_entry(
            class_metadata=class_meta,
            subjects=subjects,
            student_rows=student_rows,
            draft_id=draft_id,
            comments=comments
        )
        return jsonify({
            "status": "success",
            "dataset_id": manifest["dataset_id"],
            "manifest": manifest,
            "redirect_url": url_for("data.catalog")
        })
    except Exception as e:
        logger.error(f"Error committing class entry: {e}")
        return jsonify({"error": f"Failed to commit class entry: {str(e)}"}), 500


@class_bp.route("/api/export-csv", methods=["POST"])
def export_csv():
    """API endpoint: Exports current table state to CSV."""
    data = request.get_json() or {}
    subjects = data.get("subjects", [])
    student_rows = data.get("students", [])

    service = get_service()
    csv_text = service.generate_csv_template(subjects, student_rows)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=class_marks_template.csv"}
    )


@class_bp.route("/api/import-csv", methods=["POST"])
def import_csv():
    """API endpoint: Ingests an existing spreadsheet into the editable table."""
    if "file" not in request.files:
        return jsonify({"error": "No CSV file uploaded"}), 400

    file = request.files["file"]
    subjects_json = request.form.get("subjects", "[]")

    try:
        subjects = json.loads(subjects_json)
        csv_text = file.read().decode("utf-8")
        service = get_service()
        student_rows = service.parse_csv_into_grid(csv_text, subjects)
        return jsonify({
            "status": "success",
            "students": student_rows,
            "count": len(student_rows)
        })
    except Exception as e:
        logger.error(f"Error importing CSV into grid: {e}")
        return jsonify({"error": f"Failed to parse CSV: {str(e)}"}), 400
