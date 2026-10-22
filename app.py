"""
EduPulse Analytics - Master Application Factory & Server Entrypoint
"""
import logging
from typing import Optional
from flask import Flask
from config.settings import AppConfig, get_config
from dashboard.routes.core import core_bp
from dashboard.routes.data_management import data_bp
from dashboard.routes.class_entry import class_bp
from dashboard.routes.processing_monitor import monitor_bp
from dashboard.routes.dashboard import dash_bp
from dashboard.routes.academic_analysis import analysis_bp
from dashboard.routes.student_performance import student_bp
from dashboard.routes.reports import reports_bp
from dashboard.routes.settings import settings_bp

logger = logging.getLogger(__name__)


def create_app(config: Optional[AppConfig] = None) -> Flask:
    """
    Application Factory Pattern for EduPulse Analytics.
    Initializes configuration, logging filters, and blueprint routes.
    """
    if config is None:
        config = get_config()

    # Configure privacy-filtered logging
    config.setup_logging()
    logger.info("Initializing EduPulse Analytics Application Factory")

    app = Flask(
        __name__,
        template_folder="dashboard/templates",
        static_folder="dashboard/static"
    )

    # Core Flask Configuration
    app.config["SECRET_KEY"] = config.secret_key
    app.config["MAX_CONTENT_LENGTH"] = config.max_content_length
    app.config["DEBUG"] = config.debug
    app.config["EDUPULSE_CONFIG"] = config

    from dashboard.routes.projects import projects_bp, get_project_service

    # Register Blueprints
    app.register_blueprint(core_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(class_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(dash_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)

    @app.context_processor
    def inject_project_context():
        try:
            ps = get_project_service()
            all_p = ps.get_all_projects()
            active_p = ps.get_active_project()
            return dict(all_projects=all_p, active_project=active_p)
        except Exception:
            return dict(all_projects=[], active_project=None)

    logger.info(f"EduPulse Analytics initialized in {config.env} mode. Local storage ready.")
    return app


if __name__ == "__main__":
    app_config = get_config()
    application = create_app(app_config)
    print(f"\n=======================================================")
    print(f" EduPulse Analytics — Academic Big Data Platform")
    print(f" Local Web Server Running at: http://{app_config.host}:{app_config.port}")
    print(f" Press Ctrl+C to stop.")
    print(f"=======================================================\n")
    application.run(host=app_config.host, port=app_config.port, debug=app_config.debug)
