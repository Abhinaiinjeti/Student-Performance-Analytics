"""
EduPulse Analytics - Route Blueprints
"""
from dashboard.routes.core import core_bp
from dashboard.routes.data_management import data_bp
from dashboard.routes.class_entry import class_bp
from dashboard.routes.processing_monitor import monitor_bp
from dashboard.routes.dashboard import dash_bp
from dashboard.routes.academic_analysis import analysis_bp
from dashboard.routes.student_performance import student_bp

__all__ = [
    "core_bp", "data_bp", "class_bp", "monitor_bp",
    "dash_bp", "analysis_bp", "student_bp"
]
