"""
EduPulse Analytics - Phase 4 Verification Tests
Tests for UniversityGradeSheetService, status preservation, SGPA analytics, and guardrails.
"""
import pytest
import pandas as pd
from pathlib import Path
from storage.local_storage import LocalStorage
from src.grade_service import UniversityGradeSheetService, GradeAnalysisError


@pytest.fixture
def grade_service():
    storage = LocalStorage()
    return UniversityGradeSheetService(storage=storage)


def test_grade_status_preservation(grade_service):
    """
    Verification Gate: Verify letter grades, absent codes (Ab), withheld (W),
    and blanks are strictly distinguished and preserved without coercion.
    """
    # 1. Passed grades
    assert grade_service.classify_grade_status("O") == ("PASSED", 10.0)
    assert grade_service.classify_grade_status("A+") == ("PASSED", 9.0)
    assert grade_service.classify_grade_status("B") == ("PASSED", 6.0)

    # 2. Failed grades
    assert grade_service.classify_grade_status("F") == ("FAILED", 0.0)
    assert grade_service.classify_grade_status("FAIL") == ("FAILED", 0.0)

    # 3. Absent code: Must NOT be converted to 0.0 or FAIL
    status_ab, gp_ab = grade_service.classify_grade_status("Ab")
    assert status_ab == "ABSENT"
    assert gp_ab is None

    status_abs, gp_abs = grade_service.classify_grade_status("ABSENT")
    assert status_abs == "ABSENT"
    assert gp_abs is None

    # 4. Withheld code: Must NOT be converted to failure
    status_w, gp_w = grade_service.classify_grade_status("W")
    assert status_w == "WITHHELD"
    assert gp_w is None

    # 5. Blank unrecorded cell: Must NOT be assumed as failure
    status_blank, gp_blank = grade_service.classify_grade_status("")
    assert status_blank == "MISSING"
    assert gp_blank is None

    status_none, gp_none = grade_service.classify_grade_status(None)
    assert status_none == "MISSING"
    assert gp_none is None


def test_guardrail_against_arbitrary_conversion(grade_service):
    """
    Verification Gate: Prohibit arbitrary conversion of letter grades into raw marks.
    """
    # Invalid grades or unknown schemas must raise GradeAnalysisError
    with pytest.raises(GradeAnalysisError):
        grade_service.prohibit_arbitrary_conversion(["A+", "B", "UNKNOWN_XYZ"])


def test_verified_sgpa_calculation(grade_service):
    """
    Verification Gate: Verify credit-weighted SGPA calculation matches ground truth.
    """
    # Student with 3 courses:
    # CS301 (4 credits, grade O = 10 pts) -> 40
    # CS302 (4 credits, grade A = 8 pts)  -> 32
    # CS303 (2 credits, grade B = 6 pts)  -> 12
    # Total credit points = 84, Total credits = 10 -> SGPA = 8.40
    grades_data = [
        {"course_credits": 4.0, "letter_grade": "O"},
        {"course_credits": 4.0, "letter_grade": "A"},
        {"course_credits": 2.0, "letter_grade": "B"}
    ]
    sgpa = grade_service.calculate_verified_sgpa(grades_data)
    assert sgpa == 8.40

    # Test with an absent grade: absent course is not resolved
    grades_with_absent = [
        {"course_credits": 4.0, "letter_grade": "O"},
        {"course_credits": 4.0, "letter_grade": "Ab"}
    ]
    sgpa_absent = grade_service.calculate_verified_sgpa(grades_with_absent)
    assert sgpa_absent == 10.0  # Only resolved course evaluated


def test_unpivot_wide_university_result_sheet(grade_service):
    """
    Verification Gate: Unpivot horizontal university result sheet with SGPA and letter grades.
    """
    data = {
        "Roll_Number": ["REG101", "REG102", "REG103", "REG104"],
        "Math_Grade": ["O", "B", "Ab", "F"],
        "Physics_Grade": ["A+", "C", "A", ""],
        "Provided_SGPA": [9.5, 5.8, 8.0, 3.2]
    }
    df = pd.DataFrame(data)

    subject_cols = {
        "MA101": "Math_Grade",
        "PH101": "Physics_Grade"
    }

    records, tally = grade_service.unpivot_wide_grade_sheet(
        df=df,
        id_column="Roll_Number",
        subject_grade_columns=subject_cols,
        sgpa_column="Provided_SGPA",
        semester=1,
        department="Engineering"
    )

    # 4 students * 2 subjects = 8 records
    assert len(records) == 8
    assert tally.accepted_rows == 8
    assert tally.incomplete_rows == 1  # REG104 Physics is blank (MISSING)

    # Check that SGPA is preserved from the sheet
    reg101_records = [r for r in records if r["student_id"] == "REG101"]
    assert all(r["sgpa"] == 9.5 for r in reg101_records)

    # Check that Ab is preserved
    reg103_math = next(r for r in records if r["student_id"] == "REG103" and r["subject_code"] == "MA101")
    assert reg103_math["grade_status"] == "ABSENT"


def test_grade_dataset_analytics(grade_service):
    """
    Verification Gate: Verify subject-wise grade distributions, pass percentages,
    and SGPA statistics.
    """
    records = [
        {"student_id": "S1", "subject_code": "CS101", "letter_grade": "O", "grade_status": "PASSED", "sgpa": 9.2},
        {"student_id": "S2", "subject_code": "CS101", "letter_grade": "A+", "grade_status": "PASSED", "sgpa": 8.8},
        {"student_id": "S3", "subject_code": "CS101", "letter_grade": "F", "grade_status": "FAILED", "sgpa": 4.5},
        {"student_id": "S4", "subject_code": "CS101", "letter_grade": "Ab", "grade_status": "ABSENT", "sgpa": 7.0},
        {"student_id": "S5", "subject_code": "CS101", "letter_grade": "W", "grade_status": "WITHHELD", "sgpa": 6.5}
    ]

    analysis = grade_service.analyze_grade_dataset(records)

    assert analysis["total_records"] == 5
    assert analysis["unique_students"] == 5
    sub_metrics = analysis["subjects"]["CS101"]
    
    assert sub_metrics["passed"] == 2
    assert sub_metrics["failed"] == 1
    assert sub_metrics["absent"] == 1
    assert sub_metrics["withheld"] == 1
    # Pass rate: 2 passed / (2 passed + 1 failed) = 66.67%
    assert sub_metrics["pass_rate"] == 66.67

    # SGPA Metrics
    sgpa_stats = analysis["sgpa_stats"]
    assert sgpa_stats["count"] == 5
    assert sgpa_stats["median"] == 7.0
    assert sgpa_stats["max"] == 9.2
    assert sgpa_stats["min"] == 4.5


def test_commit_grade_dataset_e2e(grade_service):
    """
    Verification Gate: End-to-end commit of grade-based dataset creates manifest and validated files.
    """
    records = [
        {"student_id": "U01", "subject_code": "BIO101", "letter_grade": "A", "grade_status": "PASSED", "sgpa": 8.0},
        {"student_id": "U02", "subject_code": "BIO101", "letter_grade": "B", "grade_status": "PASSED", "sgpa": 7.0}
    ]
    manifest = grade_service.commit_grade_dataset(records, "Spring_Bio_Grades.xlsx", "End-to-end grade test")

    assert manifest["model_type"] == "grade_based"
    assert manifest["row_counts"]["accepted_rows"] == 2
    assert Path(manifest["storage_locations"]["validated_path"]).exists()
    assert Path(manifest["storage_locations"]["raw_path"]).exists()
    assert "grade_analysis" in manifest
