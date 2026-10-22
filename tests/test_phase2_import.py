"""
EduPulse Analytics - Phase 2 Verification Tests
Tests for LocalStorage, DataValidationService, ImportService, and Data Management routes.
"""
import io
import json
import pytest
import pandas as pd
from pathlib import Path
from storage.local_storage import LocalStorage
from src.data_validation import DataValidationService
from src.import_service import ImportService
from app import create_app


@pytest.fixture
def storage():
    return LocalStorage()


@pytest.fixture
def validation():
    return DataValidationService()


@pytest.fixture
def import_service(storage, validation):
    return ImportService(storage=storage, validation=validation)


def test_storage_path_traversal_defense(storage):
    """Verify resolve_safe_path raises PermissionError on directory traversal attempts."""
    with pytest.raises(PermissionError):
        storage.resolve_safe_path(storage.config.data_dir, "../../windows/system32/cmd.exe")


def test_storage_atomic_write_and_sha256(storage):
    """Verify atomic write and SHA-256 computation."""
    content = b"sample_record_data_12345"
    raw_path, sha256_hash, file_size = storage.save_raw_upload(
        dataset_id="test-dataset-001",
        original_filename="students_batch1.csv",
        file_bytes=content
    )
    assert raw_path.exists()
    assert file_size == len(content)
    assert len(sha256_hash) == 64  # SHA-256 hex string length


def test_formula_injection_sanitization(validation):
    """Verify formula injection triggers (=, +, -, @) are sanitized with a single quote prefix."""
    malicious_inputs = {
        "student_id": "=CMD|' /C calc'!A0",
        "subject_name": "+HYPERLINK('evil.com')",
        "remarks": "@SUM(A1:A10)",
        "legit_name": "Data Structures"
    }
    sanitized = validation.sanitize_record(malicious_inputs)
    assert sanitized["student_id"].startswith("'=")
    assert sanitized["subject_name"].startswith("'+")
    assert sanitized["remarks"].startswith("'@")
    assert sanitized["legit_name"] == "Data Structures"


def test_marks_validation_pipeline(validation):
    """Verify marks validation, range limits, duplicate detection, and absent preservation."""
    records = [
        {"student_id": "STU001", "subject_code": "CS101", "internal_marks": 35.0, "external_marks": 50.0},
        {"student_id": "STU002", "subject_code": "CS101", "internal_marks": 10.0, "external_marks": 15.0}, # Fail
        {"student_id": "STU003", "subject_code": "CS101", "internal_marks": 25.0, "external_marks": "Ab"}, # Absent
        {"student_id": "STU001", "subject_code": "CS101", "internal_marks": 35.0, "external_marks": 50.0}, # Duplicate
        {"student_id": "", "subject_code": "CS101", "internal_marks": 20.0, "external_marks": 30.0},       # Rejected
        {"student_id": "STU004", "subject_code": "CS101", "internal_marks": 99.0, "external_marks": 50.0}, # Out of bounds
    ]
    accepted, tally = validation.validate_marks_records(records)
    
    assert len(accepted) == 3
    assert tally.total_raw_rows == 6
    assert tally.accepted_rows == 3
    assert tally.rejected_rows == 2     # Empty student_id + out-of-bounds internal mark
    assert tally.duplicate_rows == 1    # Duplicate STU001
    
    # Check statuses
    statuses = {r["student_id"]: r["status"] for r in accepted}
    assert statuses["STU001"] == "PASS"
    assert statuses["STU002"] == "FAIL"
    assert statuses["STU003"] == "ABSENT"


def test_grade_validation_pipeline(validation):
    """Verify letter grade classification, preservation of absent codes and blanks."""
    records = [
        {"student_id": "STU101", "subject_code": "MA101", "letter_grade": "O"},
        {"student_id": "STU102", "subject_code": "MA101", "letter_grade": "F"},
        {"student_id": "STU103", "subject_code": "MA101", "letter_grade": "Ab"},
        {"student_id": "STU104", "subject_code": "MA101", "letter_grade": ""},
        {"student_id": "STU105", "subject_code": "MA101", "letter_grade": "UNKNOWN_GRADE"}
    ]
    accepted, tally = validation.validate_grade_records(records)

    assert len(accepted) == 4
    assert tally.rejected_rows == 1      # UNKNOWN_GRADE rejected
    assert tally.incomplete_rows == 1    # Blank grade marked MISSING/incomplete

    statuses = {r["student_id"]: r["grade_status"] for r in accepted}
    assert statuses["STU101"] == "PASSED"
    assert statuses["STU102"] == "FAILED"
    assert statuses["STU103"] == "ABSENT"
    assert statuses["STU104"] == "MISSING"


