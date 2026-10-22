"""
EduPulse Analytics - Universal Academic Assessment Import Engine Tests
Comprehensive verification of multi-sheet inspection, header banner detection,
wide-to-long unpivoting, roll number integrity, cell-level error tolerance,
and persistence across diverse academic assessment types.
"""
import io
import json
import pytest
import pandas as pd
from pathlib import Path
from storage.local_storage import LocalStorage
from src.data_validation import DataValidationService
from src.import_service import ImportService
from config.assessment_rules import AssessmentRules


@pytest.fixture
def storage():
    return LocalStorage()


@pytest.fixture
def validation():
    return DataValidationService()


@pytest.fixture
def import_service(storage, validation):
    return ImportService(storage=storage, validation=validation)


def test_wide_csv_internal_marks_unpivoting(import_service):
    """
    Verify wide CSV with internal marks is auto-detected as 'wide',
    unpivoted into individual subject records, and preserves all marks.
    """
    csv_data = """Roll No,Student Name,Mathematics,Physics,Chemistry,Python Programming
21A91A0501,Alice Johnson,35,32,38,40
21A91A0502,Bob Smith,14,18,22,25
21A91A0503,Charlie Davis,28,Ab,30,35
"""
    file_bytes = csv_data.encode("utf-8")
    
    # 1. Inspect
    inspection = import_service.inspect_file(file_bytes, "mid1_marks.csv")
    assert inspection["detected_layout"] == "wide"
    assert inspection["detected_student_id_column"] == "Roll No"
    assert "Mathematics" in inspection["candidate_subject_columns"]
    assert "Python Programming" in inspection["candidate_subject_columns"]
    assert len(inspection["candidate_subject_columns"]) == 4

    # 2. Preview
    preview = import_service.generate_preview(
        file_bytes=file_bytes,
        filename="mid1_marks.csv",
        sheet_name="Sheet1",
        header_row=0,
        layout="wide",
        student_id_col="Roll No",
        subject_cols=inspection["candidate_subject_columns"],
        student_name_col="Student Name",
        assessment_type="mid_1",
        default_max_marks=40.0,
        default_pass_marks=16.0
    )
    assert preview["layout"] == "wide"
    assert preview["total_unpivoted_count"] == 12  # 3 students * 4 subjects
    assert preview["sample_tally"]["accepted_rows"] == 12

    # Check unpivoted rows
    rows_by_student = {}
    for r in preview["preview_rows"]:
        rows_by_student.setdefault(r["student_id"], {})[r["subject_name"]] = r

    # Alice: all passed
    assert rows_by_student["21A91A0501"]["Mathematics"]["marks_obtained"] == 35.0
    assert rows_by_student["21A91A0501"]["Mathematics"]["result_status"] == "PASS"

    # Bob: failed Math (14 < 16)
    assert rows_by_student["21A91A0502"]["Mathematics"]["marks_obtained"] == 14.0
    assert rows_by_student["21A91A0502"]["Mathematics"]["result_status"] == "FAIL"

    # Charlie: Absent in Physics
    assert rows_by_student["21A91A0503"]["Physics"]["result_status"] == "ABSENT"
    assert rows_by_student["21A91A0503"]["Physics"]["attendance_status"] == "ABSENT"
    assert rows_by_student["21A91A0503"]["Physics"]["marks_obtained"] is None

    # 3. Commit
    manifest = import_service.commit_import(
        file_bytes=file_bytes,
        original_filename="mid1_marks.csv",
        sheet_name="Sheet1",
        header_row=0,
        layout="wide",
        student_id_col="Roll No",
        subject_cols=inspection["candidate_subject_columns"],
        student_name_col="Student Name",
        assessment_type="mid_1",
        default_max_marks=40.0,
        default_pass_marks=16.0
    )
    assert manifest["layout"] == "wide"
    assert manifest["assessment_type"] == "mid_1"
    assert manifest["row_counts"]["accepted_rows"] == 12

    # Verify persisted validated CSV
    val_df = pd.read_csv(manifest["storage_locations"]["validated_path"], dtype=str)
    assert len(val_df) == 12
    assert set(val_df["student_id"].unique()) == {"21A91A0501", "21A91A0502", "21A91A0503"}


