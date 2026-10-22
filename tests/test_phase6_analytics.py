"""
EduPulse Analytics - Phase 6 Verification Tests
Tests for AnalyticsEngine, AnalyticsService, Rule-Based Support Indicators, and Analytics Web Routes.
"""
import pytest
import pandas as pd
from pathlib import Path
from src.analytics import AnalyticsEngine
from services.analytics_service import AnalyticsService
from storage.local_storage import LocalStorage
from app import create_app


@pytest.fixture
def analytics_engine():
    return AnalyticsEngine()


@pytest.fixture
def sample_marks_df():
    """
    Standard ground-truth marks dataset fixture:
    4 students, 2 subjects, diverse pass/fail/absent outcomes.
    """
    data = [
        # Student 1: High performer
        {"student_id": "STU-001", "department": "CSE", "semester": 1, "subject_code": "CS101", "subject_name": "Prog Fundamentals", "total_marks": 80.0, "percentage": 80.0, "status": "PASS"},
        {"student_id": "STU-001", "department": "CSE", "semester": 1, "subject_code": "CS102", "subject_name": "Data Structures", "total_marks": 70.0, "percentage": 70.0, "status": "PASS"},
        # Student 2: Critical multiple failures
        {"student_id": "STU-002", "department": "CSE", "semester": 1, "subject_code": "CS101", "subject_name": "Prog Fundamentals", "total_marks": 25.0, "percentage": 25.0, "status": "FAIL"},
        {"student_id": "STU-002", "department": "CSE", "semester": 1, "subject_code": "CS102", "subject_name": "Data Structures", "total_marks": 30.0, "percentage": 30.0, "status": "FAIL"},
        # Student 3: Single failure
        {"student_id": "STU-003", "department": "ECE", "semester": 1, "subject_code": "CS101", "subject_name": "Prog Fundamentals", "total_marks": 55.0, "percentage": 55.0, "status": "PASS"},
        {"student_id": "STU-003", "department": "ECE", "semester": 1, "subject_code": "CS102", "subject_name": "Data Structures", "total_marks": 35.0, "percentage": 35.0, "status": "FAIL"},
        # Student 4: Absent in one exam
        {"student_id": "STU-004", "department": "CSE", "semester": 1, "subject_code": "CS101", "subject_name": "Prog Fundamentals", "total_marks": 60.0, "percentage": 60.0, "status": "PASS"},
        {"student_id": "STU-004", "department": "CSE", "semester": 1, "subject_code": "CS102", "subject_name": "Data Structures", "total_marks": None, "percentage": None, "status": "ABSENT"}
    ]
    return pd.DataFrame(data)


@pytest.fixture
def sample_grades_df():
    """
    Standard ground-truth university grade result fixture:
    3 students, 2 subjects, with letter grades and SGPA.
    """
    data = [
        # Student 1: Excellent
        {"student_id": "STU-G01", "department": "CSE", "semester": 2, "subject_code": "CS201", "subject_name": "Algorithms", "letter_grade": "O", "grade_status": "PASSED", "credits": 4, "sgpa": 9.2},
        {"student_id": "STU-G01", "department": "CSE", "semester": 2, "subject_code": "CS202", "subject_name": "Operating Systems", "letter_grade": "A", "grade_status": "PASSED", "credits": 4, "sgpa": 9.2},
        # Student 2: Double Backlog, Low SGPA < 5.0
        {"student_id": "STU-G02", "department": "CSE", "semester": 2, "subject_code": "CS201", "subject_name": "Algorithms", "letter_grade": "F", "grade_status": "FAILED", "credits": 4, "sgpa": 4.2},
        {"student_id": "STU-G02", "department": "CSE", "semester": 2, "subject_code": "CS202", "subject_name": "Operating Systems", "letter_grade": "F", "grade_status": "FAILED", "credits": 4, "sgpa": 4.2},
        # Student 3: Moderate, SGPA 5.6 (< 6.0 benchmark)
        {"student_id": "STU-G03", "department": "ECE", "semester": 2, "subject_code": "CS201", "subject_name": "Algorithms", "letter_grade": "B", "grade_status": "PASSED", "credits": 4, "sgpa": 5.6},
        {"student_id": "STU-G03", "department": "ECE", "semester": 2, "subject_code": "CS202", "subject_name": "Operating Systems", "letter_grade": "C", "grade_status": "PASSED", "credits": 4, "sgpa": 5.6}
    ]
    return pd.DataFrame(data)


