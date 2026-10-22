"""
EduPulse Analytics - Processing Monitor & Batch Job Routes
"""
import logging
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify, current_app, url_for
from services.processing_service import ProcessingService
from src.data_generator import SyntheticDataGenerator
from storage.local_storage import LocalStorage
from src.auth_service import role_required

monitor_bp = Blueprint("monitor", __name__, url_prefix="/processing-monitor")
logger = logging.getLogger(__name__)


def get_job_service() -> ProcessingService:
    storage = LocalStorage()
    return ProcessingService(storage=storage)


@monitor_bp.route("/")
@role_required("admin")
def index():
    """Renders the PySpark Job Monitor & Synthetic Generator dashboard."""
    service = get_job_service()
    jobs = service.list_jobs()
    storage = LocalStorage()
    manifests = storage.list_manifests()
    return render_template(
        "processing_monitor.html",
        jobs=jobs,
        manifests=manifests
    )


@monitor_bp.route("/api/generate-synthetic", methods=["POST"])
@role_required("admin")
def generate_synthetic():
    """API endpoint: Generates scalable synthetic academic benchmark datasets."""
    data = request.get_json() or {}
    total_records = int(data.get("record_count", 10_000))
    model_type = data.get("model_type", "marks_based")
    seed = int(data.get("seed", 42))

    generator = SyntheticDataGenerator(seed=seed)
    try:
        if model_type == "marks_based":
            result = generator.generate_marks_dataset(total_records=total_records)
        else:
            result = generator.generate_grade_dataset(total_records=total_records)

        return jsonify({
            "status": "success",
            "result": result
        })
    except Exception as e:
        logger.error(f"Synthetic generation failed: {e}")
        return jsonify({"error": f"Failed to generate synthetic data: {str(e)}"}), 500


@monitor_bp.route("/api/launch-spark-job", methods=["POST"])
@role_required("admin")
def launch_spark_job():
    """API endpoint: Enqueues an asynchronous batch PySpark processing job."""
    data = request.get_json() or {}
    dataset_id = data.get("dataset_id")
    file_path = data.get("file_path")
    model_type = data.get("model_type", "marks_based")

    if not file_path or not Path(file_path).exists():
        return jsonify({"error": f"File does not exist: {file_path}"}), 400

    dataset_id = dataset_id or f"SYNTH_{Path(file_path).stem}"
    service = get_job_service()
    job_id = service.enqueue_spark_job(
        dataset_id=dataset_id,
        input_csv_path=file_path,
        model_type=model_type
    )

    return jsonify({
        "status": "success",
        "job_id": job_id,
        "message": "PySpark batch job enqueued successfully"
    })


@monitor_bp.route("/api/job/<job_id>/status")
def get_job_status(job_id: str):
    """API endpoint: Returns current job heartbeat for client polling."""
    service = get_job_service()
    status = service.get_job_status(job_id)
    if not status:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"status": "success", "job": status})