def test_leading_zero_preservation(import_service):
    """
    Verify alphanumeric roll numbers and numeric IDs with leading zeros (e.g. '00101', '09A11A0501')
    are preserved as strings and never converted to ints or floats.
    """
    df = pd.DataFrame({
        "Roll No": ["00101", "00102", "09A11A0501"],
        "Subject1": [25, 30, 35],
        "Subject2": [28, 32, 38]
    })
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    manifest = import_service.commit_import(
        file_bytes=csv_bytes,
        original_filename="leading_zeros.csv",
        sheet_name="Sheet1",
        header_row=0,
        layout="wide",
        student_id_col="Roll No",
        subject_cols=["Subject1", "Subject2"],
        assessment_type="internal"
    )
    
    val_csv_path = Path(manifest["storage_locations"]["validated_path"])
    raw_content = val_csv_path.read_text(encoding="utf-8")
    
    # Must contain '00101' and '00102' literally in the CSV
    assert "00101" in raw_content
    assert "00102" in raw_content
    assert "09A11A0501" in raw_content


def test_serial_number_disambiguation(import_service):
    """
    Verify engine distinguishes S.No (serial number) from actual student ID (HT No / Roll No).
    """
    df = pd.DataFrame({
        "S.No": ["1", "2", "3"],
        "HT No": ["22R11A05C0", "22R11A05E9", "22R11A05N8"],
        "Subject_A": ["30", "25", "28"],
        "Subject_B": ["32", "27", "29"]
    })
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    inspection = import_service.inspect_file(csv_bytes, "results_with_sno.csv")
    assert inspection["detected_student_id_column"] == "HT No"
    assert inspection["detected_serial_column"] == "S.No"
    assert "S.No" not in inspection["candidate_subject_columns"]
    assert "HT No" not in inspection["candidate_subject_columns"]
    assert set(inspection["candidate_subject_columns"]) == {"Subject_A", "Subject_B"}


def test_banner_detection_and_offset(import_service):
    """
    Verify college title banners and address headers at the top of spreadsheets
    are detected and skipped so the genuine header row is identified.
    """
    # Create Excel with 4 banner rows before header
    rows = [
        ["GEETHANJALI COLLEGE OF ENGINEERING & TECHNOLOGY", None, None, None],
        ["CHEERYALA(V), KEESARA(M), MEDCHAL DIST.", None, None, None],
        ["III YEAR II SEMESTER MID-1 EXAMINATIONS", None, None, None],
        [None, None, None, None],  # Blank row
        ["HT No", "Student Name", "IoT", "Machine Learning"]  # Real header at index 4
    ]
    # Data rows
    for i in range(1, 4):
        rows.append([f"21R11A050{i}", f"Student {i}", "35", "38"])

    df = pd.DataFrame(rows)
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        df.to_excel(writer, header=False, index=False)
    excel_bytes = stream.getvalue()

    inspection = import_service.inspect_file(excel_bytes, "college_results.xlsx")
    assert inspection["detected_header_row"] == 4
    assert "GEETHANJALI COLLEGE" in inspection["banner_text"]
    assert inspection["detected_student_id_column"] == "HT No"
    assert "IoT" in inspection["candidate_subject_columns"]
    assert "Machine Learning" in inspection["candidate_subject_columns"]


def test_multi_sheet_excel_workbook(import_service):
    """
    Verify inspection and processing of multi-worksheet Excel workbooks.
    """
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        df_cse_a = pd.DataFrame({
            "Roll No": ["CSE_A_01", "CSE_A_02"],
            "Networks": [30, 32],
            "Database": [34, 36]
        })
        df_cse_a.to_excel(writer, sheet_name="CSE_Section_A", index=False)

        df_cse_b = pd.DataFrame({
            "Roll No": ["CSE_B_01", "CSE_B_02"],
            "Networks": [28, 29],
            "Database": [31, 33]
        })
        df_cse_b.to_excel(writer, sheet_name="CSE_Section_B", index=False)

    excel_bytes = stream.getvalue()

    # 1. Inspect discovers both sheets
    inspection = import_service.inspect_file(excel_bytes, "CSE_Sections.xlsx")
    assert len(inspection["sheets"]) == 2
    assert "CSE_Section_A" in inspection["sheets"]
    assert "CSE_Section_B" in inspection["sheets"]

    # 2. Commit Section A
    manifest_a = import_service.commit_import(
        file_bytes=excel_bytes,
        original_filename="CSE_Sections.xlsx",
        sheet_name="CSE_Section_A",
        header_row=0,
        layout="wide",
        student_id_col="Roll No",
        subject_cols=["Networks", "Database"],
        assessment_type="mid_1"
    )
    assert manifest_a["row_counts"]["accepted_rows"] == 4

    # 3. Commit Section B
    manifest_b = import_service.commit_import(
        file_bytes=excel_bytes,
        original_filename="CSE_Sections.xlsx",
        sheet_name="CSE_Section_B",
        header_row=0,
        layout="wide",
        student_id_col="Roll No",
        subject_cols=["Networks", "Database"],
        assessment_type="mid_1"
    )
    assert manifest_b["row_counts"]["accepted_rows"] == 4


