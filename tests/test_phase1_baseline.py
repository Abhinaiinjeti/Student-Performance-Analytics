"""
EduPulse Analytics - Phase 1 Verification Tests
"""
import pytest
import logging
from config.settings import get_config, StudentDataMaskingFilter
from config.assessment_rules import AssessmentRules, SubjectMarksRule
from app import create_app


def test_config_initialization():
    """Verify configuration loads properly and creates directories."""
    config = get_config()
    assert config.storage.data_dir.exists()
    assert config.storage.raw_dir.exists()
    assert config.storage.validated_dir.exists()
    assert config.storage.processed_dir.exists()
    assert config.storage.manifests_dir.exists()
    assert config.storage.jobs_dir.exists()
    assert config.aws.enabled is False  # AWS must be disabled by default


def test_student_data_masking_filter():
    """Verify logger filter masks real student roll numbers and IDs."""
    mask_filter = StudentDataMaskingFilter()
    
    # Test roll number
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="Processing record for student STU-2026-99999 with result PASS",
        args=(), exc_info=None
    )
    mask_filter.filter(record)
    assert "STU-2026-99999" not in record.msg
    assert "ST***99" in record.msg or "***" in record.msg

    # Test college registration code
    record2 = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="Importing record 21BCSE0421 successfully",
        args=(), exc_info=None
    )
    mask_filter.filter(record2)
    assert "21BCSE0421" not in record2.msg
    assert "21***21" in record2.msg


def test_marks_assessment_rules():
    """Verify marks passing logic against default and custom rules."""
    rules = AssessmentRules()
    default_rule = rules.get_marks_rule("CS101")
    
    # 40% internal (16/40) + 40% external (24/60) + 40% total (40/100)
    status, total = default_rule.evaluate_result(internal=20.0, external=30.0)
    assert status == "PASS"
    assert total == 50.0

    # Failing external threshold
    status_fail, total_fail = default_rule.evaluate_result(internal=35.0, external=20.0)
    assert status_fail == "FAIL"
    assert total_fail == 55.0

    # Absent handling
    status_abs, total_abs = default_rule.evaluate_result(internal=30.0, external=None, explicit_status="ABSENT")
    assert status_abs == "ABSENT"
    assert total_abs is None


def test_grade_scale_rules():
    """Verify letter grade classification and distinct statuses."""
    rules = AssessmentRules()
    grade_rule = rules.grade_rule

    # Passed grade
    status_a, pt_a = grade_rule.classify_grade("A+")
    assert status_a == "PASSED"
    assert pt_a == 9.0

    # Failed grade
    status_f, pt_f = grade_rule.classify_grade("F")
    assert status_f == "FAILED"
    assert pt_f == 0.0

    # Absent status
    status_ab, pt_ab = grade_rule.classify_grade("Ab")
    assert status_ab == "ABSENT"
    assert pt_ab is None

    # Blank / unrecorded cell
    status_blank, pt_blank = grade_rule.classify_grade("")
    assert status_blank == "MISSING"
    assert pt_blank is None


def test_flask_app_routes():
    """Verify Flask application factory, landing page, and health endpoint."""
    app = create_app()
    client = app.test_client()

    # Test landing page
    response = client.get("/")
    assert response.status_code == 200
    assert b"EduPulse" in response.data
    assert b"Academic Big Data Platform" in response.data
    assert b"Dual Academic Data Models" in response.data

    # Test health check endpoint
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    json_data = health_resp.get_json()
    assert json_data["status"] == "healthy"
    assert json_data["storage"]["raw"] is True
    assert json_data["aws_s3_enabled"] is False
