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
        "simulation_mode": getattr(config.aws, "simulation_mode", False),
        "bucket": config.aws.bucket_name or "",
        "region": config.aws.region,
        "prefix": config.aws.prefix,
        "access_key_id": config.aws.access_key_id or "",
        "has_secret": bool(config.aws.secret_access_key)
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


@settings_bp.route("/api/aws", methods=["POST"])
def update_aws_config_route():
    """API endpoint: Saves AWS Cloud Archiving settings and updates .env file."""
    from config.settings import save_env_config, AWSConfig
    from storage.s3_storage import S3StorageAdapter

    data = request.get_json() or {}
    try:
        enabled = bool(data.get("enabled", False))
        simulation_mode = bool(data.get("simulation_mode", False))
        region = (data.get("region") or "us-east-1").strip()
        bucket = (data.get("bucket_name") or "").strip()
        prefix = (data.get("prefix") or "archives/").strip()
        access_key = (data.get("access_key_id") or "").strip()
        secret_key = (data.get("secret_access_key") or "").strip()

        updates = {
            "AWS_ENABLED": "true" if enabled else "false",
            "AWS_SIMULATION_MODE": "true" if simulation_mode else "false",
            "AWS_REGION": region,
            "AWS_S3_BUCKET": bucket,
            "AWS_S3_PREFIX": prefix,
        }
        if access_key:
            updates["AWS_ACCESS_KEY_ID"] = access_key
        if secret_key:
            updates["AWS_SECRET_ACCESS_KEY"] = secret_key

        save_env_config(updates)
        cfg = get_config(reload=True)

        logger.info(f"AWS configuration updated (enabled={cfg.aws.enabled}, simulation={cfg.aws.simulation_mode})")
        return jsonify({
            "status": "success",
            "message": "AWS configuration saved successfully.",
            "aws": {
                "enabled": cfg.aws.enabled,
                "simulation_mode": getattr(cfg.aws, "simulation_mode", False),
                "region": cfg.aws.region,
                "bucket": cfg.aws.bucket_name,
                "prefix": cfg.aws.prefix,
                "has_access_key": bool(cfg.aws.access_key_id)
            }
        })
    except Exception as e:
        logger.error(f"Error saving AWS configuration: {e}")
        return jsonify({"status": "error", "message": f"Failed to save AWS settings: {str(e)}"}), 500


@settings_bp.route("/api/aws/test", methods=["POST"])
def test_aws_connection_route():
    """API endpoint: Tests live S3 connectivity or validates simulation environment."""
    from config.settings import AWSConfig
    from storage.s3_storage import S3StorageAdapter

    data = request.get_json() or {}
    try:
        current_cfg = get_config().aws
        enabled = bool(data.get("enabled", current_cfg.enabled))
        simulation_mode = bool(data.get("simulation_mode", getattr(current_cfg, "simulation_mode", False)))
        region = (data.get("region") or current_cfg.region).strip()
        bucket = (data.get("bucket_name") or current_cfg.bucket_name).strip()
        prefix = (data.get("prefix") or current_cfg.prefix).strip()
        access_key = (data.get("access_key_id") or current_cfg.access_key_id).strip()
        secret_key = (data.get("secret_access_key") or current_cfg.secret_access_key).strip()

        test_cfg = AWSConfig(
            enabled=enabled,
            simulation_mode=simulation_mode,
            region=region,
            bucket_name=bucket,
            prefix=prefix,
            access_key_id=access_key,
            secret_access_key=secret_key
        )
        adapter = S3StorageAdapter(config=test_cfg)
        result = adapter.test_connection()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error testing AWS connection: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

