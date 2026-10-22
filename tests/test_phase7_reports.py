"""
EduPulse Analytics - Phase 7 Verification Tests
Tests for ReportGenerator (HTML & CSV exports), Settings Manager, and Phase 7 Web Routes.
"""
import io
import csv
import pytest
import pandas as pd
from pathlib import Path
from storage.local_storage import LocalStorage
from services.analytics_service import AnalyticsService
from src.report_generator import ReportGenerator
from app import create_app


@pytest.fixture
def test_dataset():
    """Sets up a validated dataset and registered manifest for report testing."""
    storage = LocalStorage()
    service = AnalyticsService(storage=storage)
    dataset_id = "test-reports-ds-001"

    data = [
        {"student_id": "STU-R01", "department": "CSE", "semester": 1, "subject_code": "CS101", "subject_name": "Prog Fundamentals", "total_marks": 85.0, "percentage": 85.0, "status": "PASS"},
        {"student_id": "STU-R01", "department": "CSE", "semester": 1, "subject_code": "CS102", "subject_name": "Data Structures", "total_marks": 75.0, "percentage": 75.0, "status": "PASS"},
        {"student_id": "STU-R02", "department": "CSE", "semester": 1, "subject_code": "CS101", "subject_name": "Prog Fundamentals", "total_marks": 30.0, "percentage": 30.0, "status": "FAIL"},
        {"student_id": "STU-R02", "department": "CSE", "semester": 1, "subject_code": "CS102", "subject_name": "Data Structures", "total_marks": 28.0, "percentage": 28.0, "status": "FAIL"},
        {"student_id": "STU-R03", "department": "ECE", "semester": 1, "subject_code": "CS101", "subject_name": "Prog Fundamentals", "total_marks": None, "percentage": None, "status": "ABSENT"}
    ]
    df = pd.DataFrame(data)

    val_file = storage.config.validated_dir / f"VAL_{dataset_id}.csv"
    df.to_csv(val_file, index=False)

    manifest = {
        "dataset_id": dataset_id,
        "model_type": "marks_based",
        "academic_year": "2025-2026",
        "import_timestamp": "2026-10-21T12:00:00Z",
        "source_file": {
            "original_filename": "report_test_marks.csv",
            "sha256_checksum": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        },
        "row_counts": {"total_raw_rows": 5, "accepted_rows": 5, "rejected_rows": 0, "duplicate_rows": 0},
        "storage_locations": {
            "validated_path": str(val_file)
        }
    }
    storage.save_manifest(dataset_id, manifest)
    return dataset_id


def test_generate_executive_html(test_dataset):
    """
    Verification Gate: Verify standalone, printable HTML executive briefing generation.
    """
    generator = ReportGenerator()
    html = generator.generate_executive_html(test_dataset)

    assert "<!DOCTYPE html>" in html
    assert "EduPulse Analytics" in html
    assert test_dataset in html
    assert "CS101" in html
    assert "CS102" in html
    assert "@media print" in html
    assert "MULTIPLE_FAILURES" in html or "ABSENT_ALERT" in html


def test_generate_csv_reports(test_dataset):
    """
    Verification Gate: Verify generation and integrity of CSV analytical exports.
    """
    generator = ReportGenerator()

    # 1. Subject Summary CSV
    subj_csv = generator.generate_subject_summary_csv(test_dataset)
    assert subj_csv != ""
    reader = csv.reader(io.StringIO(subj_csv))
    rows = list(reader)
    header = rows[0]
    assert "subject_code" in header
    assert "pass_rate" in header
    assert "difficulty_index" in header
    assert len(rows) >= 3  # Header + CS101 + CS102

    # 2. Student Support Indicators CSV
    supp_csv = generator.generate_support_indicators_csv(test_dataset)
    assert supp_csv != ""
    reader_supp = csv.reader(io.StringIO(supp_csv))
    rows_supp = list(reader_supp)
    header_supp = rows_supp[0]
    assert "student_id" in header_supp
    assert "flag_type" in header_supp
    assert "action_recommended" in header_supp
    assert any("STU-R02" in r[0] for r in rows_supp[1:])

    # 3. Validated Clean CSV
    val_csv = generator.generate_validated_export_csv(test_dataset)
    assert "STU-R01" in val_csv
    assert "Prog Fundamentals" in val_csv

    # 4. Student Consolidated Ledger CSV
    ledger_csv = generator.generate_consolidated_student_ledger_csv(test_dataset)
    assert ledger_csv != ""
    assert "student_id" in ledger_csv
    assert "passed_evaluations" in ledger_csv
    assert "STU-R01" in ledger_csv

    # 5. Backlogs Remedial Action List CSV
    remedial_csv = generator.generate_backlogs_remedial_csv(test_dataset)
    assert remedial_csv != ""
    assert "remedial_recommendation" in remedial_csv


