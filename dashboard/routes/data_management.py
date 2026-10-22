"""
EduPulse Analytics - Data Management & Import Wizard Routes
Handles inspection, preview, validation, and commitment of academic assessment spreadsheets
across Wide and Long layouts and diverse assessment types.
"""
import json
import logging
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for
from storage.local_storage import LocalStorage
from src.import_service import ImportService
from src.data_validation import DataValidationService

data_bp = Blueprint("data", __name__, url_prefix="/data-management")
logger = logging.getLogger(__name__)


def get_import_service() -> ImportService:
    storage = LocalStorage()
    validation = DataValidationService()
    return ImportService(storage=storage, validation=validation)


@data_bp.route("/")
def catalog():
    """Renders the Dataset Library & Catalog with registered manifests."""
    storage = LocalStorage()
    manifests = storage.list_manifests()
    return render_template(
        "data_management.html",
        manifests=manifests,
        total_datasets=len(manifests)
    )


@data_bp.route("/import")
@data_bp.route("/import-wizard")
def import_wizard():
    """Renders the Universal Guided Spreadsheet Import Wizard."""
    return render_template("import_wizard.html")


@data_bp.route("/api/inspect", methods=["POST"])
def inspect_file():
    """API endpoint: Uploads and inspects workbook structure, sheets, layouts & headers."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    file_bytes = file.read()
    if len(file_bytes) == 0:
        return jsonify({"error": "Uploaded file is empty"}), 400

    service = get_import_service()
    try:
        inspection = service.inspect_file(file_bytes, file.filename)
        return jsonify({"status": "success", "inspection": inspection})
    except Exception as e:
        logger.error(f"Error inspecting spreadsheet: {e}")
        return jsonify({"error": f"Failed to inspect spreadsheet: {str(e)}"}), 500


@data_bp.route("/api/preview", methods=["POST"])
def preview_mapping():
    """API endpoint: Generates live preview with unpivoting and validation scorecard."""
    if "file" not in request.files:
        return jsonify({"error": "File required for preview"}), 400

    file = request.files["file"]
    form_data = request.form

    try:
        sheet_name = form_data.get("sheet_name", "Sheet1")
        header_row = int(form_data.get("header_row", 0))
        model_type = form_data.get("model_type", "marks_based")
        layout = form_data.get("layout", "auto")
        student_id_col = form_data.get("student_id_col") or None
        student_name_col = form_data.get("student_name_col") or None
        assessment_type = form_data.get("assessment_type", "mid_1")
        
        subject_cols_raw = form_data.get("subject_cols")
        subject_cols = json.loads(subject_cols_raw) if subject_cols_raw else None
        
        default_max_marks = float(form_data.get("default_max_marks")) if form_data.get("default_max_marks") else None
        default_pass_marks = float(form_data.get("default_pass_marks")) if form_data.get("default_pass_marks") else None
        default_semester = int(form_data.get("default_semester", 1))
        default_department = form_data.get("default_department", "General")

        column_mappings = json.loads(form_data.get("mappings", "{}"))

        file_bytes = file.read()
        service = get_import_service()
        preview = service.generate_preview(
            file_bytes=file_bytes,
            filename=file.filename,
            sheet_name=sheet_name,
            header_row=header_row,
            column_mappings=column_mappings,
            model_type=model_type,
            layout=layout,
            student_id_col=student_id_col,
            subject_cols=subject_cols,
            student_name_col=student_name_col,
            assessment_type=assessment_type,
            default_max_marks=default_max_marks,
            default_pass_marks=default_pass_marks,
            default_semester=default_semester,
            default_department=default_department,
            max_rows=25
        )
        return jsonify({"status": "success", "preview": preview})
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        return jsonify({"error": f"Failed to generate preview: {str(e)}"}), 500


@data_bp.route("/api/commit", methods=["POST"])
def commit_dataset():
    """API endpoint: Commits validated dataset (unpivoting if wide) and generates manifest."""
    if "file" not in request.files:
        return jsonify({"error": "File required for commit"}), 400

    file = request.files["file"]
    form_data = request.form

    try:
        sheet_name = form_data.get("sheet_name", "Sheet1")
        header_row = int(form_data.get("header_row", 0))
        model_type = form_data.get("model_type", "marks_based")
        layout = form_data.get("layout", "auto")
        student_id_col = form_data.get("student_id_col") or None
        student_name_col = form_data.get("student_name_col") or None
        assessment_type = form_data.get("assessment_type", "mid_1")
        
        subject_cols_raw = form_data.get("subject_cols")
        subject_cols = json.loads(subject_cols_raw) if subject_cols_raw else None
        
        default_max_marks = float(form_data.get("default_max_marks")) if form_data.get("default_max_marks") else None
        default_pass_marks = float(form_data.get("default_pass_marks")) if form_data.get("default_pass_marks") else None
        default_semester = int(form_data.get("default_semester", 1))
        default_department = form_data.get("default_department", "General")
        comments = form_data.get("comments", "")
        project_id = form_data.get("project_id") or session.get("active_project_id")

        column_mappings = json.loads(form_data.get("mappings", "{}"))

        file_bytes = file.read()
        service = get_import_service()
        manifest = service.commit_import(
            file_bytes=file_bytes,
            original_filename=file.filename,
            sheet_name=sheet_name,
            header_row=header_row,
            column_mappings=column_mappings,
            model_type=model_type,
            layout=layout,
            student_id_col=student_id_col,
            subject_cols=subject_cols,
            student_name_col=student_name_col,
            assessment_type=assessment_type,
            default_max_marks=default_max_marks,
            default_pass_marks=default_pass_marks,
            default_semester=default_semester,
            default_department=default_department,
            comments=comments,
            project_id=project_id
        )
        return jsonify({
            "status": "success",
            "dataset_id": manifest["dataset_id"],
            "manifest": manifest,
            "redirect_url": url_for("data.catalog")
        })
    except Exception as e:
        logger.error(f"Error committing dataset import: {e}")
        return jsonify({"error": f"Import failed: {str(e)}"}), 500


@data_bp.route("/api/manifest/<dataset_id>")
def get_manifest_json(dataset_id: str):
    """API endpoint: Returns cryptographic manifest for a dataset."""
    storage = LocalStorage()
    manifest = storage.get_manifest(dataset_id)
    if not manifest:
        return jsonify({"error": "Manifest not found"}), 404
    return jsonify(manifest)


@data_bp.route("/api/dataset/<dataset_id>", methods=["DELETE", "POST"])
def remove_dataset(dataset_id: str):
    """API endpoint: Permanently removes a dataset and its associated files."""
    storage = LocalStorage()
    manifest = storage.get_manifest(dataset_id)
    if not manifest:
        return jsonify({"error": "Dataset not found"}), 404

    try:
        success = storage.delete_dataset(dataset_id)
        if success:
            logger.info(f"Dataset {dataset_id} removed successfully.")
            return jsonify({
                "status": "success",
                "message": f"Dataset {dataset_id} removed successfully.",
                "dataset_id": dataset_id
            })
        else:
            return jsonify({"error": "Could not remove dataset files"}), 500
    except Exception as e:
        logger.error(f"Error removing dataset {dataset_id}: {e}")
        return jsonify({"error": f"Failed to remove dataset: {str(e)}"}), 500


@data_bp.route("/api/datasets/delete-all", methods=["DELETE", "POST"])
def remove_all_datasets():
    """API endpoint: Permanently removes all datasets and associated lakehouse artifacts."""
    storage = LocalStorage()
    try:
        deleted_count = storage.delete_all_datasets()
        logger.info(f"Purge complete: {deleted_count} dataset(s) removed.")
        return jsonify({
            "status": "success",
            "message": f"Successfully removed {deleted_count} dataset(s) from lakehouse.",
            "deleted_count": deleted_count
        })
    except Exception as e:
        logger.error(f"Error purging all datasets: {e}")
        return jsonify({"error": f"Failed to remove all datasets: {str(e)}"}), 500

