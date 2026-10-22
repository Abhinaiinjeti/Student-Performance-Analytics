"""
EduPulse Analytics - Configuration Package
"""
from config.settings import AppConfig, get_config
from config.assessment_rules import AssessmentRules

Config = AppConfig

__all__ = ["AppConfig", "Config", "get_config", "AssessmentRules"]
