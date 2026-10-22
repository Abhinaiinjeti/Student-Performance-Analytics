"""
EduPulse Analytics - Analytics Service & Cache Coordinator
Coordinates sub-second retrieval of pre-aggregated snapshots, filtered drill-downs,
and longitudinal student records.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd

from storage.local_storage import LocalStorage
from src.analytics import AnalyticsEngine
from config.settings import get_config

logger = logging.getLogger(__name__)


class AnalyticsService:
    """
    Coordinates analytical queries and pre-computed caches for the dashboard.
    """
    def __init__(self, storage: Optional[LocalStorage] = None, engine: Optional[AnalyticsEngine] = None):
        self.storage = storage or LocalStorage()
        self.engine = engine or AnalyticsEngine()
        self.config = get_config()

    def get_latest_dataset_id(self) -> Optional[str]:
        """Returns the dataset_id of the most recently registered manifest."""
        manifests = self.storage.list_manifests()
        if manifests:
            return manifests[0].get("dataset_id")
        return None

    def get_dataset_analytics(self, dataset_id: Optional[str] = None, project_id: Optional[str] = None, assessment_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves analytical snapshot for a dataset.
        Supports:
        - Specific dataset_id: checks data/analytics/AGG_{id}.json or VAL_{id}.csv.
        - 'ALL': dynamically aggregates across all registered lakehouse datasets (scoped to project_id if specified).
        - assessment_type: filters by THEORY, LABORATORY, SEMESTER_EXAM, INTERNAL.
        """
        if assessment_type and assessment_type != "ALL":
            return self.get_filtered_analytics(dataset_id=dataset_id, project_id=project_id, assessment_type=assessment_type)

        target_id = dataset_id or self.get_latest_dataset_id()
        if not target_id:
            return None

        # 1. Multi-dataset institutional overview
        if target_id == "ALL":
            manifests = self.storage.list_manifests()
            if project_id and project_id != "ALL":
                try:
                    from services.project_service import ProjectService
                    ps = ProjectService(config=self.config, storage=self.storage)
                    p_dataset_ids = set(ps.get_project_dataset_ids(project_id))
                    manifests = [m for m in manifests if m.get("dataset_id") in p_dataset_ids]
                except Exception as e:
                    logger.warning(f"Error scoping datasets to project {project_id}: {e}")

            if not manifests:
                return None
            dfs = []
            has_marks = False
            has_grade = False
            for m in manifests:
                v_path = self.config.storage.validated_dir / f"VAL_{m['dataset_id']}.csv"
                if v_path.exists():
                    try:
                        d = pd.read_csv(v_path)
                        dfs.append(d)
                        if m.get("model_type") == "marks_based":
                            has_marks = True
                        else:
                            has_grade = True
                    except Exception as e:
                        logger.warning(f"Error reading {v_path}: {e}")
            if not dfs:
                return None
            df_combined = pd.concat(dfs, ignore_index=True)
            model_type = "grade_based" if has_grade else "marks_based"
            if model_type == "marks_based":
                result = self.engine.compute_marks_analytics(df_combined)
            else:
                result = self.engine.compute_grade_analytics(df_combined)
            result["dataset_id"] = "ALL"
            result["manifest"] = {
                "dataset_id": "ALL",
                "source_file": {"original_filename": f"All Ingested Semesters ({len(manifests)} Datasets Combined)"},
                "model_type": model_type,
                "row_counts": {"accepted_rows": len(df_combined)}
            }
            return result

        # 2. Specific dataset: try pre-computed analytics snapshot
        agg_file = self.config.storage.analytics_dir / f"AGG_{target_id}.json"
        cached_data = self.storage.read_json(agg_file)
        if cached_data and ("subjects" in cached_data or "subject_summary" in cached_data):
            # Augment with manifest metadata
            manifest = self.storage.get_manifest(target_id)
            cached_data["manifest"] = manifest
            return cached_data

        # 3. Compute dynamically from validated CSV
        val_file = self.config.storage.validated_dir / f"VAL_{target_id}.csv"
        if not val_file.exists():
            return None

        df = pd.read_csv(val_file)
        manifest = self.storage.get_manifest(target_id)
        model_type = manifest.get("model_type", "marks_based") if manifest else "marks_based"

        if model_type == "marks_based":
            result = self.engine.compute_marks_analytics(df)
        else:
            result = self.engine.compute_grade_analytics(df)

        result["dataset_id"] = target_id
        result["manifest"] = manifest

        # Cache for future instant queries
        self.storage.atomic_write_json(agg_file, result)
        return result

    def get_available_filter_options(self, dataset_id: Optional[str] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Extracts available departments, semesters, and assessment types for filter dropdowns.
        """
        manifests = self.storage.list_manifests()
        if project_id and project_id != "ALL":
            try:
                from services.project_service import ProjectService
                ps = ProjectService(config=self.config, storage=self.storage)
                p_dataset_ids = set(ps.get_project_dataset_ids(project_id))
                manifests = [m for m in manifests if m.get("dataset_id") in p_dataset_ids]
            except Exception:
                pass

        departments = set()
        semesters = set()

        if dataset_id and dataset_id != "ALL":
            val_file = self.config.storage.validated_dir / f"VAL_{dataset_id}.csv"
            if val_file.exists():
                try:
                    df = pd.read_csv(val_file)
                    if "department" in df:
                        departments.update([str(d).strip() for d in df["department"].dropna().unique() if str(d).strip()])
                    if "semester" in df:
                        semesters.update([int(s) for s in df["semester"].dropna().unique() if pd.notna(s)])
                except Exception:
                    pass

        # Also get all available semesters and departments across all datasets
        all_semesters = set()
        all_departments = set()
        for m in manifests:
            val_file = self.config.storage.validated_dir / f"VAL_{m['dataset_id']}.csv"
            if val_file.exists():
                try:
                    df = pd.read_csv(val_file)
                    if "semester" in df:
                        all_semesters.update([int(s) for s in df["semester"].dropna().unique() if pd.notna(s)])
                    if "department" in df:
                        all_departments.update([str(d).strip() for d in df["department"].dropna().unique() if str(d).strip()])
                except Exception:
                    pass

        assessment_types = [
            {"key": "ALL", "label": "All Evaluations"},
            {"key": "THEORY", "label": "Theory Courses"},
            {"key": "LABORATORY", "label": "Laboratory / Practicals"},
            {"key": "SEMESTER_EXAM", "label": "Semester Final Results"},
            {"key": "INTERNAL", "label": "Internal & Mid Exams"}
        ]

        return {
            "departments": sorted(list(departments or all_departments)),
            "semesters": sorted(list(semesters)) if semesters else sorted(list(all_semesters)),
            "all_semesters": sorted(list(all_semesters)) or list(range(1, 9)),
            "all_departments": sorted(list(all_departments)),
            "assessment_types": assessment_types
        }

    def get_filtered_analytics(
        self,
        dataset_id: Optional[str] = None,
        department: Optional[str] = None,
        semester: Optional[int] = None,
        project_id: Optional[str] = None,
        assessment_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Applies department, semester, project batch, and assessment type filters on the dataset.
        """
        target_id = dataset_id or "ALL"
        manifests = self.storage.list_manifests()
        if not manifests:
            return None

        # Filter manifests by batch project if applicable
        if project_id and project_id != "ALL":
            try:
                from services.project_service import ProjectService
                ps = ProjectService(config=self.config, storage=self.storage)
                p_dataset_ids = set(ps.get_project_dataset_ids(project_id))
                manifests = [m for m in manifests if m.get("dataset_id") in p_dataset_ids]
            except Exception as e:
                logger.warning(f"Error scoping datasets to project {project_id}: {e}")

        if not manifests:
            return None

        is_all_mode = (target_id == "ALL")
        manifest = None
        df = None
        model_type = "grade_based"

        if not is_all_mode:
            val_file = self.config.storage.validated_dir / f"VAL_{target_id}.csv"
            if val_file.exists():
                try:
                    df = pd.read_csv(val_file)
                    manifest = self.storage.get_manifest(target_id)
                    model_type = manifest.get("model_type", "grade_based") if manifest else "grade_based"

                    # SMART AUTO-SWITCH:
                    if semester and semester != 0 and "semester" in df:
                        sem_vals = df["semester"].dropna().unique().tolist()
                        if semester not in sem_vals:
                            for other_m in manifests:
                                other_id = other_m["dataset_id"]
                                other_val = self.config.storage.validated_dir / f"VAL_{other_id}.csv"
                                if other_val.exists():
                                    try:
                                        other_df = pd.read_csv(other_val)
                                        if "semester" in other_df and (other_df["semester"] == semester).any():
                                            df = other_df
                                            target_id = other_id
                                            manifest = other_m
                                            model_type = other_m.get("model_type", "grade_based")
                                            logger.info(f"Smart auto-switched to dataset {other_id} for semester {semester}")
                                            break
                                    except Exception:
                                        continue
                except Exception as e:
                    logger.error(f"Error reading dataset {target_id}: {e}")
                    df = None

        # Fallback to ALL mode if df is None
        if df is None:
            dfs = []
            has_marks = False
            has_grade = False
            for m in manifests:
                v_path = self.config.storage.validated_dir / f"VAL_{m['dataset_id']}.csv"
                if v_path.exists():
                    try:
                        d = pd.read_csv(v_path)
                        dfs.append(d)
                        if m.get("model_type") == "marks_based":
                            has_marks = True
                        else:
                            has_grade = True
                    except Exception:
                        pass
            if not dfs:
                return None
            df = pd.concat(dfs, ignore_index=True)
            target_id = "ALL"
            model_type = "grade_based" if has_grade else "marks_based"
            manifest = {
                "dataset_id": "ALL",
                "source_file": {"original_filename": f"All Ingested Semesters ({len(manifests)} Datasets Combined)"},
                "model_type": model_type,
                "row_counts": {"accepted_rows": len(df)}
            }

        # Apply Department Filter with robust matching
        if department and department != "ALL":
            dept_str = str(department).strip()
            d_series = df["department"].astype(str) if "department" in df else pd.Series([], dtype=str)
            mask = (
                (d_series == dept_str) |
                (d_series.str.lower() == dept_str.lower()) |
                (d_series.str.lower().str.contains(dept_str.lower(), regex=False, na=False))
            )
            dept_upper = dept_str.upper()
            if dept_upper in ["CSE", "CS"]:
                mask = mask | d_series.str.contains("CSE|Computer Science", case=False, na=False)
            elif dept_upper in ["ECE", "EC"]:
                mask = mask | d_series.str.contains("ECE|Electronics", case=False, na=False)
            elif dept_upper in ["MECH", "ME"]:
                mask = mask | d_series.str.contains("MECH|Mechanical", case=False, na=False)
            elif dept_upper in ["CIVIL", "CE"]:
                mask = mask | d_series.str.contains("CIVIL|Civil", case=False, na=False)

            df = df[mask]

        # Apply Semester Filter
        if semester and semester != 0:
            if "semester" in df:
                df = df[df["semester"] == semester]

        # Apply Assessment Type / Subject Type Filter
        if assessment_type and assessment_type != "ALL":
            asmt_upper = str(assessment_type).upper()
            if asmt_upper == "THEORY":
                if "subject_type" in df:
                    df = df[df["subject_type"] == "THEORY"]
                elif "subject_code" in df:
                    df = df[~df["subject_code"].astype(str).str.contains("LAB|PRACTICAL|PR", case=False, na=False)]
            elif asmt_upper in ("LABORATORY", "LAB"):
                if "subject_type" in df:
                    df = df[df["subject_type"] == "LABORATORY"]
                elif "assessment_type" in df:
                    df = df[(df["assessment_type"] == "laboratory") | (df["subject_code"].astype(str).str.contains("LAB|PRACTICAL|PR", case=False, na=False))]
                elif "subject_code" in df:
                    df = df[df["subject_code"].astype(str).str.contains("LAB|PRACTICAL|PR", case=False, na=False)]
            elif asmt_upper in ("SEMESTER_EXAM", "SEMESTER"):
                if "assessment_type" in df:
                    df = df[df["assessment_type"] == "semester_exam"]
            elif asmt_upper in ("INTERNAL", "MID"):
                if "assessment_type" in df:
                    df = df[df["assessment_type"].isin(["internal", "mid_1", "mid_2", "quiz", "assignment"])]

        if model_type == "marks_based":
            res = self.engine.compute_marks_analytics(df)
        else:
            res = self.engine.compute_grade_analytics(df)

        res["dataset_id"] = target_id
        res["manifest"] = manifest
        res["filter"] = {
            "department": department or "ALL",
            "semester": semester or 0,
            "assessment_type": assessment_type or "ALL",
            "project_id": project_id or "ALL"
        }
        return res

    def get_sample_students(self, limit: int = 12, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Discovers student IDs across validated datasets with department,
        completed semester count, and sample roll numbers, scoped to project if specified.
        """
        manifests = self.storage.list_manifests()
        if project_id and project_id != "ALL":
            try:
                from services.project_service import ProjectService
                ps = ProjectService(config=self.config, storage=self.storage)
                p_dataset_ids = set(ps.get_project_dataset_ids(project_id))
                manifests = [m for m in manifests if m.get("dataset_id") in p_dataset_ids]
            except Exception:
                pass

        student_map = {}
        for m in manifests:
            v_path = self.config.storage.validated_dir / f"VAL_{m['dataset_id']}.csv"
            if v_path.exists():
                try:
                    df = pd.read_csv(v_path, usecols=["student_id", "department", "semester"])
                    for (sid, dept), group in df.groupby(["student_id", "department"]):
                        if pd.notna(sid):
                            sid_str = str(sid).strip()
                            if sid_str not in student_map:
                                student_map[sid_str] = {
                                    "student_id": sid_str,
                                    "department": str(dept) if pd.notna(dept) else "General",
                                    "semesters": set()
                                }
                            student_map[sid_str]["semesters"].update(group["semester"].dropna().unique().tolist())
                except Exception:
                    pass

        # Sort priority: students with the most semesters first, then alphabetical
        sorted_students = sorted(
            student_map.values(),
            key=lambda x: (-len(x["semesters"]), x["student_id"])
        )

        samples = []
        for info in sorted_students[:limit]:
            samples.append({
                "student_id": info["student_id"],
                "department": info["department"],
                "semesters_count": len(info["semesters"])
            })
        return samples

    def get_student_longitudinal_record(self, student_id: str, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Looks up longitudinal performance trajectory for an individual student.
        Calculates cumulative CGPA, semester breakdowns, backlog tracking, and sanitized course history.
        """
        student_id_clean = student_id.strip()
        manifests = self.storage.list_manifests()
        if project_id and project_id != "ALL":
            try:
                from services.project_service import ProjectService
                ps = ProjectService(config=self.config, storage=self.storage)
                p_dataset_ids = set(ps.get_project_dataset_ids(project_id))
                manifests = [m for m in manifests if m.get("dataset_id") in p_dataset_ids]
            except Exception:
                pass

        all_student_records = []

        for m in manifests:
            val_path = Path(m.get("storage_locations", {}).get("validated_path") or (self.config.storage.validated_dir / f"VAL_{m['dataset_id']}.csv"))
            if val_path.exists():
                try:
                    df = pd.read_csv(val_path)
                    if "student_id" in df:
                        matches = df[df["student_id"] == student_id_clean]
                        if not matches.empty:
                            for _, row in matches.iterrows():
                                all_student_records.append(row.to_dict())
                except Exception as e:
                    logger.warning(f"Error reading {val_path} for student lookup: {e}")

        if not all_student_records:
            return None

        # Clean NaN values so Jinja never renders literal 'nan' or 'nan (%)'
        def clean_val(v):
            if v is None or pd.isna(v):
                return None
            return v

        default_keys = {
            "student_id": student_id_clean,
            "semester": 1,
            "subject_code": "",
            "subject_name": "",
            "letter_grade": None,
            "grade_points": None,
            "credits": None,
            "sgpa": None,
            "internal_marks": None,
            "external_marks": None,
            "total_marks": None,
            "percentage": None,
            "status": None,
            "grade_status": None,
            "assessment_name": None
        }

        cleaned_records = []
        for row in all_student_records:
            entry = dict(default_keys)
            for k, v in row.items():
                entry[k] = clean_val(v)
            cleaned_records.append(entry)

        cleaned_records.sort(key=lambda x: (x.get("semester") or 0, str(x.get("subject_code") or "")))

        df_stu = pd.DataFrame(all_student_records)
        df_stu = df_stu.sort_values(by="semester") if "semester" in df_stu else df_stu

        # Semester-wise GPA / Percentage progression
        progression = []
        semesters_dict = {}
        for sem, s_df in df_stu.groupby("semester"):
            sem_int = int(sem)
            avg_pct = s_df["percentage"].mean() if "percentage" in s_df and s_df["percentage"].notna().any() else None
            sgpa = s_df["sgpa"].iloc[0] if "sgpa" in s_df and s_df["sgpa"].notna().any() else None

            s_courses = [c for c in cleaned_records if c.get("semester") == sem_int]
            s_passed = sum(1 for c in s_courses if (c.get("status") in ['PASS', 'PASSED']) or (c.get("grade_status") in ['PASS', 'PASSED']) or (c.get("letter_grade") and c.get("letter_grade") not in ['F', 'AB']))
            s_failed = sum(1 for c in s_courses if (c.get("status") in ['FAIL', 'FAILED']) or (c.get("grade_status") in ['FAIL', 'FAILED']) or (c.get("letter_grade") in ['F', 'AB']))

            prog_item = {
                "semester": sem_int,
                "average_percentage": round(float(avg_pct), 2) if avg_pct is not None else None,
                "sgpa": round(float(sgpa), 2) if sgpa is not None else None,
                "courses_count": len(s_courses),
                "passed_count": s_passed,
                "failed_count": s_failed
            }
            progression.append(prog_item)
            semesters_dict[sem_int] = {
                "semester": sem_int,
                "sgpa": round(float(sgpa), 2) if sgpa is not None else None,
                "courses": s_courses,
                "courses_count": len(s_courses),
                "passed_count": s_passed,
                "failed_count": s_failed
            }

        progression.sort(key=lambda x: x["semester"])

        # Overall summary stats
        total_courses = len(cleaned_records)
        total_passed = sum(1 for c in cleaned_records if (c.get("status") in ['PASS', 'PASSED']) or (c.get("grade_status") in ['PASS', 'PASSED']) or (c.get("letter_grade") and c.get("letter_grade") not in ['F', 'AB']))
        total_failed = sum(1 for c in cleaned_records if (c.get("status") in ['FAIL', 'FAILED']) or (c.get("grade_status") in ['FAIL', 'FAILED']) or (c.get("letter_grade") in ['F', 'AB']))
        total_absent = sum(1 for c in cleaned_records if c.get("status") == 'ABSENT' or c.get("letter_grade") == 'AB')
        pass_pct = round((total_passed / total_courses) * 100, 2) if total_courses > 0 else 0.0

        sgpas = [p["sgpa"] for p in progression if p.get("sgpa") is not None]
        cgpa = round(sum(sgpas) / len(sgpas), 2) if sgpas else None

        # Trajectory trend
        if len(sgpas) >= 2:
            diff = round(sgpas[-1] - sgpas[0], 2)
            lowest = min(sgpas)
            recovery = round(sgpas[-1] - lowest, 2)
            if diff > 0.3:
                trend = f"Strong Upward Momentum (+{diff} GPA gain)"
            elif recovery > 0.5 and sgpas[-1] > sgpas[-2]:
                trend = f"Upward Recovery (+{recovery} GPA from Sem {sgpas.index(lowest)+1})"
            elif diff < -0.3:
                trend = f"Downward Drift ({diff} GPA from Sem 1)"
            else:
                trend = "Consistent Performance"
        else:
            trend = "Single Semester Recorded"

        # Academic Standing
        if total_failed > 0:
            standing = f"{total_failed} Active Backlog(s)"
            standing_color = "danger" if total_failed > 2 else "warning"
        elif cgpa and cgpa >= 7.5:
            standing = "First Class with Distinction"
            standing_color = "success"
        elif cgpa and cgpa >= 6.5:
            standing = "First Class Standing"
            standing_color = "primary"
        elif cgpa and cgpa >= 5.0:
            standing = "Second Class Standing"
            standing_color = "info"
        else:
            standing = "Pass Division"
            standing_color = "secondary"

        # List of backlogs
        backlogs = [c for c in cleaned_records if (c.get("status") in ['FAIL', 'FAILED']) or (c.get("grade_status") in ['FAIL', 'FAILED']) or (c.get("letter_grade") in ['F', 'AB'])]

        # Inferred batch
        dept = df_stu["department"].iloc[0] if "department" in df_stu and pd.notna(df_stu["department"].iloc[0]) else "Computer Science(CSE)"
        batch = df_stu["batch"].iloc[0] if "batch" in df_stu and pd.notna(df_stu["batch"].iloc[0]) else ""
        if not batch or str(batch).strip() == "" or str(batch).lower() == "nan":
            if len(student_id_clean) >= 2 and student_id_clean[:2].isdigit():
                yr = int(student_id_clean[:2])
                batch = f"20{yr} - 20{yr+4} (B.Tech)"
            else:
                batch = "Undergraduate"

        # Student Name if available
        student_name = None
        if "student_name" in df_stu:
            names = [str(n).strip() for n in df_stu["student_name"].dropna().unique() if str(n).strip() and str(n).lower() != "nan"]
            if names:
                student_name = names[0]

        return {
            "student_id": student_id_clean,
            "student_name": student_name,
            "department": str(dept),
            "batch": str(batch),
            "total_courses_taken": total_courses,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "total_absent": total_absent,
            "pass_percentage": pass_pct,
            "cgpa": cgpa,
            "min_sgpa": min(sgpas) if sgpas else None,
            "max_sgpa": max(sgpas) if sgpas else None,
            "trajectory_trend": trend,
            "academic_standing": standing,
            "standing_color": standing_color,
            "backlogs_count": len(backlogs),
            "backlogs_list": backlogs,
            "progression": progression,
            "semesters_dict": semesters_dict,
            "semesters_list": sorted(list(semesters_dict.keys())),
            "course_history": cleaned_records
        }

    def clear_student_backlog(
        self,
        student_id: str,
        subject_code: str,
        new_letter_grade: str,
        new_grade_points: float,
        semester: Optional[int] = None,
        updated_sgpa: Optional[float] = None,
        remarks: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Updates a student's backlog record to cleared/passed status across the validated dataset.
        Atomically saves changes and refreshes analytical caches.
        """
        student_id_clean = str(student_id).strip()
        subject_code_clean = str(subject_code).strip()

        manifests = self.storage.list_manifests()
        updated = False
        target_dataset_id = None
        old_grade = None
        old_gp = None

        for m in manifests:
            did = m["dataset_id"]
            val_file = self.config.storage.validated_dir / f"VAL_{did}.csv"
            if val_file.exists():
                try:
                    df = pd.read_csv(val_file)
                    if "student_id" not in df.columns or "subject_code" not in df.columns:
                        continue
                    cond = (df["student_id"].astype(str).str.strip() == student_id_clean) & \
                           (df["subject_code"].astype(str).str.strip() == subject_code_clean)
                    if semester and "semester" in df:
                        cond = cond & (df["semester"] == semester)

                    if cond.any():
                        target_dataset_id = did
                        idx = df[cond].index

                        old_grade = df.loc[idx, "letter_grade"].iloc[0] if "letter_grade" in df else "F"
                        old_gp = df.loc[idx, "grade_points"].iloc[0] if "grade_points" in df else 0.0

                        df.loc[idx, "letter_grade"] = str(new_letter_grade).strip().upper()
                        df.loc[idx, "grade_points"] = float(new_grade_points)
                        df.loc[idx, "status"] = "PASS"
                        df.loc[idx, "grade_status"] = "PASSED"
                        df.loc[idx, "result_status"] = "PASS"
                        df.loc[idx, "attendance_status"] = "PRESENT"

                        clear_remark = remarks or f"Cleared Backlog in Supplementary ({new_letter_grade})"
                        df.loc[idx, "remarks"] = clear_remark

                        if updated_sgpa is not None and "sgpa" in df:
                            df.loc[df["student_id"].astype(str).str.strip() == student_id_clean, "sgpa"] = float(updated_sgpa)

                        # Save updated validated CSV
                        df.to_csv(val_file, index=False)
                        updated = True

                        # Invalidate caches
                        agg_file = self.config.storage.analytics_dir / f"AGG_{did}.json"
                        if agg_file.exists():
                            try:
                                agg_file.unlink()
                            except Exception:
                                pass
                        agg_all = self.config.storage.analytics_dir / "AGG_ALL.json"
                        if agg_all.exists():
                            try:
                                agg_all.unlink()
                            except Exception:
                                pass

                        logger.info(f"Cleared backlog for student {student_id_clean}, subject {subject_code_clean} in dataset {did}")
                except Exception as e:
                    logger.warning(f"Error checking backlog in {val_file}: {e}")
                    continue

        if not updated:
            raise ValueError(f"No matching backlog record found for student {student_id_clean} and course {subject_code_clean}")

        # Record in backlog_clearances.json audit log
        audit_file = self.config.storage.data_dir / "backlog_clearances.json"
        audit_records = self.storage.read_json(audit_file) or []
        audit_entry = {
            "student_id": student_id_clean,
            "subject_code": subject_code_clean,
            "semester": semester,
            "dataset_id": target_dataset_id,
            "previous_grade": str(old_grade),
            "previous_grade_points": float(old_gp) if pd.notna(old_gp) else 0.0,
            "cleared_grade": str(new_letter_grade).strip().upper(),
            "cleared_grade_points": float(new_grade_points),
            "updated_sgpa": float(updated_sgpa) if updated_sgpa else None,
            "remarks": remarks or "Cleared in Supplementary Exam",
            "cleared_timestamp": pd.Timestamp.now().isoformat()
        }
        audit_records.append(audit_entry)
        self.storage.atomic_write_json(audit_file, audit_records)

        return {
            "success": True,
            "student_id": student_id_clean,
            "subject_code": subject_code_clean,
            "cleared_grade": new_letter_grade,
            "cleared_grade_points": new_grade_points,
            "dataset_id": target_dataset_id
        }