def test_cell_level_error_tolerance(validation):
    """
    Verify cell-level validation preserves valid subjects for a student even if one cell
    in that student's record is invalid (e.g. mark out of range).
    """
    canonical_records = [
        # Student 1: 3 valid subjects, 1 invalid mark (999 > 40)
        {"student_id": "STU100", "subject_code": "MATH", "marks_obtained": 35.0, "max_marks": 40.0, "pass_marks": 16.0},
        {"student_id": "STU100", "subject_code": "PHYS", "marks_obtained": 999.0, "max_marks": 40.0, "pass_marks": 16.0},  # Invalid
        {"student_id": "STU100", "subject_code": "CHEM", "marks_obtained": 30.0, "max_marks": 40.0, "pass_marks": 16.0},
        {"student_id": "STU100", "subject_code": "ENGL", "marks_obtained": 28.0, "max_marks": 40.0, "pass_marks": 16.0},
    ]
    accepted, tally = validation.validate_canonical_records(canonical_records)

    # 3 records must be accepted, only 1 rejected
    assert tally.total_raw_rows == 4
    assert tally.accepted_rows == 3
    assert tally.rejected_rows == 1
    assert len(accepted) == 3

    accepted_subjects = [r["subject_code"] for r in accepted]
    assert "MATH" in accepted_subjects
    assert "CHEM" in accepted_subjects
    assert "ENGL" in accepted_subjects
    assert "PHYS" not in accepted_subjects


def test_diverse_assessment_types(import_service):
    """
    Verify assessment types: mid-1, mid-2, internal, laboratory, semester exam, assignment, quiz.
    """
    types_to_test = ["mid_1", "mid_2", "internal", "laboratory", "semester_exam", "assignment", "quiz"]
    
    for asmt_type in types_to_test:
        df = pd.DataFrame({
            "Student_ID": ["S01", "S02"],
            "Course1": [8, 9],
            "Course2": [7, 10]
        })
        csv_bytes = df.to_csv(index=False).encode("utf-8")

        manifest = import_service.commit_import(
            file_bytes=csv_bytes,
            original_filename=f"test_{asmt_type}.csv",
            sheet_name="Sheet1",
            header_row=0,
            layout="wide",
            student_id_col="Student_ID",
            subject_cols=["Course1", "Course2"],
            assessment_type=asmt_type
        )
        assert manifest["assessment_type"] == asmt_type
        assert manifest["row_counts"]["accepted_rows"] == 4


def test_real_world_university_grade_sheet_ingestion(import_service):
    """
    Verify ingestion of real-world multi-banner university grade sheet (Geethanjali CSE Sem 6)
    with 14 subjects, letter grades, absent codes, and SGPA.
    """
    real_file_path = Path("C:/Users/ezraa/.gemini/antigravity/brain/373563d1-332e-474c-b0df-68574436d45e/.user_uploaded/media_1792572493982.xlsx")
    if not real_file_path.exists():
        pytest.skip("Uploaded test workbook not found in artifacts")

    file_bytes = real_file_path.read_bytes()
    inspection = import_service.inspect_file(file_bytes, "Geethanjali_CSE_Sem6.xlsx")
    
    assert inspection["detected_layout"] == "wide"
    assert inspection["detected_header_row"] == 4
    assert inspection["detected_student_id_column"] == "HT No"
    assert len(inspection["candidate_subject_columns"]) >= 10

    # Commit with wide unpivoting
    manifest = import_service.commit_import(
        file_bytes=file_bytes,
        original_filename="Geethanjali_CSE_Sem6.xlsx",
        sheet_name="Table 1",
        header_row=4,
        layout="wide",
        student_id_col="HT No",
        subject_cols=inspection["candidate_subject_columns"],
        model_type="grade_based",
        assessment_type="semester_exam",
        comments="Real world Geethanjali Sem 6 grade sheet ingestion"
    )

    assert manifest["layout"] == "wide"
    assert manifest["model_type"] == "grade_based"
    assert manifest["row_counts"]["accepted_rows"] > 1000

    # Verify persisted validated CSV
    val_df = pd.read_csv(manifest["storage_locations"]["validated_path"], dtype=str)
    assert len(val_df) > 1000
    assert "student_id" in val_df.columns
    assert "subject_code" in val_df.columns
    assert "letter_grade" in val_df.columns
    assert "grade_points" in val_df.columns
    assert "sgpa" in val_df.columns
    # Check that subjects were unpivoted cleanly
    assert "20CS32001" in val_df["subject_code"].values
    assert "22R11A05C0" in val_df["student_id"].values

