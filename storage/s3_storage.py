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

logger = logging.getLogger(__name__)


class S3StorageAdapter:
    """
    Optional S3 adapter with strict safety guardrails.
    Never transmits data to AWS unless AWS_ENABLED=true and a confirmation token is validated.
    """
    S3_STANDARD_PER_GB_MONTH_USD = 0.023

    def __init__(self, config: Optional[AWSConfig] = None, storage: Optional[LocalStorage] = None):
        self.config = config or get_config().aws
        self.storage = storage or LocalStorage()
        self._s3_client = None

    def is_enabled(self) -> bool:
        """Returns True only if AWS integration is explicitly enabled in configuration."""
        return bool(self.config.enabled and self.config.bucket_name)

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
            files_to_sync.append({"type": "manifest", "path": str(man_path), "bytes": sz})
            total_bytes += sz

        # 2. Validated CSV
        val_path = self.storage.config.validated_dir / f"VAL_{dataset_id}.csv"
        if val_path.exists():
            sz = val_path.stat().st_size
            files_to_sync.append({"type": "validated_csv", "path": str(val_path), "bytes": sz})
            total_bytes += sz

        # 3. Parquet Directory
        proc_dir = self.storage.config.processed_dir / f"PROC_{dataset_id}"
        if proc_dir.exists():
            for p_file in proc_dir.glob("**/*"):
                if p_file.is_file():
                    sz = p_file.stat().st_size
                    files_to_sync.append({"type": "parquet_partition", "path": str(p_file), "bytes": sz})
                    total_bytes += sz

        total_mb = round(total_bytes / (1024 * 1024), 2)
        total_gb = total_bytes / (1024 * 1024 * 1024)
        estimated_monthly_cost = round(total_gb * self.S3_STANDARD_PER_GB_MONTH_USD, 6)

        # Generate single-use confirmation token
        token = secrets.token_hex(3).upper()

        return {
            "dataset_id": dataset_id,
            "aws_enabled": self.is_enabled(),
            "target_bucket": self.config.bucket_name or "Not Configured",
            "target_region": self.config.region,
            "target_prefix": f"{self.config.prefix}{dataset_id}/",
            "file_count": len(files_to_sync),
            "total_bytes": total_bytes,
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
        if not self.is_enabled():
            raise PermissionError("AWS S3 Synchronization is disabled by policy (AWS_ENABLED=false).")

        if not provided_token or provided_token.strip().upper() != valid_token.strip().upper():
            raise ValueError("Invalid confirmation token. Cloud upload rejected.")

        estimate = self.calculate_sync_estimate(dataset_id)
        s3 = self.get_client()
        uploaded_keys = []
        prefix = f"{self.config.prefix}{dataset_id}/"

        # Manifest
        man_path = self.storage.config.manifests_dir / f"MAN_{dataset_id}.json"
        if man_path.exists():
            key = f"{prefix}MAN_{dataset_id}.json"
            s3.upload_file(str(man_path), self.config.bucket_name, key, ExtraArgs={"ServerSideEncryption": "AES256"})
            uploaded_keys.append(key)

        # Validated CSV
        val_path = self.storage.config.validated_dir / f"VAL_{dataset_id}.csv"
        if val_path.exists():
            key = f"{prefix}VAL_{dataset_id}.csv"
            s3.upload_file(str(val_path), self.config.bucket_name, key, ExtraArgs={"ServerSideEncryption": "AES256"})
            uploaded_keys.append(key)

        # Parquet Directory
        proc_dir = self.storage.config.processed_dir / f"PROC_{dataset_id}"
        if proc_dir.exists():
            for p_file in proc_dir.glob("**/*"):
                if p_file.is_file():
                    rel = p_file.relative_to(proc_dir)
                    key = f"{prefix}parquet/{rel.as_posix()}"
                    s3.upload_file(str(p_file), self.config.bucket_name, key, ExtraArgs={"ServerSideEncryption": "AES256"})
                    uploaded_keys.append(key)

        logger.info(f"Successfully synchronized {len(uploaded_keys)} files to S3 bucket {self.config.bucket_name}")
        return {
            "status": "success",
            "dataset_id": dataset_id,
            "bucket": self.config.bucket_name,
            "uploaded_objects": uploaded_keys,
            "total_files": len(uploaded_keys),
            "total_mb": estimate["total_mb"]
        }
