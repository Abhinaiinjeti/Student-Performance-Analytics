"""
EduPulse Analytics - Phase 3 Verification Tests
Tests for ClassEntryService, draft management, CSV template export/import, and Class Entry routes.
"""
import json
import pytest
from pathlib import Path
from storage.local_storage import LocalStorage
from services.class_entry_service import ClassEntryService
from app import create_app


@pytest.fixture
def storage():
    return LocalStorage()


@pytest.fixture
def service(storage):
    return ClassEntryService(storage=storage)


def test_unpivot_and_validate_30_students(service):
    """
    Verification Gate: Enter marks for 30 students across 4 subjects.
    Verify unpivoting to 120 records, subject-specific cutoffs, and summary calculations.
    """
    class_meta = {
        "department": "Computer Science",
        "batch": "2023-2027",
        "section": "A",
        "semester": 3,
        "academic_year": "2025-2026",
        "assessment_period": "Final-Exam"
    }

    subjects = [
        {"code": "CS301", "name": "Data Structures", "max_internal": 40, "max_external": 60, "min_internal_pass": 16, "min_external_pass": 24, "min_total_pass": 40},
        {"code": "CS302", "name": "Algorithms", "max_internal": 40, "max_external": 60, "min_internal_pass": 16, "min_external_pass": 24, "min_total_pass": 40},
        {"code": "CS303", "name": "Database Systems", "max_internal": 50, "max_external": 50, "min_internal_pass": 20, "min_external_pass": 20, "min_total_pass": 50},
        {"code": "CS304", "name": "Computer Networks", "max_internal": 40, "max_external": 60, "min_internal_pass": 16, "min_external_pass": 24, "min_total_pass": 40}
    ]

    # Generate 30 student entries
    student_rows = []
    for i in range(1, 31):
        stu_id = f"STU-2026-{i:03d}"
        # Inject varied scores: some passes, some borderline fails, one absent, one out of range
        if i == 15:
            # Student 15 absent in CS301
            marks = {
                "CS301": {"internal": 30, "external": "Ab"},
                "CS302": {"internal": 25, "external": 35},
                "CS303": {"internal": 30, "external": 30},
                "CS304": {"internal": 20, "external": 40}
            }
        elif i == 20:
            # Student 20 fails CS302
            marks = {
                "CS301": {"internal": 25, "external": 35},
                "CS302": {"internal": 10, "external": 12}, # 22 < 40
                "CS303": {"internal": 30, "external": 30},
                "CS304": {"internal": 25, "external": 35}
            }
        else:
            marks = {
                "CS301": {"internal": 30, "external": 45},
                "CS302": {"internal": 28, "external": 42},
                "CS303": {"internal": 35, "external": 35},
                "CS304": {"internal": 32, "external": 48}
            }
        student_rows.append({"student_id": stu_id, "marks": marks})

    accepted, tally, summary = service.unpivot_and_validate(class_meta, subjects, student_rows)

    assert len(accepted) == 120  # 30 students * 4 subjects = 120 long records
    assert tally.accepted_rows == 120
    assert summary["total_students"] == 30
    assert summary["total_subject_records"] == 120
    assert summary["absent_records"] == 1  # Student 15 in CS301
    assert summary["failed_records"] >= 1  # Student 20 in CS302
    assert summary["pass_percentage"] > 95.0


def test_draft_autosave_and_restore(storage, service):
    """Verify saving a draft to data/drafts/ and restoring it cleanly."""
    draft_id = "test-draft-abc-123"
    draft_data = {
        "metadata": {"department": "Electronics", "semester": 4},
        "subjects": [{"code": "EC401", "name": "Signals"}],
        "students": [{"student_id": "EC001", "marks": {"EC401": {"internal": 32, "external": 48}}}]
    }

    # Save
    storage.save_draft(draft_id, draft_data)
    
    # Verify existence
    loaded = storage.get_draft(draft_id)
    assert loaded is not None
    assert loaded["metadata"]["department"] == "Electronics"
    assert len(loaded["students"]) == 1

    # Cleanup
    storage.delete_draft(draft_id)
    assert storage.get_draft(draft_id) is None


def test_csv_template_export_and_import(service):
    """Verify bidirectional CSV export and import into grid structure."""
    subjects = [
        {"code": "CS101", "name": "Intro to CS"},
        {"code": "CS102", "name": "Discrete Math"}
    ]
    student_rows = [
        {"student_id": "S101", "marks": {"CS101": {"internal": "30", "external": "45"}, "CS102": {"internal": "25", "external": "35"}}},
        {"student_id": "S102", "marks": {"CS101": {"internal": "20", "external": "30"}, "CS102": {"internal": "18", "external": "22"}}}
    ]

    # 1. Export
    csv_text = service.generate_csv_template(subjects, student_rows)
    assert "student_id" in csv_text
    assert "CS101_internal" in csv_text
    assert "CS102_external" in csv_text
    assert "S101" in csv_text

    # 2. Parse back
    parsed_rows = service.parse_csv_into_grid(csv_text, subjects)
    assert len(parsed_rows) == 2
    assert parsed_rows[0]["student_id"] == "S101"
    assert float(parsed_rows[0]["marks"]["CS101"]["internal"]) == 30.0
    assert float(parsed_rows[0]["marks"]["CS101"]["external"]) == 45.0


def test_class_entry_commit_e2e(service, storage):
    """Verify end-to-end commit creates validated dataset and manifest."""
    class_meta = {"department": "Mech", "semester": 2, "batch": "2024-2028"}
    subjects = [{"code": "ME201", "name": "Thermodynamics", "max_internal": 40, "max_external": 60, "min_internal_pass": 16, "min_external_pass": 24, "min_total_pass": 40}]
    student_rows = [
        {"student_id": "ME001", "marks": {"ME201": {"internal": 35, "external": 50}}},
        {"student_id": "ME002", "marks": {"ME201": {"internal": 12, "external": 15}}}
    ]

    manifest = service.commit_class_entry(class_meta, subjects, student_rows, comments="Verified ME commit")
    dataset_id = manifest["dataset_id"]

    assert Path(manifest["storage_locations"]["validated_path"]).exists()
    assert Path(manifest["storage_locations"]["raw_path"]).exists()
    assert manifest["class_summary"]["total_students"] == 2
    assert manifest["class_summary"]["passed_records"] == 1
    assert manifest["class_summary"]["failed_records"] == 1


def test_class_entry_web_routes():
    """Verify Flask routes for class entry UI, drafts API, validation API, and export API."""
    app = create_app()
    client = app.test_client()

    # 1. Class Entry Page
    res_page = client.get("/class-entry/")
    assert res_page.status_code == 200
    assert b"Class Marks Entry" in res_page.data

    # 2. Validate API
    payload = {
        "metadata": {"department": "Civil", "semester": 1},
        "subjects": [{"code": "CE101", "name": "Surveying", "max_internal": 40, "max_external": 60, "min_internal_pass": 16, "min_external_pass": 24, "min_total_pass": 40}],
        "students": [{"student_id": "CE001", "marks": {"CE101": {"internal": 30, "external": 45}}}]
    }
    res_val = client.post("/class-entry/api/validate", json=payload)
    assert res_val.status_code == 200
    val_json = res_val.get_json()
    assert val_json["status"] == "success"
    assert val_json["summary"]["pass_percentage"] == 100.0

    # 3. Export CSV API
    res_exp = client.post("/class-entry/api/export-csv", json=payload)
    assert res_exp.status_code == 200
    assert b"student_id,CE101_internal,CE101_external" in res_exp.data