def test_reports_web_routes(test_dataset):
    """
    Verification Gate: Verify Flask routes for reports dashboard and downloads.
    """
    app = create_app()
    client = app.test_client()

    # 1. Reports Dashboard Page
    res_page = client.get("/reports/")
    assert res_page.status_code == 200
    assert b"Institutional Reports & Analytical Exports" in res_page.data

    # 2. HTML Briefing Preview
    res_html = client.get(f"/reports/download/html?dataset_id={test_dataset}")
    assert res_html.status_code == 200
    assert "text/html" in res_html.content_type
    assert b"Executive Academic Briefing" in res_html.data

    # 3. HTML Briefing Download Attachment
    res_html_dl = client.get(f"/reports/download/html?dataset_id={test_dataset}&download=1")
    assert res_html_dl.status_code == 200
    assert "attachment" in res_html_dl.headers.get("Content-Disposition", "")

    # 4. Subject Summary CSV Download
    res_csv_subj = client.get(f"/reports/download/csv?dataset_id={test_dataset}&type=subject")
    assert res_csv_subj.status_code == 200
    assert "text/csv" in res_csv_subj.content_type
    assert "Subject_Summary_" in res_csv_subj.headers.get("Content-Disposition", "")

    # 5. Student Support CSV Download
    res_csv_supp = client.get(f"/reports/download/csv?dataset_id={test_dataset}&type=support")
    assert res_csv_supp.status_code == 200
    assert "Student_Support_Indicators_" in res_csv_supp.headers.get("Content-Disposition", "")

    # 6. Validated Export CSV Download
    res_csv_audit = client.get(f"/reports/download/csv?dataset_id={test_dataset}&type=audit")
    assert res_csv_audit.status_code == 200
    assert "Validated_Dataset_" in res_csv_audit.headers.get("Content-Disposition", "")

    # 7. Error handling: missing dataset_id
    res_err = client.get("/reports/download/html")
    assert res_err.status_code == 400


def test_settings_web_routes_and_api():
    """
    Verification Gate: Verify settings page rendering and API updates for assessment rules.
    """
    app = create_app()
    client = app.test_client()

    # 1. Settings Page
    res_settings = client.get("/settings/")
    assert res_settings.status_code == 200
    assert b"System Configuration & Assessment Rules" in res_settings.data
    assert b"Marks Assessment Rules" in res_settings.data
    assert b"Disabled (Local First)" in res_settings.data

    # 2. Get Rules API
    res_get_rules = client.get("/settings/api/rules")
    assert res_get_rules.status_code == 200
    rules_json = res_get_rules.get_json()
    assert rules_json["status"] == "success"
    assert "default_marks_rule" in rules_json["rules"]

    # 3. Update Rules API
    res_update = client.post("/settings/api/rules", json={
        "marks_rule": {
            "max_internal": 50.0,
            "max_external": 50.0,
            "min_internal_pass": 20.0,
            "min_external_pass": 20.0,
            "min_total_pass": 40.0
        }
    })
    assert res_update.status_code == 200
    update_json = res_update.get_json()
    assert update_json["status"] == "success"
    assert update_json["rules"]["default_marks_rule"]["max_internal"] == 50.0
