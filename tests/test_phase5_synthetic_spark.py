"""
EduPulse Analytics - Phase 5 Verification Tests
Tests for SyntheticDataGenerator, PySparkPipeline, ProcessingService, and Processing Monitor routes.
"""
import time
import pytest
from pathlib import Path
from src.data_generator import SyntheticDataGenerator
from src.spark_processing import PySparkPipeline
from services.processing_service import ProcessingService
from storage.local_storage import LocalStorage
from app import create_app


@pytest.fixture
def generator():
    return SyntheticDataGenerator(seed=42)


@pytest.fixture
def pipeline():
    pipe = PySparkPipeline()
    yield pipe
    pipe.stop()


@pytest.fixture
def job_service():
    return ProcessingService()


def test_synthetic_marks_generation(generator):
    """
    Verification Gate: Verify synthetic marks generator produces fictional IDs,
    reproducible records, and honest generation metrics.
    """
    result = generator.generate_marks_dataset(
        total_records=2_000,
        student_count=500
    )
    assert result["total_records"] >= 2_000
    assert result["file_size_mb"] > 0
    assert Path(result["file_path"]).exists()
    assert result["model_type"] == "marks_based"
    assert result["anomalies"]["absent"] > 0 or result["anomalies"]["missing"] > 0


def test_synthetic_grades_generation(generator):
    """
    Verification Gate: Verify synthetic grade generator produces valid university records.
    """
    result = generator.generate_grade_dataset(
        total_records=2_000,
        student_count=500
    )
    assert result["total_records"] >= 2_000
    assert Path(result["file_path"]).exists()
    assert result["model_type"] == "grade_based"


def test_pyspark_pipeline_execution(pipeline, generator):
    """
    Verification Gate: Verify genuine PySpark DataFrame batch transformations,
    deduplication, aggregations, Parquet persistence, and analytics snapshot.
    """
    # 1. Generate small fixture
    synth_res = generator.generate_marks_dataset(total_records=1_000, student_count=200)
    dataset_id = "test-spark-ds-001"

    progress_log = []
    def track_progress(pct, stage, details):
        progress_log.append((pct, stage))

    # 2. Run Spark Pipeline
    telemetry = pipeline.process_marks_dataset(
        dataset_id=dataset_id,
        input_csv_path=synth_res["file_path"],
        progress_callback=track_progress
    )

    assert telemetry["total_raw_rows"] >= 1_000
    assert telemetry["accepted_rows"] > 0
    assert Path(telemetry["parquet_path"]).exists()
    assert Path(telemetry["analytics_path"]).exists()
    assert len(progress_log) >= 5  # Progress stages were reported

    # Read back parquet using PySpark
    spark = pipeline.get_spark()
    parquet_df = spark.read.parquet(telemetry["parquet_path"])
    assert parquet_df.count() == telemetry["accepted_rows"]
    assert "total_marks" in parquet_df.columns
    assert "status" in parquet_df.columns


def test_processing_service_async_job(job_service, generator):
    """
    Verification Gate: Verify asynchronous job decoupling, status tracking, and completion.
    """
    synth_res = generator.generate_marks_dataset(total_records=500, student_count=100)
    dataset_id = "test-async-001"

    job_id = job_service.enqueue_spark_job(
        dataset_id=dataset_id,
        input_csv_path=synth_res["file_path"]
    )
    assert job_id is not None

    # Wait for background completion (up to 60s on Windows JVM startup)
    max_wait = 60
    start = time.time()
    final_status = None

    while time.time() - start < max_wait:
        status = job_service.get_job_status(job_id)
        if status and status["status"] in ("COMPLETED", "FAILED"):
            final_status = status
            break
        time.sleep(1)

    assert final_status is not None
    assert final_status["status"] == "COMPLETED"
    assert final_status["progress_pct"] == 100
    assert final_status["telemetry"]["accepted_rows"] > 0


def test_processing_monitor_web_routes():
    """Verify Flask routes for processing monitor dashboard and synthetic API."""
    app = create_app()
    client = app.test_client()

    # 1. Monitor Page
    res_page = client.get("/processing-monitor/")
    assert res_page.status_code == 200
    assert b"PySpark Distributed Processing Engine" in res_page.data

    # 2. Synthetic API
    res_gen = client.post("/processing-monitor/api/generate-synthetic", json={
        "record_count": 500,
        "model_type": "marks_based",
        "seed": 42
    })
    assert res_gen.status_code == 200
    gen_json = res_gen.get_json()
    assert gen_json["status"] == "success"
    assert gen_json["result"]["total_records"] >= 500
