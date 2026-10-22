"""
EduPulse Analytics - University Grade Sheet & SGPA Processing Service
Handles ingestion of university letter-grade sheets, canonical status classification,
credit-weighted SGPA verification, and grade distribution analytics.
"""
import io
import re
import uuid
import logging
from typing import Dict, Any, List, Tuple, Optional, Set
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import numpy as np

from storage.local_storage import LocalStorage
from config.assessment_rules import GradeScaleRule, AssessmentRules
from src.data_validation import DataValidationService, ValidationTally

logger = logging.getLogger(__name__)


class GradeAnalysisError(Exception):
    """Raised when an illegal operation is attempted on letter grades."""
    pass


class UniversityGradeSheetService:
    """
    Specialized service for ingesting, validating, and analyzing university-style
    result sheets featuring letter grades, SGPA metrics, and non-numeric statuses.
    """
    def __init__(
        self,
        storage: Optional[LocalStorage] = None,
        grade_rule: Optional[GradeScaleRule] = None
    ):
        self.storage = storage or LocalStorage()
        self.grade_rule = grade_rule or GradeScaleRule()
        self.validation = DataValidationService()

    def classify_grade_status(self, raw_grade: Any) -> Tuple[str, Optional[float]]:
        """
        Classifies letter grade into canonical status and grade points.
        Preserves non-numeric semantics:
        - 'PASSED': O, A+, A, B+, B, C, P
        - 'FAILED': F, U, FAIL
        - 'ABSENT': Ab, ABS, ABSENT
        - 'WITHHELD': W, WH, WITHHELD
        - 'MISSING': Blank, NULL, unrecorded cell
        """
        return self.grade_rule.classify_grade(raw_grade)

    def prohibit_arbitrary_conversion(self, grades: List[str]) -> None:
        """
        Architectural Guardrail: Strictly prohibits calculating arithmetic averages
        or linear numeric conversions directly on letter grades without configured rules.
        """
        for g in grades:
            if not isinstance(g, str) or g.upper() not in self.grade_rule.grade_points:
                raise GradeAnalysisError(
                    f"Integrity Violation: Arbitrary conversion of letter grade '{g}' "
                    f"to numeric marks is strictly prohibited without an institution-approved conversion formula."
                )

    def calculate_verified_sgpa(
        self,
        grades_with_credits: List[Dict[str, Any]]
    ) -> Optional[float]:
        """
        Computes credit-weighted SGPA if and only if valid course credits are provided:
        SGPA = sum(credits * grade_point) / sum(credits)
        """
        total_credit_points = 0.0
        total_credits = 0.0

        for item in grades_with_credits:
            credits = item.get("course_credits")
            raw_grade = item.get("letter_grade")

            if credits is None or float(credits) <= 0:
                continue

            credits = float(credits)
            status, gp = self.classify_grade_status(raw_grade)

            if status in ("PASSED", "FAILED") and gp is not None:
                total_credit_points += credits * gp
                total_credits += credits

        if total_credits > 0:
            return round(total_credit_points / total_credits, 2)
        return None

    def unpivot_wide_grade_sheet(
        self,
        df: pd.DataFrame,
        id_column: str,
        subject_grade_columns: Dict[str, str],
        subject_credits: Optional[Dict[str, float]] = None,
        sgpa_column: Optional[str] = None,
        semester: int = 1,
        department: str = "",
        academic_year: str = "",
        exam_type: str = "REGULAR"
    ) -> Tuple[List[Dict[str, Any]], ValidationTally]:
        """
        Unpivots a horizontal university result sheet (wide format) into canonical long format.
        subject_grade_columns: mapping of subject_code -> column_name in df
        """
        subject_credits = subject_credits or {}
        raw_records = []

        for _, row in df.iterrows():
            stu_id = str(row[id_column]).strip() if pd.notna(row.get(id_column)) else ""
            if not stu_id:
                continue

            sheet_sgpa = None
            if sgpa_column and sgpa_column in row and pd.notna(row[sgpa_column]):
                sheet_sgpa = self.validation._safe_float(row[sgpa_column])

            for sub_code, col_name in subject_grade_columns.items():
                if col_name not in row:
                    continue
                raw_grade = row[col_name]
                credits = subject_credits.get(sub_code)

                raw_records.append({
                    "student_id": stu_id,
                    "department": department,
                    "semester": semester,
                    "academic_year": academic_year,
                    "exam_type": exam_type,
                    "subject_code": sub_code,
                    "course_credits": credits,
                    "letter_grade": raw_grade,
                    "sgpa": sheet_sgpa
                })

        # Validate normalized records
        return self.validation.validate_grade_records(raw_records, self.grade_rule)

    def analyze_grade_dataset(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generates comprehensive academic analytics for grade-based datasets:
        - Subject-wise grade frequency distributions
        - Subject pass percentages (Passed / (Passed + Failed))
        - SGPA distribution curves and statistical aggregates
        - Failure and absentee concentrations
        """
        df = pd.DataFrame(records)
        if df.empty:
            return {"total_records": 0, "subjects": {}, "sgpa_stats": {}}

        total_records = len(df)
        unique_students = int(df["student_id"].nunique()) if "student_id" in df else 0

        # Subject-wise analytics
        subjects_analysis = {}
        for sub_code, sub_df in df.groupby("subject_code"):
            grade_counts = sub_df["letter_grade"].fillna("BLANK").value_counts().to_dict()
            status_counts = sub_df["grade_status"].value_counts().to_dict()

            passed = status_counts.get("PASSED", 0)
            failed = status_counts.get("FAILED", 0)
            absent = status_counts.get("ABSENT", 0)
            withheld = status_counts.get("WITHHELD", 0)
            missing = status_counts.get("MISSING", 0)

            resolved = passed + failed
            pass_rate = round((passed / resolved) * 100, 2) if resolved > 0 else 0.0

            subjects_analysis[sub_code] = {
                "total_entries": len(sub_df),
                "passed": passed,
                "failed": failed,
                "absent": absent,
                "withheld": withheld,
                "missing": missing,
                "pass_rate": pass_rate,
                "grade_distribution": grade_counts
            }

        # SGPA analytics (student level)
        sgpa_stats = {}
        if "sgpa" in df and df["sgpa"].dropna().count() > 0:
            student_sgpas = df[["student_id", "sgpa"]].dropna().drop_duplicates()
            sgpas = student_sgpas["sgpa"].astype(float)

            sgpa_stats = {
                "count": int(len(sgpas)),
                "mean": round(float(sgpas.mean()), 2),
                "median": round(float(sgpas.median()), 2),
                "std_dev": round(float(sgpas.std()), 2) if len(sgpas) > 1 else 0.0,
                "min": round(float(sgpas.min()), 2),
                "max": round(float(sgpas.max()), 2),
                "q25": round(float(sgpas.quantile(0.25)), 2),
                "q75": round(float(sgpas.quantile(0.75)), 2),
                "bands": {
                    "9.0-10.0": int((sgpas >= 9.0).sum()),
                    "8.0-8.99": int(((sgpas >= 8.0) & (sgpas < 9.0)).sum()),
                    "7.0-7.99": int(((sgpas >= 7.0) & (sgpas < 8.0)).sum()),
                    "6.0-6.99": int(((sgpas >= 6.0) & (sgpas < 7.0)).sum()),
                    "below_6.0": int((sgpas < 6.0).sum())
                }
            }

        return {
            "total_records": total_records,
            "unique_students": unique_students,
            "subject_count": len(subjects_analysis),
            "subjects": subjects_analysis,
            "sgpa_stats": sgpa_stats
        }

    def commit_grade_dataset(
        self,
        records: List[Dict[str, Any]],
        original_filename: str,
        comments: str = ""
    ) -> Dict[str, Any]:
        """
        Commits validated grade-based records, writes validated CSV and manifest.
        """
        dataset_id = str(uuid.uuid4())
        val_df = pd.DataFrame(records)
        val_csv_content = val_df.to_csv(index=False)
        val_path = self.storage.save_validated_dataset(dataset_id, val_csv_content)

        # Raw file snapshot
        raw_path, sha256_hash, file_size = self.storage.save_raw_upload(
            dataset_id=dataset_id,
            original_filename=original_filename,
            file_bytes=val_csv_content.encode("utf-8")
        )

        analysis = self.analyze_grade_dataset(records)
        now_iso = datetime.now(timezone.utc).isoformat()

        manifest = {
            "manifest_version": "1.0.0",
            "dataset_id": dataset_id,
            "import_timestamp": now_iso,
            "comments": comments or f"University grade sheet: {original_filename}",
            "source_file": {
                "original_filename": original_filename,
                "stored_filename": raw_path.name,
                "file_size_bytes": file_size,
                "sha256_checksum": sha256_hash,
                "sheet_name": "Grades",
                "header_row_index": 0
            },
            "model_type": "grade_based",
            "row_counts": {
                "total_raw_rows": len(records),
                "accepted_rows": len(records),
                "rejected_rows": 0,
                "duplicate_rows": 0,
                "incomplete_rows": sum(1 for r in records if r.get("grade_status") in ("MISSING", "ABSENT", "WITHHELD"))
            },
            "grade_analysis": analysis,
            "storage_locations": {
                "raw_path": str(raw_path),
                "validated_path": str(val_path),
                "processed_parquet_dir": f"data/processed/PROC_{dataset_id}"
            }
        }
        self.storage.save_manifest(dataset_id, manifest)
        logger.info(f"University Grade dataset committed: {dataset_id} ({len(records)} records)")
        return manifest
