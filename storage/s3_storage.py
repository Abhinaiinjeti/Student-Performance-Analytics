"""
EduPulse Analytics - Optional AWS S3 Cloud Storage Adapter
Disabled by default to enforce local-first privacy.
Provides strict guardrails, pre-upload payload calculation, cost estimations,
and mandatory confirmation tokens for optional cloud synchronization.
"""
import os
import secrets
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from config.settings import AWSConfig, get_config
from storage.local_storage import LocalStorage

from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class S3StorageAdapter:
    """
    Optional S3 adapter with strict safety guardrails.
    Never transmits data to AWS unless AWS_ENABLED=true and a confirmation token is validated.
    Supports Simulation Mode for zero-cost demonstrations and CI testing without AWS credentials.
    """
    S3_STANDARD_PER_GB_MONTH_USD = 0.023

    def __init__(self, config: Optional[AWSConfig] = None, storage: Optional[LocalStorage] = None):
        self.config = config or get_config().aws
        self.storage = storage or LocalStorage()
        self._s3_client = None

    def is_enabled(self) -> bool:
        """Returns True only if AWS integration is explicitly enabled in configuration."""
        return bool(self.config.enabled and self.config.bucket_name)

    def is_simulation(self) -> bool:
        """Returns True if AWS is enabled and simulation mode is specifically requested."""
        return bool(self.config.enabled and getattr(self.config, "simulation_mode", False))

    def get_client(self):
        """Lazy initializer for boto3 S3 client."""
        if not self.is_enabled():
            raise PermissionError("AWS S3 integration is disabled by policy (AWS_ENABLED=false).")

        if self._s3_client is None:
            kwargs = {"region_name": self.config.region}
            if self.config.access_key_id and self.config.secret_access_key:
                kwargs["aws_access_key_id"] = self.config.access_key_id
                kwargs["aws_secret_access_key"] = self.config.secret_access_key

            self._s3_client = boto3.client("s3", **kwargs)
        return self._s3_client

    def test_connection(self) -> Dict[str, Any]:
        """
        Tests AWS S3 connectivity or validates the simulation environment.
        """
        if not self.config.enabled:
            return {
                "status": "error",
                "mode": "disabled",
                "message": "AWS S3 integration is disabled. Enable AWS in settings to connect."
            }

        if self.is_simulation():
            bucket = self.config.bucket_name or "edupulse-analytics-lakehouse"
            return {
                "status": "success",
                "mode": "simulation",
                "message": f"Simulation Mode active. Virtual bucket 's3://{bucket}/' ready for zero-cost archival workflows.",
                "bucket": bucket,
                "region": self.config.region
            }

        if not self.config.bucket_name:
            return {
                "status": "error",
                "mode": "live",
                "message": "Bucket name is required for live AWS S3 connectivity."
            }

        try:
            client = self.get_client()
            client.head_bucket(Bucket=self.config.bucket_name)
            return {
                "status": "success",
                "mode": "live",
                "message": f"Successfully connected to AWS S3 bucket '{self.config.bucket_name}' in region '{self.config.region}'.",
                "bucket": self.config.bucket_name,
                "region": self.config.region
            }
        except ClientError as e:
            error_code = str(e.response.get("Error", {}).get("Code", "Unknown"))
            if error_code in ("404", "NoSuchBucket"):
                msg = f"Bucket '{self.config.bucket_name}' does not exist in region '{self.config.region}'."
            elif error_code in ("403", "AccessDenied"):
                msg = f"Access denied to bucket '{self.config.bucket_name}'. Please verify your IAM credentials and permissions."
            else:
                msg = f"AWS S3 error ({error_code}): {e.response.get('Error', {}).get('Message', str(e))}"
            return {"status": "error", "mode": "live", "message": msg}
        except NoCredentialsError:
            return {
                "status": "error",
                "mode": "live",
                "message": "AWS credentials not found. Please provide Access Key ID and Secret Access Key or enable Simulation Mode."
            }
        except Exception as e:
            return {"status": "error", "mode": "live", "message": f"Connection check failed: {str(e)}"}

    def calculate_sync_estimate(self, dataset_id: str) -> Dict[str, Any]:
        """
        Calculates payload breakdown, object count, and estimated monthly storage cost
        before any cloud transmission is allowed. Generates a one-time confirmation token.
        """
        manifest = self.storage.get_manifest(dataset_id)
        if not manifest:
            raise FileNotFoundError(f"Manifest not found for dataset_id: {dataset_id}")

        files_to_sync = []
        total_bytes = 0

        # 1. Manifest file
        man_path = self.storage.config.manifests_dir / f"MAN_{dataset_id}.json"
        if man_path.exists():
            sz = man_path.stat().st_size
            files_to_sync.append({"type": "manifest", "name": f"MAN_{dataset_id}.json", "path": str(man_path), "bytes": sz})
            total_bytes += sz

        # 2. Validated CSV
        val_path = self.storage.config.validated_dir / f"VAL_{dataset_id}.csv"
        if val_path.exists():
            sz = val_path.stat().st_size
            files_to_sync.append({"type": "validated_csv", "name": f"VAL_{dataset_id}.csv", "path": str(val_path), "bytes": sz})
            total_bytes += sz

        # 3. Parquet Directory
        proc_dir = self.storage.config.processed_dir / f"PROC_{dataset_id}"
        if proc_dir.exists():
            for p_file in proc_dir.glob("**/*"):
                if p_file.is_file():
                    sz = p_file.stat().st_size
                    files_to_sync.append({"type": "parquet_partition", "name": p_file.name, "path": str(p_file), "bytes": sz})
                    total_bytes += sz

        total_mb = round(total_bytes / (1024 * 1024), 4)
        total_kb = round(total_bytes / 1024, 2)
        total_gb = total_bytes / (1024 * 1024 * 1024)
        estimated_monthly_cost = round(total_gb * self.S3_STANDARD_PER_GB_MONTH_USD, 6)

        # Generate single-use confirmation token
        token = secrets.token_hex(3).upper()

        dataset_name = ""
        if manifest.get("source_file") and manifest["source_file"].get("original_filename"):
            dataset_name = manifest["source_file"]["original_filename"]
        else:
            dataset_name = dataset_id

        record_count = manifest.get("row_counts", {}).get("accepted_rows", 0)
        bucket = self.config.bucket_name or "edupulse-analytics-lakehouse"

        return {
            "dataset_id": dataset_id,
            "dataset_name": dataset_name,
            "record_count": record_count,
            "aws_enabled": self.is_enabled(),
            "simulation_mode": self.is_simulation(),
            "target_bucket": bucket,
            "target_region": self.config.region,
            "target_prefix": f"{self.config.prefix}{dataset_id}/",
            "file_count": len(files_to_sync),
            "files": [{"type": f["type"], "name": f["name"], "bytes": f["bytes"]} for f in files_to_sync],
            "total_bytes": total_bytes,
            "total_kb": total_kb,
            "total_mb": total_mb,
            "estimated_monthly_cost_usd": estimated_monthly_cost,
            "confirmation_token": token,
            "policy_status": "Local-First Architecture Active. Cloud upload requires explicit authorization."
        }

    def sync_dataset_to_s3(
        self,
        dataset_id: str,
        provided_token: str,
        valid_token: str
    ) -> Dict[str, Any]:
        """
        Uploads dataset assets to S3. Guarded by configuration check and confirmation token.
        """
        if not self.config.enabled:
            raise PermissionError("AWS S3 Synchronization is disabled by policy (AWS_ENABLED=false).")

        if not self.config.bucket_name and not self.is_simulation():
            raise PermissionError("AWS S3 Synchronization is disabled by policy (AWS_ENABLED=false).")

        if not provided_token or provided_token.strip().upper() != valid_token.strip().upper():
            raise ValueError("Invalid confirmation token. Cloud upload rejected.")

        estimate = self.calculate_sync_estimate(dataset_id)
        bucket = self.config.bucket_name or "edupulse-analytics-lakehouse"
        prefix = f"{self.config.prefix}{dataset_id}/"
        uploaded_keys = []

        # If an explicit mock client is injected or simulation mode is off, invoke client
        use_client = (self._s3_client is not None) or (not self.is_simulation())

        if use_client:
            s3 = self.get_client()
            # Manifest
            man_path = self.storage.config.manifests_dir / f"MAN_{dataset_id}.json"
            if man_path.exists():
                key = f"{prefix}MAN_{dataset_id}.json"
                s3.upload_file(str(man_path), bucket, key, ExtraArgs={"ServerSideEncryption": "AES256"})
                uploaded_keys.append(key)

            # Validated CSV
            val_path = self.storage.config.validated_dir / f"VAL_{dataset_id}.csv"
            if val_path.exists():
                key = f"{prefix}VAL_{dataset_id}.csv"
                s3.upload_file(str(val_path), bucket, key, ExtraArgs={"ServerSideEncryption": "AES256"})
                uploaded_keys.append(key)

            # Parquet Directory
            proc_dir = self.storage.config.processed_dir / f"PROC_{dataset_id}"
            if proc_dir.exists():
                for p_file in proc_dir.glob("**/*"):
                    if p_file.is_file():
                        rel = p_file.relative_to(proc_dir)
                        key = f"{prefix}parquet/{rel.as_posix()}"
                        s3.upload_file(str(p_file), bucket, key, ExtraArgs={"ServerSideEncryption": "AES256"})
                        uploaded_keys.append(key)
        else:
            # Simulation Mode
            man_path = self.storage.config.manifests_dir / f"MAN_{dataset_id}.json"
            if man_path.exists():
                uploaded_keys.append(f"{prefix}MAN_{dataset_id}.json")

            val_path = self.storage.config.validated_dir / f"VAL_{dataset_id}.csv"
            if val_path.exists():
                uploaded_keys.append(f"{prefix}VAL_{dataset_id}.csv")

            proc_dir = self.storage.config.processed_dir / f"PROC_{dataset_id}"
            if proc_dir.exists():
                for p_file in proc_dir.glob("**/*"):
                    if p_file.is_file():
                        rel = p_file.relative_to(proc_dir)
                        uploaded_keys.append(f"{prefix}parquet/{rel.as_posix()}")

        # Record cloud sync in manifest
        manifest = self.storage.get_manifest(dataset_id)
        if manifest:
            manifest["cloud_sync"] = {
                "status": "synced",
                "synced_at": datetime.now(timezone.utc).isoformat(),
                "mode": "simulation" if (self.is_simulation() and self._s3_client is None) else "live",
                "bucket": bucket,
                "region": self.config.region,
                "prefix": prefix,
                "s3_uri": f"s3://{bucket}/{prefix}",
                "uploaded_objects": uploaded_keys,
                "total_mb": estimate["total_mb"],
                "token_used": provided_token.strip().upper()
            }
            self.storage.save_manifest(dataset_id, manifest)

        mode_str = "simulation" if (self.is_simulation() and self._s3_client is None) else "live"
        logger.info(f"Successfully {mode_str} synchronized {len(uploaded_keys)} files to S3 bucket {bucket}")
        return {
            "status": "success",
            "mode": mode_str,
            "dataset_id": dataset_id,
            "bucket": bucket,
            "s3_uri": f"s3://{bucket}/{prefix}",
            "uploaded_objects": uploaded_keys,
            "total_files": len(uploaded_keys),
            "total_mb": estimate["total_mb"]
        }
