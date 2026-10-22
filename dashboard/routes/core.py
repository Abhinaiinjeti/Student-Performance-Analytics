"""
EduPulse Analytics - Core Application Routes
"""
import logging
from flask import Blueprint, render_template, jsonify, current_app
from config.settings import get_config

core_bp = Blueprint("core", __name__)
logger = logging.getLogger(__name__)


@core_bp.route("/")
def landing():
    """Renders the EduPulse Analytics marketing landing page."""
    config = get_config()
    return render_template(
        "landing.html",
        app_name="EduPulse Analytics",
        aws_enabled=config.aws.enabled
    )


@core_bp.route("/health")
def health():
    """Health check endpoint providing environment and subsystem status."""
    config = get_config()
    
    # Check directory health
    storage_status = {}
    for attr, path in [
        ("raw", config.storage.raw_dir),
        ("validated", config.storage.validated_dir),
        ("processed", config.storage.processed_dir),
        ("manifests", config.storage.manifests_dir),
        ("jobs", config.storage.jobs_dir)
    ]:
        storage_status[attr] = path.exists() and path.is_dir()

    return jsonify({
        "status": "healthy",
        "service": "EduPulse Analytics",
        "phase": "Phase 1 - Baseline",
        "storage": storage_status,
        "spark": {
            "master": config.spark.master,
            "driver_memory": config.spark.driver_memory
        },
        "aws_s3_enabled": config.aws.enabled
    })
