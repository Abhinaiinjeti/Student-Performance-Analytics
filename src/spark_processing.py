"""
EduPulse Analytics - PySpark Big Data Processing Pipeline
Implements genuine distributed DataFrame operations for million-record batch processing,
schema normalization, windowed deduplication, Parquet persistence, and analytical aggregations.
"""
import os
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone

import config.settings  # Triggers Java & Hadoop environment configuration
from config.settings import AppConfig, get_config
from pyspark.sql import SparkSession, DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, DoubleType, BooleanType
)

logger = logging.getLogger(__name__)


class PySparkPipeline:
    """
    Genuine PySpark Big Data Pipeline for high-throughput academic processing.
    """
    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or get_config()
        self._spark: Optional[SparkSession] = None

    def get_spark(self) -> SparkSession:
        """Initializes or returns active local PySpark Session."""
        if self._spark is None or self._spark._jsparkSession is None:
            builder = SparkSession.builder \
                .appName(self.config.spark.app_name) \
                .master(self.config.spark.master) \
                .config("spark.driver.memory", self.config.spark.driver_memory) \
                .config("spark.sql.shuffle.partitions", str(self.config.spark.shuffle_partitions)) \
                .config("spark.ui.enabled", "false") \
                .config("spark.sql.execution.arrow.pyspark.enabled", "true")
            self._spark = builder.getOrCreate()
        return self._spark

    def process_marks_dataset(
        self,
        dataset_id: str,
        input_csv_path: str,
        progress_callback: Optional[Callable[[int, str, Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes the 10-stage Big Data processing pipeline for marks-based records.
        """
        input_csv_path = str(input_csv_path)
        start_time = time.time()
        spark = self.get_spark()
        telemetry: Dict[str, Any] = {}

        def update_progress(pct: int, stage_name: str, details: Optional[Dict[str, Any]] = None):
            logger.info(f"[{dataset_id[:8]}] Stage {stage_name} ({pct}%)")
            if progress_callback:
                progress_callback(pct, stage_name, details or {})

        # Stage 1: Discovery & Ingestion
        update_progress(10, "Dataset Discovery & Ingestion")
        df_raw = spark.read.option("header", "true").option("inferSchema", "true").csv(input_csv_path)
        total_raw = df_raw.count()
        telemetry["total_raw_rows"] = total_raw

        # Stage 2: Schema Normalization & Safe Type Casting (Handling 'Ab' and blanks safely)
        update_progress(25, "Schema Normalization")
        df_norm = df_raw.select(
            F.col("student_id").cast(StringType()).alias("student_id"),
            F.coalesce(F.col("department").cast(StringType()), F.lit("General")).alias("department"),
            F.coalesce(F.col("semester").cast(IntegerType()), F.lit(1)).alias("semester"),
            F.col("subject_code").cast(StringType()).alias("subject_code"),
            F.coalesce(F.col("subject_name").cast(StringType()), F.lit("")).alias("subject_name"),
            F.col("internal_marks").cast(StringType()).alias("raw_internal"),
            F.expr("try_cast(internal_marks as double)").alias("internal_marks"),
            F.coalesce(F.expr("try_cast(max_internal as double)"), F.lit(40.0)).alias("max_internal"),
            F.col("external_marks").cast(StringType()).alias("raw_external"),
            F.expr("try_cast(external_marks as double)").alias("external_marks"),
            F.coalesce(F.expr("try_cast(max_external as double)"), F.lit(60.0)).alias("max_external"),
            F.coalesce(F.col("is_synthetic").cast(BooleanType()), F.lit(False)).alias("is_synthetic")
        )

        # Stage 3: Data Quality Checks
        update_progress(40, "Data Quality Filtering")
        df_valid_keys = df_norm.filter(F.col("student_id").isNotNull() & (F.length(F.trim(F.col("student_id"))) > 0))

        # Stage 4: Windowed Deduplication (Partition by student + subject + semester)
        update_progress(50, "Windowed Deduplication")
        w_spec = Window.partitionBy("student_id", "subject_code", "semester").orderBy(F.col("internal_marks").desc_nulls_last())
        df_dedup = df_valid_keys.withColumn("row_rank", F.row_number().over(w_spec)) \
                                .filter(F.col("row_rank") == 1) \
                                .drop("row_rank")

        # Stage 5 & 6: Data Cleaning & Status Validation
        update_progress(60, "Marks Validation & Cleaning")
        is_absent_cond = (
            F.upper(F.trim(F.coalesce(F.col("raw_external"), F.lit("")))).isin("AB", "ABS", "ABSENT") |
            F.upper(F.trim(F.coalesce(F.col("raw_internal"), F.lit("")))).isin("AB", "ABS", "ABSENT")
        )
        is_valid_range_cond = (
            F.col("internal_marks").isNotNull() &
            F.col("external_marks").isNotNull() &
            (F.col("internal_marks").between(0.0, F.col("max_internal"))) &
            (F.col("external_marks").between(0.0, F.col("max_external")))
        )
        is_missing_cond = (
            (F.col("internal_marks").isNull() | F.col("external_marks").isNull()) &
            ~is_absent_cond
        )

        df_cleaned = df_dedup.withColumn("is_absent", is_absent_cond) \
                             .withColumn("is_valid_range", is_valid_range_cond) \
                             .withColumn("is_missing", is_missing_cond)

        # Stage 7: Derived Field Calculations
        update_progress(70, "Derived Field Calculations")
        df_calc = df_cleaned.withColumn(
            "total_marks",
            F.when(F.col("is_valid_range"), F.round(F.col("internal_marks") + F.col("external_marks"), 2))
             .otherwise(None)
        ).withColumn(
            "max_total",
            F.col("max_internal") + F.col("max_external")
        ).withColumn(
            "percentage",
            F.when(F.col("total_marks").isNotNull(), F.round((F.col("total_marks") / F.col("max_total")) * 100.0, 2))
             .otherwise(None)
        ).withColumn(
            "status",
            F.when(F.col("is_absent"), F.lit("ABSENT"))
             .when(F.col("is_missing"), F.lit("INCOMPLETE"))
             .when(~F.col("is_valid_range"), F.lit("INVALID"))
             .when(
                 (F.col("internal_marks") >= (F.col("max_internal") * 0.4)) &
                 (F.col("external_marks") >= (F.col("max_external") * 0.4)) &
                 (F.col("total_marks") >= (F.col("max_total") * 0.4)),
                 F.lit("PASS")
             ).otherwise(F.lit("FAIL"))
        )

        # Filter out corrupted / out-of-bounds records for analytics
        df_accepted = df_calc.filter(F.col("status").isin("PASS", "FAIL", "ABSENT", "INCOMPLETE"))
        accepted_count = df_accepted.count()
        telemetry["accepted_rows"] = accepted_count
        telemetry["rejected_rows"] = total_raw - accepted_count

        # Stage 8: Aggregation & Academic Analytics
        update_progress(80, "Distributed Academic Aggregations")
        subject_aggs = df_accepted.groupBy("subject_code").agg(
            F.count("*").alias("total_students"),
            F.sum(F.when(F.col("status") == "PASS", 1).otherwise(0)).alias("passed"),
            F.sum(F.when(F.col("status") == "FAIL", 1).otherwise(0)).alias("failed"),
            F.sum(F.when(F.col("status") == "ABSENT", 1).otherwise(0)).alias("absent"),
            F.round(F.avg("total_marks"), 2).alias("average_marks"),
            F.round(F.stddev("total_marks"), 2).alias("std_dev"),
            F.min("total_marks").alias("min_marks"),
            F.max("total_marks").alias("max_marks"),
            F.round(F.expr("percentile_approx(total_marks, 0.5)"), 2).alias("median_marks")
        ).collect()

        subject_summary = []
        for row in subject_aggs:
            p = row["passed"] or 0
            f = row["failed"] or 0
            resolved = p + f
            pass_rate = round((p / resolved) * 100, 2) if resolved > 0 else 0.0
            subject_summary.append({
                "subject_code": row["subject_code"],
                "total_students": row["total_students"],
                "passed": p,
                "failed": f,
                "absent": row["absent"] or 0,
                "average_marks": float(row["average_marks"]) if row["average_marks"] is not None else 0.0,
                "median_marks": float(row["median_marks"]) if row["median_marks"] is not None else 0.0,
                "std_dev": float(row["std_dev"]) if row["std_dev"] is not None else 0.0,
                "min_marks": float(row["min_marks"]) if row["min_marks"] is not None else 0.0,
                "max_marks": float(row["max_marks"]) if row["max_marks"] is not None else 0.0,
                "pass_rate": pass_rate
            })

        # Stage 9: Processed Columnar Parquet Output
        update_progress(90, "Columnar Parquet Persistence")
        parquet_dir = self.config.storage.processed_dir / f"PROC_{dataset_id}"
        df_accepted.write.mode("overwrite").parquet(str(parquet_dir))

        # Write Pre-Aggregated Analytics JSON (data/analytics/AGG_{dataset_id}.json)
        analytics_file = self.config.storage.analytics_dir / f"AGG_{dataset_id}.json"
        now_iso = datetime.now(timezone.utc).isoformat()
        
        overall_passed = sum(s["passed"] for s in subject_summary)
        overall_failed = sum(s["failed"] for s in subject_summary)
        overall_resolved = overall_passed + overall_failed
        overall_pass_rate = round((overall_passed / overall_resolved) * 100, 2) if overall_resolved > 0 else 0.0

        analytics_payload = {
            "dataset_id": dataset_id,
            "generated_at": now_iso,
            "total_records": accepted_count,
            "overall_pass_percentage": overall_pass_rate,
            "subject_summary": subject_summary
        }
        with open(analytics_file, "w", encoding="utf-8") as af:
            json.dump(analytics_payload, af, indent=2)

        # Stage 10: Processing Summary & Telemetry
        elapsed = round(time.time() - start_time, 2)
        telemetry["elapsed_seconds"] = elapsed
        telemetry["records_per_second"] = round(total_raw / elapsed, 1) if elapsed > 0 else 0
        telemetry["parquet_path"] = str(parquet_dir)
        telemetry["analytics_path"] = str(analytics_file)

        update_progress(100, "Processing Complete", telemetry)
        return telemetry

    def process_grade_dataset(
        self,
        dataset_id: str,
        input_csv_path: str,
        progress_callback: Optional[Callable[[int, str, Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes the PySpark Big Data batch pipeline for university grade-based records.
        """
        input_csv_path = str(input_csv_path)
        start_time = time.time()
        spark = self.get_spark()
        telemetry: Dict[str, Any] = {}

        def update_progress(pct: int, stage_name: str, details: Optional[Dict[str, Any]] = None):
            logger.info(f"[{dataset_id[:8]}] Stage {stage_name} ({pct}%)")
            if progress_callback:
                progress_callback(pct, stage_name, details or {})

        # Stage 1: Discovery & Ingestion
        update_progress(10, "Dataset Discovery & Ingestion")
        df_raw = spark.read.option("header", "true").option("inferSchema", "true").csv(input_csv_path)
        total_raw = df_raw.count()
        telemetry["total_raw_rows"] = total_raw

        # Stage 2: Schema Normalization
        update_progress(25, "Schema Normalization")
        df_norm = df_raw.select(
            F.col("student_id").cast(StringType()).alias("student_id"),
            F.coalesce(F.col("department").cast(StringType()), F.lit("CSE")).alias("department"),
            F.coalesce(F.col("semester").cast(IntegerType()), F.lit(1)).alias("semester"),
            F.col("subject_code").cast(StringType()).alias("subject_code"),
            F.coalesce(F.col("subject_name").cast(StringType()), F.lit("")).alias("subject_name"),
            F.col("letter_grade").cast(StringType()).alias("letter_grade"),
            F.coalesce(F.col("grade_status").cast(StringType()), F.lit("PASSED")).alias("grade_status"),
            F.expr("try_cast(grade_point as double)").alias("grade_point"),
            F.expr("try_cast(sgpa as double)").alias("sgpa")
        )

        # Stage 3: Data Quality Filtering
        update_progress(40, "Data Quality Filtering")
        df_valid = df_norm.filter(
            F.col("student_id").isNotNull() & (F.length(F.trim(F.col("student_id"))) > 0) &
            F.col("subject_code").isNotNull() & (F.length(F.trim(F.col("subject_code"))) > 0)
        )

        # Stage 4: Deduplication
        update_progress(50, "Windowed Deduplication")
        df_dedup = df_valid.dropDuplicates(["student_id", "subject_code", "semester"])

        accepted_count = df_dedup.count()
        telemetry["accepted_rows"] = accepted_count
        telemetry["rejected_rows"] = total_raw - accepted_count

        # Stage 5: Distributed Aggregations
        update_progress(80, "Distributed Academic Aggregations")
        subject_aggs = df_dedup.groupBy("subject_code").agg(
            F.count("*").alias("total_students"),
            F.sum(F.when(F.col("grade_status") == "PASSED", 1).otherwise(0)).alias("passed"),
            F.sum(F.when(F.col("grade_status") == "FAILED", 1).otherwise(0)).alias("failed"),
            F.sum(F.when(F.col("grade_status") == "ABSENT", 1).otherwise(0)).alias("absent")
        ).collect()

        subject_summary = []
        for row in subject_aggs:
            p = row["passed"] or 0
            f = row["failed"] or 0
            resolved = p + f
            pass_rate = round((p / resolved) * 100, 2) if resolved > 0 else 0.0
            subject_summary.append({
                "subject_code": row["subject_code"],
                "total_students": row["total_students"],
                "passed": p,
                "failed": f,
                "absent": row["absent"] or 0,
                "pass_rate": pass_rate
            })

        # Stage 6: Columnar Parquet Output
        update_progress(90, "Columnar Parquet Persistence")
        parquet_dir = self.config.storage.processed_dir / f"PROC_{dataset_id}"
        df_dedup.write.mode("overwrite").parquet(str(parquet_dir))

        elapsed = round(time.time() - start_time, 2)
        telemetry["elapsed_seconds"] = elapsed
        telemetry["records_per_second"] = round(total_raw / elapsed, 1) if elapsed > 0 else 0
        telemetry["parquet_path"] = str(parquet_dir)

        update_progress(100, "Processing Complete", telemetry)
        return telemetry

    def stop(self) -> None:
        """Stops active PySpark session."""
        if self._spark is not None:
            self._spark.stop()
            self._spark = None
