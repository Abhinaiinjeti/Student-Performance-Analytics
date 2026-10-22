"""
EduPulse Analytics - Synthetic Big Data Generator
Streams scalable academic datasets (10k, 100k, 500k, 1M+ records) with strictly fictional IDs,
reproducible random seeds, realistic statistical distributions, and configurable edge cases.
"""
import os
import csv
import time
import random
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Generator
from config.settings import StorageConfig, get_config

logger = logging.getLogger(__name__)


class SyntheticDataGenerator:
    """
    High-throughput stream-based generator for marks-based and grade-based datasets.
    Writes directly to disk in partitioned chunks to avoid memory exhaustion.
    """
    DEPARTMENTS = ["CSE", "ECE", "MECH", "CIVIL", "IT", "EEE", "CHEM", "AI_DS"]
    SEMESTERS = [1, 2, 3, 4, 5, 6, 7, 8]
    
    SUBJECTS_POOL = {
        "CSE": [("CS101", "Programming Fundamentals"), ("CS201", "Data Structures"), ("CS301", "Algorithms"), ("CS401", "Operating Systems"), ("CS501", "Database Systems")],
        "ECE": [("EC101", "Circuit Analysis"), ("EC201", "Digital Electronics"), ("EC301", "Signals and Systems"), ("EC401", "Microprocessors"), ("EC501", "VLSI Design")],
        "MECH": [("ME101", "Engineering Mechanics"), ("ME201", "Thermodynamics"), ("ME301", "Fluid Mechanics"), ("ME401", "Kinematics"), ("ME501", "Heat Transfer")],
        "CIVIL": [("CE101", "Building Materials"), ("CE201", "Structural Analysis"), ("CE301", "Geotechnical Eng"), ("CE401", "Hydraulics"), ("CE501", "Transportation Eng")],
        "IT": [("IT101", "Web Technologies"), ("IT201", "Object Oriented Design"), ("IT301", "Computer Networks"), ("IT401", "Information Security"), ("IT501", "Cloud Computing")],
        "EEE": [("EE101", "Basic Electrical"), ("EE201", "Power Systems"), ("EE301", "Control Systems"), ("EE401", "Electrical Machines"), ("EE501", "Power Electronics")],
        "CHEM": [("CH101", "Chemical Process"), ("CH201", "Organic Chemistry"), ("CH301", "Mass Transfer"), ("CH401", "Reaction Eng"), ("CH501", "Process Dynamics")],
        "AI_DS": [("AI101", "Intro to AI"), ("AI201", "Machine Learning"), ("AI301", "Deep Learning"), ("AI401", "Natural Language Proc"), ("AI501", "Big Data Analytics")]
    }

    GRADE_SCALE = ["O", "A+", "A", "B+", "B", "C", "P", "F"]
    GRADE_WEIGHTS = [0.15, 0.25, 0.30, 0.15, 0.08, 0.04, 0.02, 0.01]  # Realistic bell-curve distribution

    def __init__(self, output_dir: Optional[Path] = None, seed: Optional[int] = 42):
        self.output_dir = output_dir or get_config().storage.synthetic_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.seed = seed
        if self.seed is not None:
            random.seed(self.seed)

    def generate_marks_dataset(
        self,
        total_records: int = 100_000,
        student_count: Optional[int] = None,
        duplicate_rate: float = 0.01,
        missing_rate: float = 0.02,
        absent_rate: float = 0.015,
        invalid_rate: float = 0.005,
        academic_year: str = "2025-2026",
        chunk_size: int = 25_000
    ) -> Dict[str, Any]:
        """
        Streams a large marks-based synthetic dataset directly to CSV.
        """
        start_time = time.time()
        filename = f"SYNTH_MARKS_{total_records}_{int(start_time)}.csv"
        file_path = self.output_dir / filename

        # Infer student count if not provided (avg 6 subjects per student)
        if not student_count:
            student_count = max(1, total_records // 6)

        headers = [
            "student_id", "department", "batch", "section", "semester",
            "academic_year", "assessment_period", "subject_code", "subject_name",
            "internal_marks", "max_internal", "external_marks", "max_external",
            "attendance_pct", "is_synthetic"
        ]

        records_written = 0
        duplicates_injected = 0
        missing_injected = 0
        absent_injected = 0
        invalid_injected = 0

        # Pre-generate student cohort identifiers (strictly fictional)
        student_ids = [f"STU-2026-{idx:06d}" for idx in range(1, student_count + 1)]

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

            while records_written < total_records:
                chunk_rows = []
                current_chunk_limit = min(chunk_size, total_records - records_written)

                for _ in range(current_chunk_limit):
                    stu_id = random.choice(student_ids)
                    dept = random.choice(self.DEPARTMENTS)
                    sem = random.choice(self.SEMESTERS)
                    sec = random.choice(["A", "B", "C"])
                    batch = f"{int(academic_year[:4])-1}-{int(academic_year[:4])+3}"
                    sub_code, sub_name = random.choice(self.SUBJECTS_POOL[dept])

                    max_int = 40.0
                    max_ext = 60.0

                    # Realistic marks distribution (mean ~ 70% with standard deviation)
                    rand_val = random.random()

                    if rand_val < invalid_rate:
                        # Invalidate: marks out of range
                        internal = round(random.choice([-5.0, 48.0, 99.0]), 1)
                        external = round(random.choice([-10.0, 75.0, 110.0]), 1)
                        invalid_injected += 1
                    elif rand_val < (invalid_rate + absent_rate):
                        # Absent record
                        internal = round(max(0.0, min(max_int, random.gauss(28, 5))), 1)
                        external = "Ab"
                        absent_injected += 1
                    elif rand_val < (invalid_rate + absent_rate + missing_rate):
                        # Missing record
                        internal = ""
                        external = round(max(0.0, min(max_ext, random.gauss(42, 8))), 1)
                        missing_injected += 1
                    else:
                        # Normal realistic scores
                        internal = round(max(0.0, min(max_int, random.gauss(28.0, 6.0))), 1)
                        external = round(max(0.0, min(max_ext, random.gauss(42.0, 9.0))), 1)

                    attendance = round(max(50.0, min(100.0, random.gauss(82.0, 10.0))), 1)

                    row = [
                        stu_id, dept, batch, sec, sem,
                        academic_year, "Final-Exam", sub_code, sub_name,
                        internal, max_int, external, max_ext,
                        attendance, True
                    ]
                    chunk_rows.append(row)

                    # Invalidate: duplicate entry
                    if random.random() < duplicate_rate and records_written + len(chunk_rows) < total_records:
                        chunk_rows.append(list(row))
                        duplicates_injected += 1

                writer.writerows(chunk_rows)
                records_written += len(chunk_rows)

        elapsed = round(time.time() - start_time, 2)
        file_size_mb = round(file_path.stat().st_size / (1024 * 1024), 2)
        logger.info(f"Generated {records_written} synthetic marks records in {elapsed}s ({file_size_mb} MB)")

        return {
            "file_path": str(file_path),
            "filename": filename,
            "total_records": records_written,
            "file_size_mb": file_size_mb,
            "elapsed_seconds": elapsed,
            "records_per_second": round(records_written / elapsed, 1) if elapsed > 0 else 0,
            "anomalies": {
                "duplicates": duplicates_injected,
                "missing": missing_injected,
                "absent": absent_injected,
                "invalid": invalid_injected
            },
            "model_type": "marks_based"
        }

    def generate_grade_dataset(
        self,
        total_records: int = 100_000,
        student_count: Optional[int] = None,
        academic_year: str = "2025-2026",
        chunk_size: int = 25_000
    ) -> Dict[str, Any]:
        """
        Streams a large grade-based synthetic university result dataset directly to CSV.
        """
        start_time = time.time()
        filename = f"SYNTH_GRADES_{total_records}_{int(start_time)}.csv"
        file_path = self.output_dir / filename

        if not student_count:
            student_count = max(1, total_records // 6)

        headers = [
            "student_id", "department", "semester", "academic_year",
            "exam_type", "subject_code", "subject_name", "course_credits",
            "letter_grade", "sgpa", "is_synthetic"
        ]

        records_written = 0
        student_ids = [f"STU-2026-{idx:06d}" for idx in range(1, student_count + 1)]

        # Precompute student SGPAs
        student_sgpa_map = {
            sid: round(max(4.0, min(10.0, random.gauss(7.8, 1.2))), 2)
            for sid in student_ids
        }

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

            while records_written < total_records:
                chunk_rows = []
                current_chunk_limit = min(chunk_size, total_records - records_written)

                for _ in range(current_chunk_limit):
                    stu_id = random.choice(student_ids)
                    dept = random.choice(self.DEPARTMENTS)
                    sem = random.choice(self.SEMESTERS)
                    sub_code, sub_name = random.choice(self.SUBJECTS_POOL[dept])
                    credits = random.choice([3.0, 4.0, 2.0])
                    sgpa = student_sgpa_map[stu_id]

                    # Pick grade based on realistic weights
                    r = random.random()
                    if r < 0.02:
                        grade = "Ab"  # Absent
                    elif r < 0.03:
                        grade = "W"   # Withheld
                    elif r < 0.04:
                        grade = ""    # Missing
                    else:
                        grade = random.choices(self.GRADE_SCALE, weights=self.GRADE_WEIGHTS, k=1)[0]

                    row = [
                        stu_id, dept, sem, academic_year,
                        "REGULAR", sub_code, sub_name, credits,
                        grade, sgpa, True
                    ]
                    chunk_rows.append(row)

                writer.writerows(chunk_rows)
                records_written += len(chunk_rows)

        elapsed = round(time.time() - start_time, 2)
        file_size_mb = round(file_path.stat().st_size / (1024 * 1024), 2)
        logger.info(f"Generated {records_written} synthetic grade records in {elapsed}s ({file_size_mb} MB)")

        return {
            "file_path": str(file_path),
            "filename": filename,
            "total_records": records_written,
            "file_size_mb": file_size_mb,
            "elapsed_seconds": elapsed,
            "records_per_second": round(records_written / elapsed, 1) if elapsed > 0 else 0,
            "model_type": "grade_based"
        }
