"""
EduPulse Analytics - Settings & System Configuration Routes
Manages assessment rules, grade scale definitions, and storage/cloud policy visibility.
"""
import logging
from flask import Blueprint, render_template, request, jsonify
from config.assessment_rules import AssessmentRules, SubjectMarksRule
from config.settings import get_config
from storage.local_storage import LocalStorage

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")
logger = logging.getLogger(__name__)

# Master in-memory assessment rules registry
global_rules = AssessmentRules()


@settings_bp.route("/")
def index():
    """Renders the system configuration and assessment settings view."""
    config = get_config()
    storage = LocalStorage()
    manifest_count = len(storage.list_manifests())

    storage_stats = {
        "base_dir": str(config.storage.data_dir),
        "raw_dir": str(config.storage.raw_dir),
        "validated_dir": str(config.storage.validated_dir),
        "processed_dir": str(config.storage.processed_dir),
        "analytics_dir": str(config.storage.analytics_dir),
        "manifests_dir": str(config.storage.manifests_dir),
        "manifest_count": manifest_count
    }

    aws_stats = {
        "enabled": config.aws.enabled,
        "bucket": config.aws.bucket_name or "edupulse-analytics-lakehouse (Default)",
        "region": config.aws.region,
        "prefix": config.aws.prefix
    }

    return render_template(
        "settings.html",
        rules=global_rules.to_dict(),
        storage_stats=storage_stats,
        aws_stats=aws_stats
    )


@settings_bp.route("/api/rules", methods=["GET"])
def get_rules():
    """Returns the current active assessment rules as JSON."""
    return jsonify({
        "status": "success",
        "rules": global_rules.to_dict()
    })


@settings_bp.route("/api/rules", methods=["POST"])
def update_rules():
    """Updates default assessment rules thresholds."""
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON payload provided"}), 400

    try:
        if "marks_rule" in data:
            mr = data["marks_rule"]
            global_rules.default_marks_rule.max_internal = float(mr.get("max_internal", 40.0))
            global_rules.default_marks_rule.max_external = float(mr.get("max_external", 60.0))
            global_rules.default_marks_rule.min_internal_pass = float(mr.get("min_internal_pass", 16.0))
            global_rules.default_marks_rule.min_external_pass = float(mr.get("min_external_pass", 24.0))
            global_rules.default_marks_rule.min_total_pass = float(mr.get("min_total_pass", 40.0))

        if "grade_points" in data and isinstance(data["grade_points"], dict):
            for k, v in data["grade_points"].items():
                global_rules.grade_rule.grade_points[str(k).upper()] = float(v)

        logger.info("Assessment rules updated successfully.")
        return jsonify({
            "status": "success",
            "message": "Assessment rules updated successfully.",
            "rules": global_rules.to_dict()
        })
    except Exception as e:
        logger.error(f"Error updating assessment rules: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400
