"""
EduPulse Analytics - Data Validation & Security Sanitization Engine
Implements formula injection defense (CWE-1236), row constraint checking,
cell-level error isolation, and validation scorecards for all academic assessment types.
"""
import re
from typing import Dict, Any, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from config.assessment_rules import AssessmentRules, SubjectMarksRule, GradeScaleRule, AssessmentTypeConfig


@dataclass
class ValidationIssue:
    """Represents a specific validation warning or fatal rejection."""
    row_number: int
    field_name: str
    issue_type: str  # 'ERROR' or 'WARNING'
    message: str
    raw_value: Any = None


@dataclass
class ValidationTally:
    """Statistical summary of dataset validation results."""
    total_raw_rows: int = 0
    accepted_rows: int = 0
    rejected_rows: int = 0
    duplicate_rows: int = 0
    incomplete_rows: int = 0
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid_to_commit(self) -> bool:
        """Allows commit if there is at least one accepted row."""
        return self.accepted_rows > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_raw_rows": self.total_raw_rows,
            "accepted_rows": self.accepted_rows,
            "rejected_rows": self.rejected_rows,
            "duplicate_rows": self.duplicate_rows,
            "incomplete_rows": self.incomplete_rows,
            "error_count": sum(1 for i in self.issues if i.issue_type == "ERROR"),
            "warning_count": sum(1 for i in self.issues if i.issue_type == "WARNING"),
            "sample_errors": [
                f"Row {i.row_number} [{i.field_name}]: {i.message}"
                for i in self.issues[:25]
            ]
        }