def test_marks_analytics_engine(analytics_engine, sample_marks_df):
    """
    Verification Gate: Verify calculation of marks KPIs, distributions,
    subject difficulty index, and transparent support indicators.
    """
    result = analytics_engine.compute_marks_analytics(sample_marks_df)

    assert result["model_type"] == "marks_based"
    summary = result["summary"]
    assert summary["total_records"] == 8
    assert summary["unique_students"] == 4
    assert summary["unique_subjects"] == 2
    assert summary["passed_count"] == 4
    assert summary["failed_count"] == 3
    assert summary["absent_count"] == 1

    # Pass percentage: 4 passed out of 7 evaluated = 57.14%
    assert summary["pass_percentage"] == 57.14
    assert summary["min_score"] == 25.0
    assert summary["max_score"] == 80.0

    # Subjects breakdown
    subjects = {s["subject_code"]: s for s in result["subjects"]}
    assert "CS101" in subjects
    assert "CS102" in subjects
    assert subjects["CS101"]["passed"] == 3
    assert subjects["CS101"]["failed"] == 1
    assert 0.0 <= subjects["CS101"]["difficulty_index"] <= 1.0


def test_student_support_indicators_explainability(analytics_engine, sample_marks_df):
    """
    Verification Gate: Ensure student support indicators are transparent,
    rule-based, and give human-readable reasons (no opaque AI assertions).
    """
    flags = analytics_engine.detect_student_support_indicators(sample_marks_df)
    flags_by_stu = {f["student_id"]: f for f in flags}

    # Student 2 failed CS101 and CS102 -> MULTIPLE_FAILURES
    assert "STU-002" in flags_by_stu
    flag2 = flags_by_stu["STU-002"]
    assert flag2["flag_type"] == "MULTIPLE_FAILURES"
    assert flag2["severity"] == "HIGH"
    assert "CS101" in flag2["reason"] and "CS102" in flag2["reason"]
    assert "remedial" in flag2["action_recommended"].lower()

    # Student 3 failed CS102 -> SINGLE_FAILURE
    assert "STU-003" in flags_by_stu
    flag3 = flags_by_stu["STU-003"]
    assert flag3["flag_type"] == "SINGLE_FAILURE"
    assert flag3["severity"] == "MEDIUM"

    # Student 4 absent in CS102 -> ABSENT_ALERT
    assert "STU-004" in flags_by_stu
    flag4 = flags_by_stu["STU-004"]
    assert flag4["flag_type"] == "ABSENT_ALERT"
    assert "CS102" in flag4["reason"]


def test_grade_analytics_engine(analytics_engine, sample_grades_df):
    """
    Verification Gate: Verify calculation of university grade KPIs,
    letter grade distributions, SGPA statistics, and grade support flags.
    """
    result = analytics_engine.compute_grade_analytics(sample_grades_df)

    assert result["model_type"] == "grade_based"
    summary = result["summary"]
    assert summary["total_records"] == 6
    assert summary["unique_students"] == 3
    assert summary["passed_count"] == 4
    assert summary["failed_count"] == 2
    assert summary["pass_percentage"] == 66.67

    # SGPA Stats
    sgpa = result["sgpa_stats"]
    assert sgpa["count"] == 3
    assert sgpa["min"] == 4.2
    assert sgpa["max"] == 9.2

    # Grade Support Indicators
    flags = result["support_indicators"]
    flags_by_stu = {f["student_id"]: f for f in flags if f["flag_type"] == "BACKLOG_ALERT"}
    assert "STU-G02" in flags_by_stu
    assert flags_by_stu["STU-G02"]["severity"] == "HIGH"
    assert "F" in flags_by_stu["STU-G02"]["reason"]

    # Low SGPA flags
    sgpa_flags = {f["student_id"]: f for f in flags if f["flag_type"] == "LOW_SGPA_ALERT"}
    assert "STU-G02" in sgpa_flags  # < 5.0 -> HIGH
    assert sgpa_flags["STU-G02"]["severity"] == "HIGH"
    assert "STU-G03" in sgpa_flags  # 5.6 -> MEDIUM (< 6.0)
    assert sgpa_flags["STU-G03"]["severity"] == "MEDIUM"


