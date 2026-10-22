"""
EduPulse Analytics - Class Marks Entry Service
Handles unpivoting wide matrix entries, subject rule evaluation, CSV template import/export,
and dataset commit.
"""
import io
import csv
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
from storage.local_storage import LocalStorage
from config.assessment_rules import SubjectMarksRule, AssessmentRules
from src.data_validation import DataValidationService, ValidationTally

logger = logging.getLogger(__name__)


class ClassEntryService:
    """
    Coordinates class-wise marks data processing, validation, and persistence.
    """
    def __init__(self, storage: Optional[LocalStorage] = None, validation: Optional[DataValidationService] = None):
        self.storage = storage or LocalStorage()
        self.validation = validation or DataValidationService()

    def unpivot_and_validate(
        self,
        class_metadata: Dict[str, Any],
        subjects: List[Dict[str, Any]],
        student_rows: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], ValidationTally, Dict[str, Any]]:
        """
        Unpivots wide student marks grid into normalized long records and validates each entry.
        Returns: (normalized_records, validation_tally, class_summary)
        """
        # Build SubjectMarksRule objects
        rules_map: Dict[str, SubjectMarksRule] = {}
        for sub in subjects:
            code = str(sub.get("code") or "").strip().upper()
            rule = SubjectMarksRule(
                subject_code=code,
                subject_name=str(sub.get("name") or code).strip(),
                max_internal=float(sub.get("max_internal", 40.0)),
                max_external=float(sub.get("max_external", 60.0)),
                min_internal_pass=float(sub.get("min_internal_pass", 16.0)),
                min_external_pass=float(sub.get("min_external_pass", 24.0)),
                min_total_pass=float(sub.get("min_total_pass", 40.0))
            )
            rules_map[code] = rule

        # Prepare unpivoted raw records
        raw_unpivoted = []
        for s_idx, student in enumerate(student_rows):
            student_id = str(student.get("student_id") or "").strip()
            marks_dict = student.get("marks", {})

            for sub_code, rule in rules_map.items():
                sub_marks = marks_dict.get(sub_code, {})
                raw_internal = sub_marks.get("internal")
                raw_external = sub_marks.get("external")

                raw_unpivoted.append({
                    "student_id": student_id,
                    "department": class_metadata.get("department", "General"),
                    "batch": class_metadata.get("batch", ""),
                    "section": class_metadata.get("section", ""),
                    "semester": class_metadata.get("semester", 1),
                    "academic_year": class_metadata.get("academic_year", ""),
                    "assessment_period": class_metadata.get("assessment_period", "Final"),
                    "subject_code": sub_code,
                    "subject_name": rule.subject_name,
                    "internal_marks": raw_internal,
                    "external_marks": raw_external,
                    "attendance_pct": sub_marks.get("attendance")
                })

        # Validate each record using subject-specific rules
        accepted_records = []
        master_tally = ValidationTally(total_raw_rows=len(raw_unpivoted))
        seen_keys = set()

        for idx, row in enumerate(raw_unpivoted, start=1):
            student_id = row["student_id"]
            sub_code = row["subject_code"]
            semester = str(row["semester"])
            rule = rules_map.get(sub_code, self.validation.rules.default_marks_rule)

            if not student_id:
                master_tally.rejected_rows += 1
                continue

            comp_key = f"{student_id.upper()}::{sub_code}::{semester}"
            if comp_key in seen_keys:
                master_tally.duplicate_rows += 1
                continue
            seen_keys.add(comp_key)

            raw_int = row["internal_marks"]
            raw_ext = row["external_marks"]
            status_explicit = None

            if str(raw_ext).strip().upper() in ("AB", "ABSENT") or str(raw_int).strip().upper() in ("AB", "ABSENT"):
                status_explicit = "ABSENT"

            internal = self.validation._safe_float(raw_int)
            external = self.validation._safe_float(raw_ext)

            status, total = rule.evaluate_result(internal, external, status_explicit)

            if status == "INVALID":
                master_tally.rejected_rows += 1
                continue

            if status == "INCOMPLETE":
                master_tally.incomplete_rows += 1

            master_tally.accepted_rows += 1
            clean = {
                "student_id": student_id,
                "department": row["department"],
                "batch": row["batch"],
                "section": row["section"],
                "semester": int(semester) if semester.isdigit() else 1,
                "academic_year": row["academic_year"],
                "assessment_period": row["assessment_period"],
                "subject_code": sub_code,
                "subject_name": rule.subject_name,
                "internal_marks": internal,
                "max_internal": rule.max_internal,
                "external_marks": external,
                "max_external": rule.max_external,
                "total_marks": total,
                "max_total": rule.max_total,
                "percentage": round((total / rule.max_total) * 100, 2) if total is not None else None,
                "status": status,
                "attendance_pct": self.validation._safe_float(row["attendance_pct"])
            }
            accepted_records.append(clean)

        # Compute summary statistics
        passed_count = sum(1 for r in accepted_records if r["status"] == "PASS")
        failed_count = sum(1 for r in accepted_records if r["status"] == "FAIL")
        absent_count = sum(1 for r in accepted_records if r["status"] == "ABSENT")
        evaluated_count = passed_count + failed_count
        pass_pct = round((passed_count / evaluated_count) * 100, 2) if evaluated_count > 0 else 0.0

        scores = [r["total_marks"] for r in accepted_records if r["total_marks"] is not None]
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0

        class_summary = {
            "total_students": len(student_rows),
            "total_subject_records": len(accepted_records),
            "passed_records": passed_count,
            "failed_records": failed_count,
            "absent_records": absent_count,
            "pass_percentage": pass_pct,
            "average_score": avg_score
        }

        return accepted_records, master_tally, class_summary

    def commit_class_entry(
        self,
        class_metadata: Dict[str, Any],
        subjects: List[Dict[str, Any]],
        student_rows: List[Dict[str, Any]],
        draft_id: Optional[str] = None,
        comments: str = ""
    ) -> Dict[str, Any]:
        """
        Validates, persists to data/validated/VAL_{dataset_id}.csv,
        signs JSON manifest, and deletes draft if specified.
        """
        dataset_id = str(uuid.uuid4())
        accepted_records, tally, summary = self.unpivot_and_validate(
            class_metadata=class_metadata,
            subjects=subjects,
            student_rows=student_rows
        )

        if not tally.is_valid_to_commit:
            raise ValueError("Zero valid student records to commit.")

        # 1. Save validated CSV dataset
        val_df = pd.DataFrame(accepted_records)
        val_csv_content = val_df.to_csv(index=False)
        val_path = self.storage.save_validated_dataset(dataset_id, val_csv_content)

        # 2. Also save raw snapshot of entered grid as CSV
        grid_csv = self.generate_csv_template(subjects, student_rows)
        raw_path, sha256_hash, file_size = self.storage.save_raw_upload(
            dataset_id=dataset_id,
            original_filename=f"class_entry_{class_metadata.get('department', 'GEN')}_sem{class_metadata.get('semester', 1)}.csv",
            file_bytes=grid_csv.encode("utf-8")
        )

        # 3. Create Manifest
        now_iso = datetime.now(timezone.utc).isoformat()
        manifest = {
            "manifest_version": "1.0.0",
            "dataset_id": dataset_id,
            "import_timestamp": now_iso,
            "comments": comments or f"Class entry for {class_metadata.get('department')} Sem {class_metadata.get('semester')}",
            "source_file": {
                "original_filename": raw_path.name,
                "stored_filename": raw_path.name,
                "file_size_bytes": file_size,
                "sha256_checksum": sha256_hash,
                "sheet_name": "DirectEntry",
                "header_row_index": 0
            },
            "model_type": "marks_based",
            "row_counts": {
                "total_raw_rows": tally.total_raw_rows,
                "accepted_rows": tally.accepted_rows,
                "rejected_rows": tally.rejected_rows,
                "duplicate_rows": tally.duplicate_rows,
                "incomplete_rows": tally.incomplete_rows
            },
            "class_summary": summary,
            "validation_summary": tally.to_dict(),
            "storage_locations": {
                "raw_path": str(raw_path),
                "validated_path": str(val_path),
                "processed_parquet_dir": f"data/processed/PROC_{dataset_id}"
            }
        }
        self.storage.save_manifest(dataset_id, manifest)

        # 4. Clean up draft if provided
        if draft_id:
            self.storage.delete_draft(draft_id)

        logger.info(f"Class marks committed: Dataset {dataset_id} ({tally.accepted_rows} records)")
        return manifest

    def generate_csv_template(
        self,
        subjects: List[Dict[str, Any]],
        student_rows: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Generates CSV template with headers:
        student_id, {sub_code}_internal, {sub_code}_external, ...
        """
        headers = ["student_id"]
        for sub in subjects:
            code = str(sub.get("code") or "").strip().upper()
            headers.extend([f"{code}_internal", f"{code}_external"])

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)

        if student_rows:
            for student in student_rows:
                row = [student.get("student_id", "")]
                marks = student.get("marks", {})
                for sub in subjects:
                    code = str(sub.get("code") or "").strip().upper()
                    sub_m = marks.get(code, {})
                    row.append(sub_m.get("internal", ""))
                    row.append(sub_m.get("external", ""))
                writer.writerow(row)

        return output.getvalue()

    def parse_csv_into_grid(
        self,
        csv_text: str,
        subjects: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Parses uploaded CSV into the student_rows grid format.
        """
        df = pd.read_csv(io.StringIO(csv_text))
        student_rows = []

        # Find student ID column
        id_col = None
        for col in df.columns:
            if any(k in col.lower() for k in ["student", "roll", "reg", "id"]):
                id_col = col
                break
        if not id_col and len(df.columns) > 0:
            id_col = df.columns[0]

        for _, row in df.iterrows():
            stu_id = str(row[id_col]).strip() if id_col and pd.notna(row[id_col]) else ""
            if not stu_id:
                continue

            marks_dict = {}
            for sub in subjects:
                code = str(sub.get("code") or "").strip().upper()
                int_col = next((c for c in df.columns if code.lower() in c.lower() and "int" in c.lower()), None)
                ext_col = next((c for c in df.columns if code.lower() in c.lower() and "ext" in c.lower()), None)

                raw_int = row[int_col] if int_col and pd.notna(row[int_col]) else None
                raw_ext = row[ext_col] if ext_col and pd.notna(row[ext_col]) else None

                marks_dict[code] = {
                    "internal": raw_int,
                    "external": raw_ext
                }

            student_rows.append({
                "student_id": stu_id,
                "marks": marks_dict
            })

        return student_rows
