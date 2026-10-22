"""
EduPulse Analytics - Asynchronous Processing Job Service
Decouples heavy PySpark batch jobs from web request-response cycles,
managing job telemetry, JSON heartbeats, and fault recovery.
"""
import os
import uuid
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor

from storage.local_storage import LocalStorage
from src.spark_processing import PySparkPipeline
from config.settings import get_config

logger = logging.getLogger(__name__)


class ProcessingService:
    """
    Manages non-blocking asynchronous execution of PySpark batch processing jobs.
    """
    _executor = ThreadPoolExecutor(max_workers=2)

    def __init__(self, storage: Optional[LocalStorage] = None):
        self.storage = storage or LocalStorage()
        self.config = get_config()

    def enqueue_spark_job(
        self,
        dataset_id: str,
        input_csv_path: str,
        model_type: str = "marks_based"
    ) -> str:
        """
        Enqueues an asynchronous batch PySpark job and returns a unique job_id immediately.
        """
        job_id = str(uuid.uuid4())
        initial_state = {
            "job_id": job_id,
            "dataset_id": dataset_id,
            "model_type": model_type,
            "status": "PENDING",
            "progress_pct": 0,
            "current_stage": "Queued in Background Pool",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "end_time": None,
            "elapsed_seconds": 0,
            "telemetry": {},
            "error_message": None
        }

        job_file = self.config.storage.jobs_dir / f"JOB_{job_id}.json"
        self.storage.atomic_write_json(job_file, initial_state)

        # Submit task to background thread pool
        self._executor.submit(
            self._run_job_worker,
            job_id=job_id,
            dataset_id=dataset_id,
            input_csv_path=input_csv_path,
            model_type=model_type
        )

        logger.info(f"Enqueued PySpark batch job {job_id[:8]} for dataset {dataset_id[:8]}")
        return job_id

    def _run_job_worker(
        self,
        job_id: str,
        dataset_id: str,
        input_csv_path: str,
        model_type: str
    ) -> None:
        """Worker thread executing the PySpark pipeline and updating JSON heartbeats."""
        job_file = self.config.storage.jobs_dir / f"JOB_{job_id}.json"
        start_ts = time.time()

        def update_state(pct: int, stage: str, details: Optional[Dict[str, Any]] = None):
            state = self.storage.read_json(job_file) or {}
            state["status"] = "RUNNING"
            state["progress_pct"] = pct
            state["current_stage"] = stage
            state["elapsed_seconds"] = round(time.time() - start_ts, 2)
            if details:
                state["telemetry"] = {**state.get("telemetry", {}), **details}
            self.storage.atomic_write_json(job_file, state)

        try:
            update_state(5, "Initializing Spark Engine")
            pipeline = PySparkPipeline()
            telemetry = pipeline.process_marks_dataset(
                dataset_id=dataset_id,
                input_csv_path=input_csv_path,
                progress_callback=update_state
            )

            # Finalize Job State
            final_state = self.storage.read_json(job_file) or {}
            final_state["status"] = "COMPLETED"
            final_state["progress_pct"] = 100
            final_state["current_stage"] = "Completed Successfully"
            final_state["end_time"] = datetime.now(timezone.utc).isoformat()
            final_state["elapsed_seconds"] = round(time.time() - start_ts, 2)
            final_state["telemetry"] = telemetry
            self.storage.atomic_write_json(job_file, final_state)
            logger.info(f"PySpark batch job {job_id[:8]} finished in {final_state['elapsed_seconds']}s")

        except Exception as e:
            logger.error(f"PySpark batch job {job_id[:8]} failed: {e}", exc_info=True)
            err_state = self.storage.read_json(job_file) or {}
            err_state["status"] = "FAILED"
            err_state["end_time"] = datetime.now(timezone.utc).isoformat()
            err_state["elapsed_seconds"] = round(time.time() - start_ts, 2)
            err_state["error_message"] = str(e)
            self.storage.atomic_write_json(job_file, err_state)

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Reads current state of a background job."""
        job_file = self.config.storage.jobs_dir / f"JOB_{job_id}.json"
        return self.storage.read_json(job_file)

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Lists all batch jobs ordered by timestamp descending."""
        jobs = []
        for file in sorted(self.config.storage.jobs_dir.glob("JOB_*.json"), key=os.path.getmtime, reverse=True):
            try:
                data = self.storage.read_json(file)
                if data:
                    jobs.append(data)
            except Exception as e:
                logger.warning(f"Error reading job {file.name}: {e}")
        return jobs