def test_import_service_csv_e2e(import_service):
    """Verify complete end-to-end import of a CSV with non-standard column headers."""
    csv_data = """Roll No,Sub Code,CIA Marks,ESE Marks,Semester
STU201,CS201,32,48,3
STU202,CS201,14,20,3
STU203,CS201,28,42,3
"""
    file_bytes = csv_data.encode("utf-8")
    
    # 1. Inspect
    inspection = import_service.inspect_file(file_bytes, "exam_scores.csv")
    assert inspection["suggested_model"] == "marks_based"
    assert "Roll No" in inspection["raw_headers"]

    # 2. Preview
    mappings = {
        "student_id": "Roll No",
        "subject_code": "Sub Code",
        "internal_marks": "CIA Marks",
        "external_marks": "ESE Marks",
        "semester": "Semester"
    }
    preview = import_service.generate_preview(
        file_bytes=file_bytes,
        filename="exam_scores.csv",
        sheet_name="Sheet1",
        header_row=0,
        column_mappings=mappings,
        model_type="marks_based"
    )
    assert len(preview["preview_rows"]) == 3
    assert preview["sample_tally"]["accepted_rows"] == 3

    # 3. Commit
    manifest = import_service.commit_import(
        file_bytes=file_bytes,
        original_filename="exam_scores.csv",
        sheet_name="Sheet1",
        header_row=0,
        column_mappings=mappings,
        model_type="marks_based",
        comments="Test commit CSV"
    )
    assert manifest["dataset_id"] is not None
    assert manifest["row_counts"]["accepted_rows"] == 3
    assert Path(manifest["storage_locations"]["raw_path"]).exists()
    assert Path(manifest["storage_locations"]["validated_path"]).exists()


def test_import_service_excel_e2e(import_service):
    """Verify complete end-to-end import of an Excel workbook with multi-sheet structure."""
    df_grades = pd.DataFrame({
        "Reg_Number": ["REG001", "REG002", "REG003"],
        "Course_ID": ["MA201", "MA201", "MA201"],
        "Final_Grade": ["A+", "B", "Ab"],
        "SGPA_Points": [8.5, 6.8, 4.0]
    })
    
    excel_stream = io.BytesIO()
    with pd.ExcelWriter(excel_stream, engine="openpyxl") as writer:
        df_grades.to_excel(writer, sheet_name="SemesterResults", index=False)
    excel_bytes = excel_stream.getvalue()

    # 1. Inspect
    inspection = import_service.inspect_file(excel_bytes, "University_Results.xlsx")
    assert "SemesterResults" in inspection["sheets"]
    assert inspection["suggested_model"] == "grade_based"

    # 2. Commit
    mappings = {
        "student_id": "Reg_Number",
        "subject_code": "Course_ID",
        "letter_grade": "Final_Grade",
        "sgpa": "SGPA_Points"
    }
    manifest = import_service.commit_import(
        file_bytes=excel_bytes,
        original_filename="University_Results.xlsx",
        sheet_name="SemesterResults",
        header_row=0,
        column_mappings=mappings,
        model_type="grade_based",
        comments="Test commit Excel"
    )
    assert manifest["model_type"] == "grade_based"
    assert manifest["row_counts"]["accepted_rows"] == 3


def test_data_management_web_routes():
    """Verify Flask routes for dataset library, inspect, preview, and commit APIs."""
    app = create_app()
    client = app.test_client()

    # 1. Catalog Page
    res_cat = client.get("/data-management/")
    assert res_cat.status_code == 200
    assert b"Dataset Library" in res_cat.data

    # 2. Wizard Page
    res_wiz = client.get("/data-management/import")
    assert res_wiz.status_code == 200
    assert b"Guided Spreadsheet Ingestion" in res_wiz.data

    # 3. API Inspect
    csv_bytes = b"StudentID,SubjectCode,Internal,External\nS101,CS101,30,45\n"
    data = {
        "file": (io.BytesIO(csv_bytes), "test_upload.csv")
    }
    res_inspect = client.post("/data-management/api/inspect", data=data, content_type="multipart/form-data")
    assert res_inspect.status_code == 200
    insp_json = res_inspect.get_json()
    assert insp_json["status"] == "success"
    assert "StudentID" in insp_json["inspection"]["raw_headers"]


