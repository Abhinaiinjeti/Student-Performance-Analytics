"""
EduPulse Analytics - Universal Academic Assessment Import Engine
Handles multi-sheet inspection, intelligent header row heuristics, banner filtering,
wide-to-long unpivoting, layout auto-detection, cell-level validation, and dataset registration
across CSV, XLSX, and XLS formats.
"""
import io
import re
import csv
import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Set
import pandas as pd
from storage.local_storage import LocalStorage
from src.data_validation import DataValidationService, ValidationTally
from config.assessment_rules import AssessmentRules, AssessmentTypeConfig, STANDARD_ASSESSMENT_TYPES

logger = logging.getLogger(__name__)


class ImportService:
    """
    Universal ingestion engine for academic assessment records.
    Supports wide matrix spreadsheets (one row per student with subject columns),
    long tabular records, multi-sheet workbooks, banner rows, and diverse assessment types:
    Semester Exams, Mid-1, Mid-2, Internal Assessments, Labs, Assignments, Quizzes, Projects, Vivas.
    """
    CANONICAL_MARKS_FIELDS = [
        "student_id", "subject_code", "subject_name",
        "internal_marks", "external_marks", "semester",
        "department", "batch", "section", "academic_year", "attendance_pct"
    ]

    CANONICAL_GRADE_FIELDS = [
        "student_id", "subject_code", "subject_name",
        "letter_grade", "course_credits", "sgpa",
        "semester", "department", "exam_type", "academic_year"
    ]

    # Keyword dictionaries for column heuristics
    MAPPING_KEYWORDS = {
        "student_id": ["roll", "reg", "usn", "htno", "ht_no", "ht no", "hall_ticket", "student_id", "id", "enrollment", "regno"],
        "student_name": ["name", "student_name", "candidate_name", "full_name"],
        "subject_code": ["sub_code", "course_code", "paper_code", "subcode", "subject_code", "course_id"],
        "subject_name": ["subject_name", "sub_name", "course_name", "title", "paper_name", "subject"],
        "internal_marks": ["internal", "cia", "int", "midterm", "sessional", "ca", "internal_marks"],
        "external_marks": ["external", "ese", "ext", "endsem", "theory", "external_marks", "final_exam"],
        "letter_grade": ["grade", "letter_grade", "letter", "lg", "grade_secured", "final_grade"],
        "sgpa": ["sgpa", "gpa", "spi", "semester_gpa", "sgpa_points"],
        "course_credits": ["credits", "credit", "cr", "course_credits"],
        "semester": ["semester", "sem", "term"],
        "department": ["department", "dept", "branch", "program"],
        "batch": ["batch", "cohort", "admission_year"],
        "section": ["section", "sec", "div", "division"],
        "academic_year": ["academic_year", "ay", "year"]
    }

    SERIAL_KEYWORDS = ["s.no", "sl.no", "sno", "slno", "sr.no", "sr_no", "sr no", "serial", "serial_no", "index", "#"]
    METADATA_COLUMN_KEYWORDS = [
        "s.no", "sl.no", "sno", "slno", "sr.no", "sr_no", "serial", "index", "#",
        "student_id", "roll", "reg", "usn", "htno", "hall_ticket", "enrollment",
        "name", "student_name", "candidate", "full_name",
        "dept", "department", "branch", "program",
        "sem", "semester", "term",
        "section", "sec", "batch", "cohort", "academic_year", "ay", "year",
        "sgpa", "cgpa", "gpa", "spi",
        "total", "grand_total", "total_marks", "percentage", "%", "result", "status", "remarks"
    ]

    def __init__(self, storage: Optional[LocalStorage] = None, validation: Optional[DataValidationService] = None):
        self.storage = storage or LocalStorage()
        self.validation = validation or DataValidationService()

    def inspect_file(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Inspects workbook, discovers all worksheets, finds header row (skipping banner titles),
        detects layout (Wide vs Long), identifies student ID column, subject columns,
        and auto-detects academic assessment type.
        """
        ext = Path(filename).suffix.lower()
        sheet_names = ["Sheet1"]

        # 1. Discover sheets for Excel
        if ext in (".xlsx", ".xlsm", ".xls"):
            try:
                excel_file = pd.ExcelFile(io.BytesIO(file_bytes))
                sheet_names = excel_file.sheet_names
            except Exception as e:
                logger.warning(f"Could not read Excel sheets with default engine: {e}")
                if ext == ".xls":
                    try:
                        excel_file = pd.ExcelFile(io.BytesIO(file_bytes), engine="xlrd")
                        sheet_names = excel_file.sheet_names
                    except Exception as e2:
                        logger.error(f"Failed to read XLS sheet names: {e2}")

        # 2. Inspect first sheet
        first_sheet = sheet_names[0]
        sample_df = self._read_sample_dataframe(file_bytes, ext, first_sheet, max_rows=30)

        # 3. Detect header row skipping banners
        header_row_idx, banner_text = self._detect_header_row_and_banners(sample_df)

        # 4. Extract headers
        raw_headers: List[str] = []
        if header_row_idx < len(sample_df):
            raw_headers = [
                str(col).strip() if pd.notna(col) else f"Column_{i}"
                for i, col in enumerate(sample_df.iloc[header_row_idx].tolist())
            ]
        else:
            raw_headers = [str(col).strip() for col in sample_df.columns]

        # Clean empty header names
        clean_headers = [h if h and h.lower() != "nan" else f"Column_{i}" for i, h in enumerate(raw_headers)]

        # 5. Detect Student ID column (filtering out S.No)
        student_id_col = self._detect_student_id_column(clean_headers, sample_df, header_row_idx)
        student_name_col = self._detect_student_name_column(clean_headers)
        serial_col = self._detect_serial_column(clean_headers)

        # 6. Model signature detection (Marks vs Grade)
        suggested_model = self._detect_model_signature(clean_headers, sample_df, header_row_idx)

        # 7. Layout auto-detection (Wide vs Long)
        layout, subject_cols, metadata_cols = self._detect_layout_and_subjects(
            clean_headers, student_id_col, student_name_col, serial_col
        )

        # 8. Assessment type auto-detection
        suggested_asmt = self._detect_assessment_type(banner_text, filename, first_sheet, clean_headers)

        # 9. Suggest 1:1 mappings for Long layout
        canonical_fields = self.CANONICAL_MARKS_FIELDS if suggested_model == "marks_based" else self.CANONICAL_GRADE_FIELDS
        suggested_mappings = self._suggest_mappings(clean_headers, canonical_fields)

        # 10. Sheet summaries for multi-sheet support
        sheet_summaries = []
        for s_name in sheet_names:
            sheet_summaries.append({
                "sheet_name": s_name,
                "is_default": (s_name == first_sheet)
            })

        # 11. Column type detection (Theory vs Lab)
        subject_cols_meta = []
        for col in subject_cols:
            col_u = col.upper()
            is_lab = any(kw in col_u for kw in ["LAB", "PRACTICAL", "PR.", "PR ", "-PR", "-LAB", "_LAB", "WORKSHOP"])
            subject_cols_meta.append({
                "column_name": col,
                "is_lab": is_lab,
                "type": "LABORATORY" if is_lab else "THEORY"
            })

        return {
            "original_filename": filename,
            "file_size_bytes": len(file_bytes),
            "sheets": sheet_names,
            "selected_sheet": first_sheet,
            "sheet_summaries": sheet_summaries,
            "detected_header_row": header_row_idx,
            "banner_text": banner_text,
            "suggested_model": suggested_model,
            "detected_layout": layout,  # 'wide' or 'long'
            "detected_student_id_column": student_id_col,
            "detected_student_name_column": student_name_col,
            "detected_serial_column": serial_col,
            "candidate_subject_columns": subject_cols,
            "candidate_subject_columns_meta": subject_cols_meta,
            "metadata_columns": metadata_cols,
            "suggested_assessment_type": suggested_asmt,
            "available_assessment_types": self.validation.rules.list_assessment_types(),
            "raw_headers": clean_headers,
            "suggested_mappings": suggested_mappings
        }

    def generate_preview(
        self,
        file_bytes: bytes,
        filename: str,
        sheet_name: str,
        header_row: int,
        column_mappings: Optional[Dict[str, str]] = None,
        model_type: str = "marks_based",
        layout: str = "auto",
        student_id_col: Optional[str] = None,
        subject_cols: Optional[List[str]] = None,
        student_name_col: Optional[str] = None,
        assessment_type: str = "mid_1",
        default_max_marks: Optional[float] = None,
        default_pass_marks: Optional[float] = None,
        default_semester: int = 1,
        default_department: str = "General",
        max_rows: int = 25
    ) -> Dict[str, Any]:
        """
        Generates mapped preview rows and validation scorecards.
        Supports both Wide matrix spreadsheets (unpivoting subject columns) and Long tabular schemas.
        """
        ext = Path(filename).suffix.lower()
        df = self._read_full_dataframe(file_bytes, ext, sheet_name=sheet_name, header_row=header_row)

        column_mappings = column_mappings or {}

        # Determine effective layout
        effective_layout = layout
        if effective_layout == "auto":
            # If explicit column mappings for long format (subject_code + marks) are present, use long
            has_long_mappings = "subject_code" in column_mappings and (
                "internal_marks" in column_mappings or "letter_grade" in column_mappings
            )
            effective_layout = "long" if has_long_mappings else ("wide" if subject_cols else "long")

        if effective_layout == "wide" and (subject_cols or student_id_col):
            # WIDE LAYOUT UNPIVOTING
            s_id_col = student_id_col or column_mappings.get("student_id")
            if not s_id_col:
                # Find student id column heuristically
                s_id_col = self._detect_student_id_column(list(df.columns), df.head(10), 0)

            s_cols = subject_cols or [c for c in df.columns if c not in self.METADATA_COLUMN_KEYWORDS and c != s_id_col]

            unpivoted_records = self._unpivot_wide_dataframe(
                df=df,
                student_id_col=s_id_col,
                subject_cols=s_cols,
                student_name_col=student_name_col,
                model_type=model_type,
                assessment_type=assessment_type,
                default_max_marks=default_max_marks,
                default_pass_marks=default_pass_marks,
                default_semester=default_semester,
                default_department=default_department
            )

            # Validate unpivoted sample
            accepted_sample, sample_tally = self.validation.validate_canonical_records(
                records=unpivoted_records[:100],
                default_assessment_type=assessment_type,
                default_max_marks=default_max_marks,
                default_pass_marks=default_pass_marks
            )

            preview_records = accepted_sample[:max_rows]
            cols = list(preview_records[0].keys()) if preview_records else []

            return {
                "layout": "wide",
                "preview_rows": preview_records,
                "total_unpivoted_count": len(unpivoted_records),
                "total_columns": len(cols),
                "columns": cols,
                "sample_tally": sample_tally.to_dict()
            }

        else:
            # LONG LAYOUT (Backward Compatible)
            inv_map = {src: dst for dst, src in column_mappings.items() if src and src in df.columns}
            preview_df = df.rename(columns=inv_map)

            # Retain mapped columns
            mapped_cols = [dst for dst in column_mappings.keys() if dst in preview_df.columns]
            if mapped_cols:
                preview_df = preview_df[mapped_cols]

            preview_records = preview_df.head(max_rows).to_dict(orient="records")

            if model_type == "marks_based":
                _, sample_tally = self.validation.validate_marks_records(preview_records)
            else:
                _, sample_tally = self.validation.validate_grade_records(preview_records)

            return {
                "layout": "long",
                "preview_rows": preview_records,
                "total_columns": len(preview_df.columns),
                "columns": list(preview_df.columns),
                "sample_tally": sample_tally.to_dict()
            }

    def commit_import(
        self,
        file_bytes: bytes,
        original_filename: str,
        sheet_name: str = "Sheet1",
        header_row: int = 0,
        column_mappings: Optional[Dict[str, str]] = None,
        model_type: str = "marks_based",
        layout: str = "auto",
        student_id_col: Optional[str] = None,
        subject_cols: Optional[List[str]] = None,
        student_name_col: Optional[str] = None,
        assessment_type: str = "mid_1",
        default_max_marks: Optional[float] = None,
        default_pass_marks: Optional[float] = None,
        default_semester: int = 1,
        default_department: str = "General",
        comments: str = "",
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Commits validated dataset: saves untouched raw file to data/raw/,
        normalizes unpivoted or long records, validates, saves tabular CSV to data/validated/VAL_{dataset_id}.csv,
        and signs cryptographic manifest in data/manifests/MAN_{dataset_id}.json.
        """
        dataset_id = str(uuid.uuid4())
        ext = Path(original_filename).suffix.lower()
        column_mappings = column_mappings or {}

        # 1. Permanently save untouched raw source file
        raw_path, sha256_hash, file_size = self.storage.save_raw_upload(
            dataset_id=dataset_id,
            original_filename=original_filename,
            file_bytes=file_bytes
        )

        # 2. Read full dataset
        df = self._read_full_dataframe(file_bytes, ext, sheet_name=sheet_name, header_row=header_row)

        # 3. Determine Layout & Transform
        effective_layout = layout
        if effective_layout == "auto":
            has_long_mappings = "subject_code" in column_mappings and (
                "internal_marks" in column_mappings or "letter_grade" in column_mappings
            )
            effective_layout = "long" if has_long_mappings else ("wide" if (subject_cols or student_id_col) else "long")

        if effective_layout == "wide":
            s_id_col = student_id_col or column_mappings.get("student_id")
            if not s_id_col:
                s_id_col = self._detect_student_id_column(list(df.columns), df.head(10), 0)

            s_cols = subject_cols or [c for c in df.columns if c not in self.METADATA_COLUMN_KEYWORDS and c != s_id_col]

            unpivoted_records = self._unpivot_wide_dataframe(
                df=df,
                student_id_col=s_id_col,
                subject_cols=s_cols,
                student_name_col=student_name_col,
                model_type=model_type,
                assessment_type=assessment_type,
                default_max_marks=default_max_marks,
                default_pass_marks=default_pass_marks,
                default_semester=default_semester,
                default_department=default_department
            )

            # Validate unpivoted records
            accepted_records, tally = self.validation.validate_canonical_records(
                records=unpivoted_records,
                default_assessment_type=assessment_type,
                default_max_marks=default_max_marks,
                default_pass_marks=default_pass_marks
            )

        else:
            # LONG LAYOUT (Backward Compatible)
            inv_map = {src: dst for dst, src in column_mappings.items() if src and src in df.columns}
            mapped_df = df.rename(columns=inv_map)
            records = mapped_df.to_dict(orient="records")

            if model_type == "marks_based":
                accepted_records, tally = self.validation.validate_marks_records(records)
            else:
                accepted_records, tally = self.validation.validate_grade_records(records)

        if not tally.is_valid_to_commit:
            raise ValueError(f"Cannot commit dataset {dataset_id}: Zero accepted rows passed validation.")

        # 4. Persist normalized tabular dataset (data/validated/VAL_{dataset_id}.csv)
        val_df = pd.DataFrame(accepted_records)
        val_csv_content = val_df.to_csv(index=False)
        val_path = self.storage.save_validated_dataset(dataset_id, val_csv_content)

        # 5. Generate Cryptographic Manifest (data/manifests/MAN_{dataset_id}.json)
        now_iso = datetime.now(timezone.utc).isoformat()
        manifest = {
            "manifest_version": "2.0.0",
            "dataset_id": dataset_id,
            "import_timestamp": now_iso,
            "comments": comments,
            "source_file": {
                "original_filename": original_filename,
                "stored_filename": raw_path.name,
                "file_size_bytes": file_size,
                "sha256_checksum": sha256_hash,
                "sheet_name": sheet_name,
                "header_row_index": header_row
            },
            "model_type": model_type,
            "layout": effective_layout,
            "assessment_type": assessment_type if effective_layout == "wide" else "standard",
            "row_counts": {
                "total_raw_rows": tally.total_raw_rows,
                "accepted_rows": tally.accepted_rows,
                "rejected_rows": tally.rejected_rows,
                "duplicate_rows": tally.duplicate_rows,
                "incomplete_rows": tally.incomplete_rows
            },
            "column_mappings": column_mappings,
            "validation_summary": tally.to_dict(),
            "storage_locations": {
                "raw_path": str(raw_path),
                "validated_path": str(val_path),
                "processed_parquet_dir": f"data/processed/PROC_{dataset_id}"
            }
        }

        # Resolve and link to target academic batch project
        target_project_id = project_id
        try:
            from services.project_service import ProjectService
            ps = ProjectService(config=self.config, storage=self.storage)
            if not target_project_id:
                active_p = ps.get_active_project()
                if active_p:
                    target_project_id = active_p["project_id"]
            if target_project_id:
                ps.link_dataset_to_project(target_project_id, dataset_id)
        except Exception as e:
            logger.warning(f"Could not link dataset {dataset_id} to project: {e}")

        manifest["project_id"] = target_project_id
        self.storage.save_manifest(dataset_id, manifest)

        logger.info(f"Universal import committed: Dataset {dataset_id} ({tally.accepted_rows} rows accepted, layout: {effective_layout}, project: {target_project_id})")
        return manifest

    # ---------------------------------------------------------
    # Helper & Detection Methods
    # ---------------------------------------------------------
    def _read_sample_dataframe(self, file_bytes: bytes, ext: str, sheet_name: str, max_rows: int = 30) -> pd.DataFrame:
        """Reads sample rows preserving exact string representations (leading zeroes)."""
        stream = io.BytesIO(file_bytes)
        if ext in (".xlsx", ".xlsm"):
            return pd.read_excel(stream, sheet_name=sheet_name, nrows=max_rows, header=None, dtype=str)
        elif ext == ".xls":
            try:
                return pd.read_excel(stream, sheet_name=sheet_name, nrows=max_rows, header=None, dtype=str, engine="xlrd")
            except Exception:
                return pd.read_excel(stream, sheet_name=sheet_name, nrows=max_rows, header=None, dtype=str)
        else:
            # CSV with delimiter sniffing
            return self._read_csv_with_sniffer(file_bytes, max_rows=max_rows, header=None)

    def _read_full_dataframe(self, file_bytes: bytes, ext: str, sheet_name: str, header_row: int) -> pd.DataFrame:
        """Reads full dataframe preserving strings (protecting alphanumeric IDs and leading zeros)."""
        stream = io.BytesIO(file_bytes)
        if ext in (".xlsx", ".xlsm"):
            return pd.read_excel(stream, sheet_name=sheet_name, header=header_row, dtype=str)
        elif ext == ".xls":
            try:
                return pd.read_excel(stream, sheet_name=sheet_name, header=header_row, dtype=str, engine="xlrd")
            except Exception:
                return pd.read_excel(stream, sheet_name=sheet_name, header=header_row, dtype=str)
        else:
            return self._read_csv_with_sniffer(file_bytes, max_rows=None, header=header_row)

    def _read_csv_with_sniffer(self, file_bytes: bytes, max_rows: Optional[int], header: Any) -> pd.DataFrame:
        """Sniffs delimiter and encoding for CSV files, reading all values as strings."""
        encodings_to_try = ["utf-8-sig", "utf-8", "cp1252", "latin1"]
        decoded_sample = None
        used_encoding = "utf-8"

        for enc in encodings_to_try:
            try:
                decoded_sample = file_bytes[:4096].decode(enc)
                used_encoding = enc
                break
            except UnicodeDecodeError:
                continue

        sep = ","
        if decoded_sample:
            try:
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(decoded_sample)
                sep = dialect.delimiter
            except Exception:
                # Fallback: check most common delimiter in first few lines
                lines = decoded_sample.splitlines()[:5]
                text = "\n".join(lines)
                counts = {",": text.count(","), ";": text.count(";"), "\t": text.count("\t"), "|": text.count("|")}
                best_delim = max(counts, key=counts.get)
                if counts[best_delim] > 0:
                    sep = best_delim

        stream = io.BytesIO(file_bytes)
        return pd.read_csv(stream, sep=sep, encoding=used_encoding, nrows=max_rows, header=header, dtype=str)

    def _detect_header_row_and_banners(self, sample_df: pd.DataFrame) -> Tuple[int, str]:
        """
        Detects the genuine table header row while identifying and collecting title banner text.
        Skips college banners, addresses, and exam name headers.
        """
        best_row = 0
        best_score = -1
        banners: List[str] = []

        header_markers = {
            "roll", "reg", "id", "student", "usn", "htno", "ht no", "hall ticket",
            "s.no", "sl.no", "sno", "sub", "code", "mark", "grade", "internal",
            "external", "sgpa", "mid", "lab", "subject", "name"
        }

        limit = min(20, len(sample_df))
        for idx in range(limit):
            row_vals = [str(x).strip() for x in sample_df.iloc[idx].dropna().tolist()]
            if not row_vals:
                continue

            row_lower = [v.lower() for v in row_vals]
            score = sum(1 for v in row_lower if any(m in v for m in header_markers))

            # Check if this row is an institutional banner (e.g. 1 or 2 long text cells spanning width)
            if len(row_vals) <= 3 and any(len(v) > 25 for v in row_vals):
                banners.extend(row_vals)
                continue

            if score > best_score:
                best_score = score
                best_row = idx

        banner_text = " | ".join(banners)
        return best_row, banner_text

    def _detect_student_id_column(self, headers: List[str], sample_df: pd.DataFrame, header_row: int) -> Optional[str]:
        """
        Finds the student identifier column, strictly distinguishing it from serial numbers (S.No).
        """
        id_keywords = ["htno", "ht no", "ht_no", "roll no", "roll_no", "roll", "reg no", "reg_no", "regno", "usn", "student_id", "hall_ticket", "enrollment", "reg"]
        serial_keywords = ["s.no", "sl.no", "sno", "slno", "sr.no", "sr no", "serial", "index", "#"]

        candidates = []
        for h in headers:
            h_clean = h.lower().replace("_", " ").strip()
            # If header is explicitly a serial number, ignore
            if any(s == h_clean or s in h_clean.split() for s in serial_keywords):
                continue
            for kw in id_keywords:
                if kw in h_clean:
                    candidates.append((h, kw))
                    break

        if candidates:
            # Sort by keyword specificity
            candidates.sort(key=lambda x: len(x[1]), reverse=True)
            return candidates[0][0]

        # Content-based heuristic inspection if header didn't directly match
        if header_row + 1 < len(sample_df):
            data_rows = sample_df.iloc[header_row + 1: header_row + 6]
            for col_idx in range(min(5, sample_df.shape[1])):
                col_vals = [str(v).strip() for v in data_rows.iloc[:, col_idx].dropna().tolist()]
                # If values are alphanumeric (contain both letters and digits) like '22R11A05C0' or 'STU001'
                if any(re.search(r"[A-Za-z]", v) and re.search(r"\d", v) for v in col_vals):
                    if col_idx < len(headers):
                        return headers[col_idx]

        return None

    def _detect_student_name_column(self, headers: List[str]) -> Optional[str]:
        """Identifies student name column."""
        for h in headers:
            h_clean = h.lower().replace("_", " ").strip()
            if "name" in h_clean and "subject" not in h_clean and "course" not in h_clean and "sub" not in h_clean:
                return h
        return None

    def _detect_serial_column(self, headers: List[str]) -> Optional[str]:
        """Identifies serial number column (S.No / Sl.No)."""
        for h in headers:
            h_clean = h.lower().replace("_", " ").strip()
            if any(s == h_clean or s in h_clean.split() for s in self.SERIAL_KEYWORDS):
                return h
        return None

    def _detect_layout_and_subjects(
        self,
        headers: List[str],
        student_id_col: Optional[str],
        student_name_col: Optional[str],
        serial_col: Optional[str]
    ) -> Tuple[str, List[str], List[str]]:
        """
        Auto-detects layout (Wide vs Long) and separates subject columns from metadata columns.
        """
        metadata_cols: List[str] = []
        subject_cols: List[str] = []

        headers_lower = [h.lower() for h in headers]
        has_long_subject = any(kw in " ".join(headers_lower) for kw in ["subject_code", "course_code", "sub_code", "subcode"])
        has_long_marks = any(kw in " ".join(headers_lower) for kw in ["internal_marks", "external_marks", "cia_marks", "ese_marks"])

        # Long layout heuristic
        if has_long_subject and has_long_marks:
            return "long", [], headers

        # Categorize columns
        for h in headers:
            h_clean = h.lower().replace("_", " ").replace("-", " ").strip()
            if h in (student_id_col, student_name_col, serial_col):
                metadata_cols.append(h)
            elif any(kw == h_clean or kw in h_clean.split() for kw in self.METADATA_COLUMN_KEYWORDS):
                metadata_cols.append(h)
            elif h.upper() in ("SGPA", "CGPA", "GPA", "SPI"):
                metadata_cols.append(h)
            else:
                subject_cols.append(h)

        layout = "wide" if (student_id_col and len(subject_cols) >= 2) else "long"
        return layout, subject_cols, metadata_cols

    def _detect_assessment_type(self, banner_text: str, filename: str, sheet_name: str, headers: List[str]) -> str:
        """Infers assessment type from banners, file/sheet names, and header text."""
        # 1. High-confidence document context (filename, banner, sheet name)
        doc_context = f"{banner_text} {filename} {sheet_name}".lower()

        if any(kw in doc_context for kw in ["mid 1", "mid-1", "mid_1", "mid1", "midterm 1", "midterm-1", "i mid", "1st mid"]):
            return "mid_1"
        if any(kw in doc_context for kw in ["mid 2", "mid-2", "mid_2", "mid2", "midterm 2", "midterm-2", "ii mid", "2nd mid"]):
            return "mid_2"
        if any(kw in doc_context for kw in ["semester", "regular", "endsem", "external", "university", "results"]):
            return "semester_exam"
        if any(kw in doc_context for kw in ["internal", "cia", "sessional", "continuous", "mid marks", "mid_marks", "mid exam"]):
            return "internal"
        if any(kw in doc_context for kw in ["lab", "practical", "laboratory"]):
            return "laboratory"
        if any(kw in doc_context for kw in ["assignment", "homework", "tutorial"]):
            return "assignment"
        if any(kw in doc_context for kw in ["quiz", "class test", "objective"]):
            return "quiz"
        if any(kw in doc_context for kw in ["project", "seminar", "presentation"]):
            return "project"
        if any(kw in doc_context for kw in ["viva", "oral"]):
            return "viva"

        # 2. Secondary fallback: Examine column headers
        headers_str = " ".join(headers).lower()
        if any(kw in headers_str for kw in ["mid 1", "mid-1", "mid1"]):
            return "mid_1"
        if any(kw in headers_str for kw in ["mid 2", "mid-2", "mid2"]):
            return "mid_2"
        if any(kw in headers_str for kw in ["grade", "sgpa", "cgpa"]):
            return "semester_exam"
        if any(kw in headers_str for kw in ["mid", "internal", "sessional"]):
            return "internal"
        if all("lab" in h.lower() or "practical" in h.lower() for h in headers if h and len(h) > 2):
            return "laboratory"

        return "internal"

    def _detect_model_signature(self, headers: List[str], sample_df: pd.DataFrame, header_row: int) -> str:
        """Determines if spreadsheet signature matches Marks-Based or Grade-Based model."""
        headers_lower = " ".join([h.lower() for h in headers])
        grade_signals = sum(1 for kw in ["grade", "sgpa", "cgpa", "letter", "credit"] if kw in headers_lower)
        marks_signals = sum(1 for kw in ["internal", "external", "total", "theory", "practical", "cia", "ese", "mid", "marks"] if kw in headers_lower)

        # Inspect data values below header
        if header_row + 1 < len(sample_df):
            sample_vals = [str(x).strip().upper() for x in sample_df.iloc[header_row + 1: header_row + 5].values.flatten() if pd.notna(x)]
            letter_grades = {"O", "A+", "A", "B+", "B", "C", "P", "F"}
            if sum(1 for v in sample_vals if v in letter_grades) > 5:
                grade_signals += 5

        if grade_signals > marks_signals:
            return "grade_based"
        return "marks_based"

    def _suggest_mappings(self, raw_headers: List[str], canonical_fields: List[str]) -> Dict[str, Optional[str]]:
        """Maps canonical schema fields to best matching raw spreadsheet header for Long layout."""
        suggestions: Dict[str, Optional[str]] = {}
        for canonical in canonical_fields:
            keywords = self.MAPPING_KEYWORDS.get(canonical, [canonical])
            match = None
            for raw in raw_headers:
                raw_clean = raw.lower().replace(" ", "_").replace("-", "_")
                if any(kw in raw_clean for kw in keywords):
                    match = raw
                    break
            suggestions[canonical] = match
        return suggestions

    def _unpivot_wide_dataframe(
        self,
        df: pd.DataFrame,
        student_id_col: str,
        subject_cols: List[str],
        student_name_col: Optional[str] = None,
        model_type: str = "marks_based",
        assessment_type: str = "mid_1",
        default_max_marks: Optional[float] = None,
        default_pass_marks: Optional[float] = None,
        default_semester: int = 1,
        default_department: str = "General",
        skip_empty_electives: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Unpivots wide student assessment matrices into canonical normalized assessment records.
        Preserves string student IDs with leading zeroes, evaluates subject codes/names from column headers,
        and isolates absent / incomplete / valid results.
        """
        records: List[Dict[str, Any]] = []
        asmt_cfg = self.validation.rules.get_assessment_type(assessment_type)

        max_marks = default_max_marks if default_max_marks is not None else asmt_cfg.default_max_marks
        pass_marks = default_pass_marks if default_pass_marks is not None else asmt_cfg.default_pass_marks

        # Clean subject headers into (code, name) tuples
        subject_meta = {}
        for col in subject_cols:
            clean_name = col.replace("\n", " ").strip()
            # If header looks like '20CS32001- IoT' or 'CS101: Mathematics'
            if "-" in clean_name:
                parts = clean_name.split("-", 1)
                s_code = parts[0].strip()
                s_name = parts[1].strip() or s_code
            elif ":" in clean_name:
                parts = clean_name.split(":", 1)
                s_code = parts[0].strip()
                s_name = parts[1].strip() or s_code
            else:
                s_code = clean_name.replace(" ", "_").upper()
                s_name = clean_name
            subject_meta[col] = (s_code, s_name)

        # Detect optional row-level metadata columns in df
        dept_col = next((c for c in df.columns if c.lower() in ("dept", "department", "branch")), None)
        sem_col = next((c for c in df.columns if c.lower() in ("sem", "semester")), None)
        sec_col = next((c for c in df.columns if c.lower() in ("section", "sec")), None)
        batch_col = next((c for c in df.columns if c.lower() in ("batch", "cohort")), None)
        ay_col = next((c for c in df.columns if c.lower() in ("academic_year", "ay", "year")), None)
        sgpa_col = next((c for c in df.columns if c.upper() in ("SGPA", "GPA", "SPI")), None)

        for _, row in df.iterrows():
            raw_id = row.get(student_id_col)
            if pd.isna(raw_id) or str(raw_id).strip() == "" or str(raw_id).strip().lower() == "nan":
                continue

            student_id = str(raw_id).strip()
            # Skip if student_id is a header repeat
            if student_id.lower() in ("ht no", "roll no", "student id", "student_id", "htno", "reg no"):
                continue

            student_name = str(row.get(student_name_col) or "").strip() if student_name_col else ""
            department = str(row.get(dept_col) or default_department).strip() if dept_col else default_department
            
            raw_sem = row.get(sem_col) if sem_col else default_semester
            try:
                semester = int(str(raw_sem).strip())
            except (ValueError, TypeError):
                semester = default_semester

            section = str(row.get(sec_col) or "").strip() if sec_col else ""
            batch = str(row.get(batch_col) or "").strip() if batch_col else ""
            academic_year = str(row.get(ay_col) or "").strip() if ay_col else ""
            
            raw_sgpa = row.get(sgpa_col) if sgpa_col else None
            sgpa = self.validation._safe_float(raw_sgpa)

            # Unpivot each subject column
            for col in subject_cols:
                raw_val = row.get(col)
                # If elective cell is empty/NaN, skip if skip_empty_electives is enabled
                if pd.isna(raw_val) or str(raw_val).strip() in ("", "-", "None", "nan", "NULL", "NA"):
                    if skip_empty_electives:
                        continue
                    else:
                        val_str = ""
                else:
                    val_str = str(raw_val).strip()

                s_code, s_name = subject_meta[col]

                # Auto-classify Theory vs Laboratory per subject column
                col_u = col.upper()
                is_col_lab = any(kw in col_u for kw in ["LAB", "PRACTICAL", "PR.", "PR ", "-PR", "-LAB", "_LAB", "WORKSHOP"])
                if is_col_lab:
                    col_assessment_type = "laboratory"
                    col_assessment_name = "Laboratory / Practical"
                    subject_type = "LABORATORY"
                else:
                    col_assessment_type = assessment_type
                    col_assessment_name = asmt_cfg.display_name
                    subject_type = "THEORY"

                # Distinguish marks vs grade
                marks_obtained: Optional[float] = None
                letter_grade: Optional[str] = None
                result_status = "PASS"
                attendance_status = "PRESENT"

                grade_points: Optional[float] = None
                val_upper = val_str.upper()
                if val_upper in ("AB", "ABS", "ABSENT"):
                    result_status = "ABSENT"
                    attendance_status = "ABSENT"
                    if model_type == "grade_based":
                        letter_grade = "AB"
                elif val_upper in ("W", "WH", "WITHHELD"):
                    result_status = "WITHHELD"
                    if model_type == "grade_based":
                        letter_grade = "WH"
                elif val_upper in ("I", "INCOMPLETE"):
                    result_status = "INCOMPLETE"
                else:
                    if model_type == "grade_based":
                        letter_grade = val_upper
                        g_status, g_pts = self.validation.rules.grade_rule.classify_grade(val_upper)
                        grade_points = g_pts
                        result_status = "PASS" if g_status == "PASSED" else ("FAIL" if g_status == "FAILED" else g_status)
                        if g_status == "ABSENT":
                            attendance_status = "ABSENT"
                    else:
                        # Numeric marks
                        parsed = self.validation._safe_float(val_str)
                        if parsed is not None:
                            marks_obtained = parsed
                            result_status = "PASS" if (pass_marks is None or marks_obtained >= pass_marks) else "FAIL"
                        else:
                            # Might be a letter grade in a mixed sheet
                            letter_grade = val_upper
                            g_status, g_pts = self.validation.rules.grade_rule.classify_grade(val_upper)
                            grade_points = g_pts
                            result_status = "PASS" if g_status == "PASSED" else ("FAIL" if g_status == "FAILED" else g_status)
                            if g_status == "ABSENT":
                                attendance_status = "ABSENT"

                grade_status = "PASSED" if result_status == "PASS" else ("FAILED" if result_status == "FAIL" else result_status)

                record = {
                    "student_id": student_id,
                    "student_name": student_name,
                    "department": department,
                    "semester": semester,
                    "academic_year": academic_year,
                    "section": section,
                    "batch": batch,
                    "subject_code": s_code,
                    "subject_name": s_name,
                    "subject_type": subject_type,
                    "assessment_type": col_assessment_type,
                    "assessment_name": col_assessment_name,
                    "max_marks": max_marks,
                    "pass_marks": pass_marks,
                    "weightage": asmt_cfg.weightage,
                    "internal_marks": marks_obtained if "mid" in col_assessment_type or "internal" in col_assessment_type or "laboratory" in col_assessment_type else None,
                    "external_marks": marks_obtained if "semester" in col_assessment_type else None,
                    "total_marks": marks_obtained,
                    "marks_obtained": marks_obtained,
                    "letter_grade": letter_grade,
                    "grade_points": grade_points,
                    "credits": None,
                    "sgpa": sgpa,
                    "result_status": result_status,
                    "grade_status": grade_status,
                    "status": result_status,
                    "attendance_status": attendance_status,
                    "remarks": "",
                    "validation_status": "VALID",
                    "validation_notes": "OK"
                }
                records.append(record)

        return records
