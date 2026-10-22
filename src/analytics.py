"""
EduPulse Analytics - Academic Analytics Engine
Calculates marks-based analytics, grade-based distributions, and transparent
rule-based Student Support Indicators with explicit explainability.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """
    Core calculation engine for institutional academic performance,
    subject drill-downs, and transparent student support indicators.
    """
    def compute_marks_analytics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Computes comprehensive metrics for marks-based datasets.
        """
        if df.empty:
            return {
                "model_type": "marks_based",
                "total_records": 0,
                "summary": {
                    "total_records": 0,
                    "unique_students": 0,
                    "unique_subjects": 0,
                    "passed_count": 0,
                    "failed_count": 0,
                    "absent_count": 0,
                    "incomplete_count": 0,
                    "pass_percentage": 0.0,
                    "average_score": 0.0,
                    "median_score": 0.0,
                    "std_dev": 0.0,
                    "min_score": 0.0,
                    "max_score": 0.0,
                    "average_percentage": 0.0
                },
                "subjects": [],
                "support_indicators": []
            }

        # Safe column defaults
        if "status" not in df or df["status"].isnull().all():
            if "result_status" in df and df["result_status"].notna().any():
                df["status"] = df["result_status"].astype(str).str.strip().str.upper()
            elif "grade_status" in df and df["grade_status"].notna().any():
                status_map = {"PASSED": "PASS", "FAILED": "FAIL", "ABSENT": "ABSENT", "WITHHELD": "WITHHELD", "MISSING": "INCOMPLETE"}
                df["status"] = df["grade_status"].map(lambda x: status_map.get(str(x).upper(), "UNKNOWN"))
            elif "total_marks" in df or "marks" in df:
                score_col = "total_marks" if "total_marks" in df else "marks"
                df["status"] = pd.to_numeric(df[score_col], errors="coerce").apply(
                    lambda s: "PASS" if pd.notna(s) and s >= 40.0 else ("FAIL" if pd.notna(s) else "UNKNOWN")
                )
            else:
                df["status"] = "UNKNOWN"
        else:
            df["status"] = df["status"].astype(str).str.strip().str.upper()

        if "subject_code" not in df:
            df["subject_code"] = "GEN101"
        if "total_marks" not in df and "marks" in df:
            df["total_marks"] = df["marks"]
        if "percentage" not in df and "total_marks" in df:
            df["percentage"] = df["total_marks"]

        # Filter to valid evaluated records for score analytics
        evaluated_df = df[df["status"].isin(["PASS", "FAIL"])].copy()
        
        # Overall Summary KPIs
        total_records = len(df)
        unique_students = int(df["student_id"].nunique()) if "student_id" in df else 0
        unique_subjects = int(df["subject_code"].nunique()) if "subject_code" in df else 0
        
        passed_count = int((df["status"] == "PASS").sum())
        failed_count = int((df["status"] == "FAIL").sum())
        absent_count = int((df["status"] == "ABSENT").sum())
        incomplete_count = int((df["status"] == "INCOMPLETE").sum())

        evaluated_total = passed_count + failed_count
        pass_rate = round((passed_count / evaluated_total) * 100, 2) if evaluated_total > 0 else 0.0

        scores = pd.to_numeric(evaluated_df["total_marks"], errors="coerce").dropna() if "total_marks" in evaluated_df else pd.Series([], dtype=float)
        percentages = pd.to_numeric(evaluated_df["percentage"], errors="coerce").dropna() if "percentage" in evaluated_df else pd.Series([], dtype=float)

        overall_stats = {
            "total_records": total_records,
            "unique_students": unique_students,
            "unique_subjects": unique_subjects,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "absent_count": absent_count,
            "incomplete_count": incomplete_count,
            "pass_percentage": pass_rate,
            "average_score": round(float(scores.mean()), 2) if not scores.empty else 0.0,
            "median_score": round(float(scores.median()), 2) if not scores.empty else 0.0,
            "std_dev": round(float(scores.std()), 2) if len(scores) > 1 else 0.0,
            "min_score": round(float(scores.min()), 2) if not scores.empty else 0.0,
            "max_score": round(float(scores.max()), 2) if not scores.empty else 0.0,
            "average_percentage": round(float(percentages.mean()), 2) if not percentages.empty else 0.0
        }

        # Subject-wise Breakdown
        subject_breakdown = []
        for sub_code, s_df in df.groupby("subject_code"):
            s_name = s_df["subject_name"].iloc[0] if "subject_name" in s_df and pd.notna(s_df["subject_name"].iloc[0]) else sub_code
            s_eval = s_df[s_df["status"].isin(["PASS", "FAIL"])]
            s_pass = int((s_df["status"] == "PASS").sum())
            s_fail = int((s_df["status"] == "FAIL").sum())
            s_abs = int((s_df["status"] == "ABSENT").sum())
            s_res = s_pass + s_fail
            s_pass_rate = round((s_pass / s_res) * 100, 2) if s_res > 0 else 0.0

            s_scores = pd.to_numeric(s_eval["total_marks"], errors="coerce").dropna()

            # Difficulty Index: 1.0 - (mean percentage / 100)
            s_pcts = pd.to_numeric(s_eval["percentage"], errors="coerce").dropna()
            mean_pct = float(s_pcts.mean()) if not s_pcts.empty else 50.0
            difficulty_idx = round(1.0 - (mean_pct / 100.0), 2)

            subject_breakdown.append({
                "subject_code": str(sub_code),
                "subject_name": str(s_name),
                "total_students": len(s_df),
                "passed": s_pass,
                "failed": s_fail,
                "absent": s_abs,
                "pass_rate": s_pass_rate,
                "average_marks": round(float(s_scores.mean()), 2) if not s_scores.empty else 0.0,
                "median_marks": round(float(s_scores.median()), 2) if not s_scores.empty else 0.0,
                "std_dev": round(float(s_scores.std()), 2) if len(s_scores) > 1 else 0.0,
                "difficulty_index": max(0.0, min(1.0, difficulty_idx))
            })

        # Calculate Transparent Student Support Indicators
        support_indicators = self.detect_student_support_indicators(df)

        return {
            "model_type": "marks_based",
            "summary": overall_stats,
            "subjects": subject_breakdown,
            "support_indicators": support_indicators
        }

    def compute_grade_analytics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Computes metrics for grade-based datasets.
        """
        if df.empty:
            return {
                "model_type": "grade_based",
                "total_records": 0,
                "summary": {
                    "total_records": 0,
                    "unique_students": 0,
                    "unique_subjects": 0,
                    "passed_count": 0,
                    "failed_count": 0,
                    "absent_count": 0,
                    "withheld_count": 0,
                    "missing_count": 0,
                    "pass_percentage": 0.0
                },
                "subjects": [],
                "sgpa_stats": {},
                "support_indicators": []
            }

        from config.assessment_rules import GradeScaleRule
        rule = GradeScaleRule()

        if "grade_status" not in df or df["grade_status"].isnull().all():
            if "letter_grade" in df and df["letter_grade"].notna().any():
                df["grade_status"] = df["letter_grade"].apply(
                    lambda g: rule.classify_grade(g)[0] if pd.notna(g) and str(g).strip() else "MISSING"
                )
            elif "result_status" in df and df["result_status"].notna().any():
                status_map = {"PASS": "PASSED", "FAIL": "FAILED", "ABSENT": "ABSENT", "WITHHELD": "WITHHELD", "INCOMPLETE": "MISSING"}
                df["grade_status"] = df["result_status"].map(lambda x: status_map.get(str(x).upper(), "UNKNOWN"))
            elif "status" in df and df["status"].notna().any():
                status_map = {"PASS": "PASSED", "FAIL": "FAILED", "ABSENT": "ABSENT", "WITHHELD": "WITHHELD", "INCOMPLETE": "MISSING"}
                df["grade_status"] = df["status"].map(lambda x: status_map.get(str(x).upper(), "UNKNOWN"))
            else:
                df["grade_status"] = "UNKNOWN"
        else:
            # If letter_grade is present, ensure rows with 'F' or 'AB' are strictly classified as FAILED or ABSENT
            if "letter_grade" in df:
                clean_grades = df["letter_grade"].astype(str).str.strip().str.upper()
                f_mask = clean_grades.isin(rule.fail_grades)
                df.loc[f_mask, "grade_status"] = "FAILED"
                ab_mask = clean_grades.isin(rule.absent_markers)
                df.loc[ab_mask, "grade_status"] = "ABSENT"
                wh_mask = clean_grades.isin(rule.withheld_markers)
                df.loc[wh_mask, "grade_status"] = "WITHHELD"

        if "subject_code" not in df:
            df["subject_code"] = "GEN101"

        total_records = len(df)
        unique_students = int(df["student_id"].nunique()) if "student_id" in df else 0
        unique_subjects = int(df["subject_code"].nunique()) if "subject_code" in df else 0

        passed_count = int((df["grade_status"] == "PASSED").sum())
        failed_count = int((df["grade_status"] == "FAILED").sum())
        absent_count = int((df["grade_status"] == "ABSENT").sum())
        withheld_count = int((df["grade_status"] == "WITHHELD").sum())
        missing_count = int((df["grade_status"] == "MISSING").sum())

        resolved = passed_count + failed_count
        pass_rate = round((passed_count / resolved) * 100, 2) if resolved > 0 else 0.0

        overall_stats = {
            "total_records": total_records,
            "unique_students": unique_students,
            "unique_subjects": unique_subjects,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "absent_count": absent_count,
            "withheld_count": withheld_count,
            "missing_count": missing_count,
            "pass_percentage": pass_rate
        }

        # Subject-wise Grade Distributions
        subject_breakdown = []
        for sub_code, s_df in df.groupby("subject_code"):
            s_name = s_df["subject_name"].iloc[0] if "subject_name" in s_df and pd.notna(s_df["subject_name"].iloc[0]) else sub_code
            s_pass = int((s_df["grade_status"] == "PASSED").sum())
            s_fail = int((s_df["grade_status"] == "FAILED").sum())
            s_abs = int((s_df["grade_status"] == "ABSENT").sum())
            s_res = s_pass + s_fail
            s_pass_rate = round((s_pass / s_res) * 100, 2) if s_res > 0 else 0.0

            grade_dist = s_df["letter_grade"].fillna("BLANK").value_counts().to_dict()

            subject_breakdown.append({
                "subject_code": str(sub_code),
                "subject_name": str(s_name),
                "total_students": len(s_df),
                "passed": s_pass,
                "failed": s_fail,
                "absent": s_abs,
                "pass_rate": s_pass_rate,
                "grade_distribution": grade_dist
            })

        # SGPA Stats
        sgpa_stats = {}
        if "sgpa" in df and df["sgpa"].dropna().count() > 0:
            student_sgpas = df[["student_id", "sgpa"]].dropna().drop_duplicates()
            sgpas = pd.to_numeric(student_sgpas["sgpa"], errors="coerce").dropna()
            if not sgpas.empty:
                sgpa_stats = {
                    "count": int(len(sgpas)),
                    "mean": round(float(sgpas.mean()), 2),
                    "median": round(float(sgpas.median()), 2),
                    "std_dev": round(float(sgpas.std()), 2) if len(sgpas) > 1 else 0.0,
                    "min": round(float(sgpas.min()), 2),
                    "max": round(float(sgpas.max()), 2),
                    "q25": round(float(sgpas.quantile(0.25)), 2),
                    "q75": round(float(sgpas.quantile(0.75)), 2)
                }

        # Rule-based support indicators for grades
        support_indicators = self.detect_grade_support_indicators(df)

        return {
            "model_type": "grade_based",
            "summary": overall_stats,
            "subjects": subject_breakdown,
            "sgpa_stats": sgpa_stats,
            "support_indicators": support_indicators
        }

    def detect_student_support_indicators(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Rule-Based Student Support Indicator Engine.
        Transparent, auditable rules explaining why a record was flagged:
        1. THRESHOLD_ALERT: Scoring < 40% in >= 2 subjects.
        2. CONSECUTIVE_FAIL_ALERT: Failing >= 2 subjects in this sitting.
        3. CHRONIC_ABSENTEE_ALERT: Marked ABSENT in >= 1 subject exam.
        """
        flags = []
        if df.empty or "student_id" not in df:
            return flags

        for stu_id, stu_df in df.groupby("student_id"):
            dept = stu_df["department"].iloc[0] if "department" in stu_df else "General"
            sem = stu_df["semester"].iloc[0] if "semester" in stu_df else 1

            # Rule 1 & 2: Failures & Thresholds
            failed_subs = stu_df[stu_df["status"] == "FAIL"]["subject_code"].tolist()
            if len(failed_subs) >= 2:
                flags.append({
                    "student_id": stu_id,
                    "department": dept,
                    "semester": int(sem),
                    "flag_type": "MULTIPLE_FAILURES",
                    "severity": "HIGH",
                    "reason": f"Failed {len(failed_subs)} subjects ({', '.join(failed_subs)}) in current assessment.",
                    "action_recommended": "Academic counseling & remedial class enrollment."
                })
            elif len(failed_subs) == 1:
                flags.append({
                    "student_id": stu_id,
                    "department": dept,
                    "semester": int(sem),
                    "flag_type": "SINGLE_FAILURE",
                    "severity": "MEDIUM",
                    "reason": f"Failed subject {failed_subs[0]}; requires re-assessment preparation.",
                    "action_recommended": "Peer tutoring and tutorial support."
                })

            # Rule 3: Absentee Alert
            absent_subs = stu_df[stu_df["status"] == "ABSENT"]["subject_code"].tolist()
            if absent_subs:
                flags.append({
                    "student_id": stu_id,
                    "department": dept,
                    "semester": int(sem),
                    "flag_type": "ABSENT_ALERT",
                    "severity": "MEDIUM",
                    "reason": f"Absent from examination for {', '.join(absent_subs)}.",
                    "action_recommended": "Verify official absence justification or medical leave."
                })

        return flags

    def detect_grade_support_indicators(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Transparent support indicators for grade-based results."""
        flags = []
        if df.empty or "student_id" not in df:
            return flags

        for stu_id, stu_df in df.groupby("student_id"):
            dept = stu_df["department"].iloc[0] if "department" in stu_df else "General"
            sem = stu_df["semester"].iloc[0] if "semester" in stu_df else 1

            failed_subs = stu_df[stu_df["grade_status"] == "FAILED"]["subject_code"].tolist()
            if failed_subs:
                flags.append({
                    "student_id": stu_id,
                    "department": dept,
                    "semester": int(sem),
                    "flag_type": "BACKLOG_ALERT",
                    "severity": "HIGH" if len(failed_subs) >= 2 else "MEDIUM",
                    "reason": f"Received 'F' grade in {len(failed_subs)} subject(s): {', '.join(failed_subs)}.",
                    "action_recommended": "Supplementary examination registration."
                })

            # SGPA alert: below 6.0
            if "sgpa" in stu_df and pd.notna(stu_df["sgpa"].iloc[0]):
                sgpa_val = float(stu_df["sgpa"].iloc[0])
                if sgpa_val < 6.0:
                    flags.append({
                        "student_id": stu_id,
                        "department": dept,
                        "semester": int(sem),
                        "flag_type": "LOW_SGPA_ALERT",
                        "severity": "HIGH" if sgpa_val < 5.0 else "MEDIUM",
                        "reason": f"Current SGPA ({sgpa_val}) is below the standard 6.0 benchmark.",
                        "action_recommended": "Credit recovery plan and mentor review."
                    })

        return flags