class DataValidationService:
    """
    Validates mapped academic records against institutional assessment rules
    and enforces formula injection security defenses (CWE-1236).
    """
    # Characters that trigger formula execution in spreadsheet software
    FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

    def __init__(self, rules: Optional[AssessmentRules] = None):
        self.rules = rules or AssessmentRules()

    def sanitize_cell_value(self, value: Any) -> Any:
        """
        Mitigates CSV/Excel formula injection (CWE-1236).
        Prepends a single quote (') if a string begins with dangerous formula triggers.
        """
        if value is None:
            return None
        val_str = str(value)
        if val_str and val_str.startswith(self.FORMULA_PREFIXES):
            # Prepend single quote to neutralize formula execution in Excel/Calc
            return f"'{val_str}"
        return value

    def sanitize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitizes all string fields in a record dictionary."""
        return {k: self.sanitize_cell_value(v) for k, v in record.items()}

    def validate_canonical_records(
        self,
        records: List[Dict[str, Any]],
        default_assessment_type: str = "mid_1",
        default_max_marks: Optional[float] = None,
        default_pass_marks: Optional[float] = None
    ) -> Tuple[List[Dict[str, Any]], ValidationTally]:
        """
        Universal validator for normalized assessment records (unpivoted from wide or long layouts).
        Enforces cell-level error tolerance so an anomaly in one subject mark does not discard
        other valid subject assessments for the same student.
        """
        tally = ValidationTally(total_raw_rows=len(records))
        accepted: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()

        for idx, raw_row in enumerate(records, start=1):
            row = self.sanitize_record(raw_row)
            student_id = str(row.get("student_id") or "").strip()
            subject_code = str(row.get("subject_code") or "DEFAULT").strip().upper()
            assessment_type = str(row.get("assessment_type") or default_assessment_type).strip()
            semester = str(row.get("semester") or "1").strip()

            # 1. Mandatory Student ID
            if not student_id:
                tally.rejected_rows += 1
                tally.issues.append(ValidationIssue(
                    row_number=idx, field_name="student_id",
                    issue_type="ERROR", message="Student ID is missing or blank"
                ))
                continue

            # 2. Duplicate Detection (student_id + subject_code + assessment_type + semester)
            composite_key = f"{student_id.upper()}::{subject_code}::{assessment_type.upper()}::{semester}"
            if composite_key in seen_keys:
                tally.duplicate_rows += 1
                tally.issues.append(ValidationIssue(
                    row_number=idx, field_name="composite_key",
                    issue_type="WARNING",
                    message=f"Duplicate entry for student {student_id[:4]}***, subject {subject_code}, assessment {assessment_type}"
                ))
                continue
            seen_keys.add(composite_key)

            # 3. Assessment Evaluation
            asmt_cfg = self.rules.get_assessment_type(assessment_type)
            max_marks = float(row.get("max_marks")) if row.get("max_marks") is not None else (
                default_max_marks if default_max_marks is not None else asmt_cfg.default_max_marks
            )
            pass_marks = float(row.get("pass_marks")) if row.get("pass_marks") is not None else (
                default_pass_marks if default_pass_marks is not None else asmt_cfg.default_pass_marks
            )

            raw_marks = row.get("marks_obtained") if row.get("marks_obtained") is not None else row.get("total_marks")
            raw_grade = row.get("letter_grade")
            explicit_status = str(row.get("result_status") or row.get("status") or "").strip().upper() or None

            # Detect explicit non-numeric status strings in marks column
            if raw_marks is not None:
                marks_str = str(raw_marks).strip().upper()
                if marks_str in ("AB", "ABS", "ABSENT"):
                    explicit_status = "ABSENT"
                    raw_marks = None
                elif marks_str in ("W", "WH", "WITHHELD"):
                    explicit_status = "WITHHELD"
                    raw_marks = None
                elif marks_str in ("I", "INCOMPLETE", "NA", "-", "NULL"):
                    explicit_status = "INCOMPLETE"
                    raw_marks = None

            is_valid = True
            val_status = "VALID"
            val_notes = []
            result_status = "PASS"
            marks_obtained: Optional[float] = None
            grade_points: Optional[float] = None

            # Evaluate Letter Grade if provided
            if raw_grade:
                g_status, g_pts = self.rules.grade_rule.classify_grade(raw_grade)
                grade_points = g_pts
                if g_status == "UNKNOWN":
                    is_valid = False
                    val_status = "INVALID"
                    val_notes.append(f"Unrecognized grade '{raw_grade}'")
                    tally.rejected_rows += 1
                    tally.issues.append(ValidationIssue(
                        row_number=idx, field_name="letter_grade",
                        issue_type="ERROR", message=f"Unrecognized grade '{raw_grade}'"
                    ))
                    continue
                elif g_status in ("ABSENT", "WITHHELD", "MISSING"):
                    result_status = g_status
                    if g_status == "MISSING":
                        tally.incomplete_rows += 1
                        val_notes.append("Grade cell missing")
                else:
                    result_status = "PASS" if g_status == "PASSED" else "FAIL"

            # Evaluate Marks if numeric marks provided
            elif raw_marks is not None:
                marks_obtained = self._safe_float(raw_marks)
                if marks_obtained is None:
                    # Non-numeric mark not caught above
                    is_valid = False
                    val_status = "INVALID"
                    val_notes.append(f"Non-numeric marks value '{raw_marks}'")
                    tally.rejected_rows += 1
                    tally.issues.append(ValidationIssue(
                        row_number=idx, field_name="marks_obtained",
                        issue_type="ERROR", message=f"Non-numeric marks value '{raw_marks}'"
                    ))
                    continue

                # Bounds check
                if marks_obtained < 0 or (max_marks is not None and marks_obtained > max_marks):
                    is_valid = False
                    val_status = "INVALID"
                    val_notes.append(f"Marks {marks_obtained} out of bounds (max: {max_marks})")
                    tally.rejected_rows += 1
                    tally.issues.append(ValidationIssue(
                        row_number=idx, field_name="marks_obtained",
                        issue_type="ERROR", message=f"Marks {marks_obtained} exceeds max {max_marks}"
                    ))
                    continue

                result_status = "PASS" if (pass_marks is None or marks_obtained >= pass_marks) else "FAIL"

            elif explicit_status:
                result_status = explicit_status
                if result_status == "INCOMPLETE":
                    tally.incomplete_rows += 1
                    val_notes.append("Assessment record incomplete")
            else:
                # No marks and no grade provided
                result_status = "INCOMPLETE"
                tally.incomplete_rows += 1
                val_notes.append("No marks or grade recorded")

            grade_status = "PASSED" if result_status == "PASS" else ("FAILED" if result_status == "FAIL" else result_status)

            # Record accepted
            tally.accepted_rows += 1
            clean_record = {
                "student_id": student_id,
                "student_name": str(row.get("student_name") or "").strip(),
                "department": str(row.get("department") or "General").strip(),
                "semester": int(semester) if semester.isdigit() else 1,
                "academic_year": str(row.get("academic_year") or "").strip(),
                "section": str(row.get("section") or "").strip(),
                "batch": str(row.get("batch") or "").strip(),
                "subject_code": subject_code,
                "subject_name": str(row.get("subject_name") or subject_code).strip(),
                "assessment_type": assessment_type,
                "assessment_name": str(row.get("assessment_name") or asmt_cfg.display_name).strip(),
                "max_marks": max_marks,
                "pass_marks": pass_marks,
                "weightage": float(row.get("weightage")) if row.get("weightage") is not None else asmt_cfg.weightage,
                "internal_marks": self._safe_float(row.get("internal_marks")),
                "external_marks": self._safe_float(row.get("external_marks")),
                "total_marks": marks_obtained,
                "marks_obtained": marks_obtained,
                "letter_grade": str(raw_grade).strip().upper() if raw_grade else None,
                "grade_points": grade_points,
                "credits": self._safe_float(row.get("credits") or row.get("course_credits")),
                "sgpa": self._safe_float(row.get("sgpa")),
                "result_status": result_status,
                "grade_status": grade_status,
                "status": result_status,
                "attendance_status": "ABSENT" if result_status == "ABSENT" else "PRESENT",
                "remarks": str(row.get("remarks") or "").strip(),
                "validation_status": val_status,
                "validation_notes": "; ".join(val_notes) if val_notes else "OK"
            }
            accepted.append(clean_record)

        return accepted, tally

    def validate_marks_records(
        self,
        records: List[Dict[str, Any]],
        default_rule: Optional[SubjectMarksRule] = None
    ) -> Tuple[List[Dict[str, Any]], ValidationTally]:
        """
        Validates marks-based academic records (Long schema).
        Returns: (accepted_records: List[dict], tally: ValidationTally)
        """
        rule = default_rule or self.rules.default_marks_rule
        tally = ValidationTally(total_raw_rows=len(records))
        accepted: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()

        for idx, raw_row in enumerate(records, start=1):
            row = self.sanitize_record(raw_row)
            student_id = str(row.get("student_id") or "").strip()
            subject_code = str(row.get("subject_code") or "DEFAULT").strip().upper()
            semester = str(row.get("semester") or "1").strip()

            # 1. Mandatory Student ID
            if not student_id:
                tally.rejected_rows += 1
                tally.issues.append(ValidationIssue(
                    row_number=idx, field_name="student_id",
                    issue_type="ERROR", message="Student ID is missing or blank"
                ))
                continue

            # 2. Duplicate Detection
            composite_key = f"{student_id.upper()}::{subject_code}::{semester}"
            if composite_key in seen_keys:
                tally.duplicate_rows += 1
                tally.issues.append(ValidationIssue(
                    row_number=idx, field_name="composite_key",
                    issue_type="WARNING", message=f"Duplicate entry for student {student_id[:2]}*** and subject {subject_code}"
                ))
                continue
            seen_keys.add(composite_key)

            # 3. Marks Parsing & Validation
            raw_internal = row.get("internal_marks")
            raw_external = row.get("external_marks")
            explicit_status = str(row.get("status") or "").strip().upper() or None

            internal = self._safe_float(raw_internal)
            external = self._safe_float(raw_external)

            # Check if student was explicitly marked absent
            if explicit_status in ("ABSENT", "AB") or str(raw_external).strip().upper() in ("AB", "ABSENT"):
                explicit_status = "ABSENT"

            status, total = rule.evaluate_result(internal, external, explicit_status)

            if status == "INVALID":
                tally.rejected_rows += 1
                tally.issues.append(ValidationIssue(
                    row_number=idx, field_name="marks",
                    issue_type="ERROR",
                    message=f"Marks out of bounds (Internal: {raw_internal}/{rule.max_internal}, External: {raw_external}/{rule.max_external})"
                ))
                continue

            if status == "INCOMPLETE":
                tally.incomplete_rows += 1
                tally.issues.append(ValidationIssue(
                    row_number=idx, field_name="marks",
                    issue_type="WARNING", message="Incomplete record: one or more mark components missing"
                ))

            # Record accepted
            tally.accepted_rows += 1
            clean_record = {
                "student_id": student_id,
                "department": str(row.get("department") or "General").strip(),
                "batch": str(row.get("batch") or "").strip(),
                "section": str(row.get("section") or "").strip(),
                "semester": int(semester) if semester.isdigit() else 1,
                "academic_year": str(row.get("academic_year") or "").strip(),
                "assessment_period": str(row.get("assessment_period") or "Final").strip(),
                "subject_code": subject_code,
                "subject_name": str(row.get("subject_name") or rule.subject_name).strip(),
                "internal_marks": internal,
                "max_internal": rule.max_internal,
                "external_marks": external,
                "max_external": rule.max_external,
                "total_marks": total,
                "max_total": rule.max_total,
                "percentage": round((total / rule.max_total) * 100, 2) if total is not None else None,
                "status": status,
                "attendance_pct": self._safe_float(row.get("attendance_pct"))
            }
            accepted.append(clean_record)

        return accepted, tally

    def validate_grade_records(
        self,
        records: List[Dict[str, Any]],
        grade_rule: Optional[GradeScaleRule] = None
    ) -> Tuple[List[Dict[str, Any]], ValidationTally]:
        """
        Validates grade-based academic records from university sheets.
        Returns: (accepted_records: List[dict], tally: ValidationTally)
        """
        rule = grade_rule or self.rules.grade_rule
        tally = ValidationTally(total_raw_rows=len(records))
        accepted: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()

        for idx, raw_row in enumerate(records, start=1):
            row = self.sanitize_record(raw_row)
            student_id = str(row.get("student_id") or "").strip()
            subject_code = str(row.get("subject_code") or "GENERAL").strip().upper()
            semester = str(row.get("semester") or "1").strip()

            # 1. Mandatory Student ID
            if not student_id:
                tally.rejected_rows += 1
                tally.issues.append(ValidationIssue(
                    row_number=idx, field_name="student_id",
                    issue_type="ERROR", message="Student ID is missing or blank"
                ))
                continue

            # 2. Duplicate Detection
            composite_key = f"{student_id.upper()}::{subject_code}::{semester}"
            if composite_key in seen_keys:
                tally.duplicate_rows += 1
                tally.issues.append(ValidationIssue(
                    row_number=idx, field_name="composite_key",
                    issue_type="WARNING", message=f"Duplicate grade entry for student {student_id[:2]}*** and subject {subject_code}"
                ))
                continue
            seen_keys.add(composite_key)

            # 3. Grade Classification
            raw_grade = row.get("letter_grade") or row.get("grade")
            status, grade_point = rule.classify_grade(raw_grade)

            if status == "UNKNOWN":
                tally.rejected_rows += 1
                tally.issues.append(ValidationIssue(
                    row_number=idx, field_name="letter_grade",
                    issue_type="ERROR", message=f"Unrecognized letter grade: '{raw_grade}'"
                ))
                continue

            if status == "MISSING":
                tally.incomplete_rows += 1
                tally.issues.append(ValidationIssue(
                    row_number=idx, field_name="letter_grade",
                    issue_type="WARNING", message="Grade cell is unrecorded / blank"
                ))

            # Record accepted
            tally.accepted_rows += 1
            clean_record = {
                "student_id": student_id,
                "department": str(row.get("department") or "").strip(),
                "semester": int(semester) if semester.isdigit() else 1,
                "academic_year": str(row.get("academic_year") or "").strip(),
                "exam_type": str(row.get("exam_type") or "REGULAR").strip().upper(),
                "subject_code": subject_code,
                "subject_name": str(row.get("subject_name") or "").strip(),
                "course_credits": self._safe_float(row.get("course_credits")),
                "letter_grade": str(raw_grade).strip().upper() if raw_grade else None,
                "grade_status": status,
                "grade_point": grade_point,
                "sgpa": self._safe_float(row.get("sgpa") or row.get("gpa"))
            }
            accepted.append(clean_record)

        return accepted, tally

    @staticmethod
    def _safe_float(val: Any) -> Optional[float]:
        """Safely parses float values, ignoring commas or non-numeric tokens."""
        if val is None:
            return None
        val_str = str(val).strip().replace(",", "")
        try:
            return float(val_str)
        except (ValueError, TypeError):
            return None