def test_analytics_service_and_filtering(tmp_path, sample_marks_df):
    """
    Verification Gate: Verify AnalyticsService reads dataset, creates pre-computed
    analytics cache, and filters properly by department and semester.
    """
    storage = LocalStorage()
    service = AnalyticsService(storage=storage)

    dataset_id = "test-service-001"
    val_file = storage.config.validated_dir / f"VAL_{dataset_id}.csv"
    sample_marks_df.to_csv(val_file, index=False)

    manifest = {
        "dataset_id": dataset_id,
        "model_type": "marks_based",
        "academic_year": "2025-2026",
        "import_timestamp": "2026-10-21T12:00:00Z",
        "source_file": {
            "original_filename": "sample_marks.csv",
            "sha256_checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        },
        "row_counts": {"total_raw_rows": 8, "accepted_rows": 8, "rejected_rows": 0, "duplicate_rows": 0},
        "storage_locations": {
            "validated_path": str(val_file)
        }
    }
    storage.save_manifest(dataset_id, manifest)

    # 1. Fetch unfiltered analytics
    analytics = service.get_dataset_analytics(dataset_id)
    assert analytics is not None
    assert analytics["summary"]["total_records"] == 8

    # Verify cache file was created
    cache_path = storage.config.analytics_dir / f"AGG_{dataset_id}.json"
    assert cache_path.exists()

    # 2. Filter by department = 'ECE'
    filtered_ece = service.get_filtered_analytics(dataset_id=dataset_id, department="ECE")
    assert filtered_ece is not None
    assert filtered_ece["summary"]["total_records"] == 2
    assert filtered_ece["summary"]["unique_students"] == 1

    # 3. Filter by non-matching department
    filtered_none = service.get_filtered_analytics(dataset_id=dataset_id, department="CIVIL")
    assert filtered_none["summary"]["total_records"] == 0


def test_student_longitudinal_lookup(sample_marks_df):
    """
    Verification Gate: Verify longitudinal record lookup across semesters and datasets.
    """
    storage = LocalStorage()
    service = AnalyticsService(storage=storage)

    dataset_id = "test-longitudinal-001"
    val_file = storage.config.validated_dir / f"VAL_{dataset_id}.csv"
    sample_marks_df.to_csv(val_file, index=False)

    manifest = {
        "dataset_id": dataset_id,
        "model_type": "marks_based",
        "import_timestamp": "2026-10-21T12:00:00Z",
        "source_file": {
            "original_filename": "sample_longitudinal.csv",
            "sha256_checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        },
        "row_counts": {"total_raw_rows": 8, "accepted_rows": 8, "rejected_rows": 0, "duplicate_rows": 0},
        "storage_locations": {
            "validated_path": str(val_file)
        }
    }
    storage.save_manifest(dataset_id, manifest)

    # Lookup existing student
    rec = service.get_student_longitudinal_record("STU-001")
    assert rec is not None
    assert rec["student_id"] == "STU-001"
    assert rec["department"] == "CSE"
    assert rec["total_courses_taken"] >= 2
    assert len(rec["progression"]) >= 1
    assert rec["progression"][0]["semester"] == 1
    assert rec["progression"][0]["average_percentage"] == 75.0

    # Non-existent student
    non_rec = service.get_student_longitudinal_record("NON-EXISTENT-ID")
    assert non_rec is None


def test_analytics_web_routes():
    """
    Verification Gate: Verify executive dashboard, academic analysis,
    and student performance web routes respond with HTTP 200.
    """
    app = create_app()
    client = app.test_client()

    # 1. Executive Dashboard
    res_dash = client.get("/dashboard/")
    assert res_dash.status_code == 200
    assert b"Institutional Academic Performance" in res_dash.data

    # 2. Academic Analysis
    res_analysis = client.get("/academic-analysis/")
    assert res_analysis.status_code == 200
    assert b"Cross-Sectional Academic Analysis" in res_analysis.data

    # 3. Student Performance View
    res_stu = client.get("/student-performance/")
    assert res_stu.status_code == 200
    assert b"Longitudinal Student Academic Trajectory" in res_stu.data

    # Search with ID
    res_stu_search = client.get("/student-performance/?student_id=STU-001")
    assert res_stu_search.status_code == 200
    assert b"STU-001" in res_stu_search.data


def test_multi_dataset_analytics_and_smart_switch(sample_marks_df, sample_grades_df):
    """
    Verify multi-dataset aggregation ('ALL') and smart semester auto-switching
    when filtering by a semester that exists in another uploaded dataset.
    """
    storage = LocalStorage()
    service = AnalyticsService(storage=storage)

    # Dataset A (Sem 1)
    id_a = "test-switch-sem1"
    val_a = storage.config.validated_dir / f"VAL_{id_a}.csv"
    sample_marks_df.to_csv(val_a, index=False)
    storage.save_manifest(id_a, {
        "dataset_id": id_a,
        "model_type": "marks_based",
        "source_file": {"original_filename": "Sem1_Marks.csv"},
        "row_counts": {"accepted_rows": len(sample_marks_df)}
    })

    # Dataset B (Sem 2)
    id_b = "test-switch-sem2"
    val_b = storage.config.validated_dir / f"VAL_{id_b}.csv"
    sample_grades_df.to_csv(val_b, index=False)
    storage.save_manifest(id_b, {
        "dataset_id": id_b,
        "model_type": "grade_based",
        "source_file": {"original_filename": "Sem2_Grades.csv"},
        "row_counts": {"accepted_rows": len(sample_grades_df)}
    })

    # 1. Multi-dataset institutional overview ('ALL')
    all_res = service.get_dataset_analytics("ALL")
    assert all_res is not None
    assert all_res["dataset_id"] == "ALL"
    assert all_res["summary"]["total_records"] >= len(sample_marks_df) + len(sample_grades_df)

    # 2. Filter ALL by Semester 1
    sem1_filtered = service.get_filtered_analytics(dataset_id="ALL", department="ALL", semester=1)
    assert sem1_filtered is not None
    assert len(sem1_filtered["subjects"]) > 0

    # 3. Smart auto-switch: Query dataset B (Sem 2) with semester=1
    # Should automatically detect semester 1 in Dataset A and return valid records
    switch_res = service.get_filtered_analytics(dataset_id=id_b, department="ALL", semester=1)
    assert switch_res is not None
    assert len(switch_res["subjects"]) > 0
    assert switch_res["dataset_id"] == id_a

    # Clean up test artifacts
    storage.delete_dataset(id_a)
    storage.delete_dataset(id_b)


def test_clear_student_backlog_api_and_service(sample_grades_df):
    """
    Verification Gate: Test student backlog clearance mechanism both via
    AnalyticsService and the Flask HTTP API endpoint /student-performance/api/clear-backlog.
    """
    app = create_app()
    client = app.test_client()
    storage = LocalStorage()
    service = AnalyticsService(storage=storage)

    # Save a temporary dataset with a failing record (STU-002 CS101 Grade F)
    dataset_id = "test-clear-backlog-ds"
    val_file = storage.config.validated_dir / f"VAL_{dataset_id}.csv"
    sample_grades_df.to_csv(val_file, index=False)
    storage.save_manifest(dataset_id, {
        "dataset_id": dataset_id,
        "model_type": "grade_based",
        "source_file": {"original_filename": "Test_Grades.csv"},
        "row_counts": {"accepted_rows": len(sample_grades_df)}
    })

    try:
        # Check initial longitudinal record for STU-002
        rec_before = service.get_student_longitudinal_record("STU-002")
        assert rec_before is not None
        assert rec_before["backlogs_count"] >= 1
        assert any(b["subject_code"] == "CS101" for b in rec_before["backlogs_list"])

        # 1. Clear backlog via API
        response = client.post("/student-performance/api/clear-backlog", json={
            "student_id": "STU-002",
            "subject_code": "CS101",
            "letter_grade": "B+",
            "grade_points": 7.0,
            "semester": 1,
            "updated_sgpa": 7.25,
            "remarks": "Passed Supplementary Exam 2026"
        })
        assert response.status_code == 200
        res_data = response.get_json()
        assert res_data["status"] == "success"

        # Check refreshed record for STU-002
        rec_after = service.get_student_longitudinal_record("STU-002")
        assert rec_after is not None
        # CS101 should no longer be in backlogs_list
        assert not any(b["subject_code"] == "CS101" for b in rec_after["backlogs_list"])
        # In course_history, CS101 should now have status PASS and letter_grade B+
        cs101_entry = next(c for c in rec_after["course_history"] if c["subject_code"] == "CS101")
        assert cs101_entry["letter_grade"] == "B+"
        assert cs101_entry["grade_points"] == 7.0
        assert cs101_entry["status"] == "PASS"

        # Check audit trail log
        audit_file = storage.config.data_dir / "backlog_clearances.json"
        assert audit_file.exists()
        audit_data = storage.read_json(audit_file)
        assert any(a["student_id"] == "STU-002" and a["subject_code"] == "CS101" for a in audit_data)
    finally:
        storage.delete_dataset(dataset_id)