def test_storage_delete_dataset(storage):
    """Verify delete_dataset removes all raw, validated, manifest, and cache files."""
    dataset_id = "test-delete-dataset-999"

    # Create dummy artifacts
    storage.save_raw_upload(dataset_id, "dummy.csv", b"raw_content_123")
    storage.save_validated_dataset(dataset_id, "student_id,marks\nS1,40\n")
    storage.save_manifest(dataset_id, {"dataset_id": dataset_id, "version": "1.0"})
    storage.atomic_write_json(storage.config.analytics_dir / f"AGG_{dataset_id}.json", {"summary": {}})

    # Verify they exist
    assert (storage.config.manifests_dir / f"MAN_{dataset_id}.json").exists()
    assert (storage.config.validated_dir / f"VAL_{dataset_id}.csv").exists()

    # Delete dataset
    success = storage.delete_dataset(dataset_id)
    assert success is True

    # Verify all deleted
    assert not (storage.config.manifests_dir / f"MAN_{dataset_id}.json").exists()
    assert not (storage.config.validated_dir / f"VAL_{dataset_id}.csv").exists()
    assert not (storage.config.analytics_dir / f"AGG_{dataset_id}.json").exists()
    assert len(list(storage.config.raw_dir.glob(f"RAW_{dataset_id}.*"))) == 0


def test_data_management_delete_api(storage):
    """Verify DELETE /data-management/api/dataset/<id> removes the dataset."""
    dataset_id = "test-api-delete-888"
    storage.save_manifest(dataset_id, {"dataset_id": dataset_id, "model_type": "marks_based"})
    storage.save_validated_dataset(dataset_id, "student_id,marks\nS1,40\n")

    app = create_app()
    client = app.test_client()

    # Call DELETE endpoint
    res = client.delete(f"/data-management/api/dataset/{dataset_id}")
    assert res.status_code == 200
    res_json = res.get_json()
    assert res_json["status"] == "success"

    # Subsequent DELETE returns 404
    res_404 = client.delete(f"/data-management/api/dataset/{dataset_id}")
    assert res_404.status_code == 404


def test_storage_delete_all_datasets(tmp_path):
    """Verify delete_all_datasets purges all datasets and clears all lakehouse artifacts."""
    from config.settings import StorageConfig
    cfg = StorageConfig(data_dir=tmp_path)
    test_storage = LocalStorage(cfg)
    id1 = "test-del-all-1"
    id2 = "test-del-all-2"

    for did in [id1, id2]:
        test_storage.save_manifest(did, {"dataset_id": did})
        test_storage.save_validated_dataset(did, "student_id,marks\nS1,50\n")
        test_storage.save_raw_upload(did, f"{did}.csv", b"raw_content")
        test_storage.atomic_write_json(test_storage.config.analytics_dir / f"AGG_{did}.json", {"summary": {}})

    assert len(test_storage.list_manifests()) >= 2

    # Execute purge all
    deleted_count = test_storage.delete_all_datasets()
    assert deleted_count >= 2

    # Verify isolated lakehouse is empty of datasets
    assert len(test_storage.list_manifests()) == 0
    assert len(list(test_storage.config.validated_dir.glob("VAL_*.csv"))) == 0
    assert len(list(test_storage.config.raw_dir.glob("RAW_*.*"))) == 0
    assert len(list(test_storage.config.analytics_dir.glob("AGG_*.json"))) == 0


def test_data_management_delete_all_api(tmp_path):
    """Verify POST /data-management/api/datasets/delete-all purges all datasets."""
    from config.settings import AppConfig, StorageConfig
    test_cfg = AppConfig(storage=StorageConfig(data_dir=tmp_path))
    test_storage = LocalStorage(test_cfg.storage)
    id_test = "test-api-del-all-x"
    test_storage.save_manifest(id_test, {"dataset_id": id_test})
    test_storage.save_validated_dataset(id_test, "student_id,marks\nS1,90\n")

    app = create_app(test_cfg)
    client = app.test_client()

    res = client.post("/data-management/api/datasets/delete-all")
    assert res.status_code == 200
    res_json = res.get_json()
    assert res_json["status"] == "success"
    assert res_json["deleted_count"] >= 1

    # Verify manifests now empty in test storage
    assert len(test_storage.list_manifests()) == 0

