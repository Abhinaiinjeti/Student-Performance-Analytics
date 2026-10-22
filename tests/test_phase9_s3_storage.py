"""
EduPulse Analytics - Phase 9 Verification Tests
Tests for S3StorageAdapter: safety guardrails, cost estimations, token validation, and mocked S3 uploads.
"""
from unittest.mock import MagicMock, patch
import pytest
from pathlib import Path
from storage.local_storage import LocalStorage
from storage.s3_storage import S3StorageAdapter
from config.settings import AWSConfig


@pytest.fixture
def mock_dataset():
    """Creates a local dataset fixture with manifest, validated CSV, and parquet mock file."""
    storage = LocalStorage()
    dataset_id = "test-s3-guardrail-001"

    val_file = storage.config.validated_dir / f"VAL_{dataset_id}.csv"
    val_file.write_text("student_id,marks\nSTU-001,85.0\n", encoding="utf-8")

    proc_dir = storage.config.processed_dir / f"PROC_{dataset_id}"
    proc_dir.mkdir(parents=True, exist_ok=True)
    (proc_dir / "part-0000.parquet").write_bytes(b"PARQUET_MOCK_DATA")

    manifest = {
        "dataset_id": dataset_id,
        "model_type": "marks_based",
        "storage_locations": {
            "validated_path": str(val_file),
            "processed_path": str(proc_dir)
        }
    }
    storage.save_manifest(dataset_id, manifest)
    return dataset_id


def test_s3_disabled_by_default():
    """
    Verification Gate: Verify AWS integration is disabled by default and
    blocks any remote operations without explicit configuration.
    """
    adapter = S3StorageAdapter()
    assert adapter.is_enabled() is False

    with pytest.raises(PermissionError) as exc_info:
        adapter.get_client()
    assert "disabled by policy" in str(exc_info.value)


def test_sync_estimate_calculation(mock_dataset):
    """
    Verification Gate: Verify pre-upload payload breakdown, cost estimation,
    and confirmation token generation.
    """
    adapter = S3StorageAdapter()
    estimate = adapter.calculate_sync_estimate(mock_dataset)

    assert estimate["dataset_id"] == mock_dataset
    assert estimate["aws_enabled"] is False
    assert estimate["file_count"] >= 2  # Manifest + Validated CSV + Parquet
    assert estimate["total_bytes"] > 0
    assert estimate["estimated_monthly_cost_usd"] >= 0.0
    assert "confirmation_token" in estimate
    assert len(estimate["confirmation_token"]) == 6
    assert "Local-First Architecture Active" in estimate["policy_status"]


def test_sync_rejection_when_disabled(mock_dataset):
    """
    Verification Gate: Ensure upload attempt fails when AWS_ENABLED=false.
    """
    adapter = S3StorageAdapter()
    with pytest.raises(PermissionError) as exc_info:
        adapter.sync_dataset_to_s3(
            dataset_id=mock_dataset,
            provided_token="ABC123",
            valid_token="ABC123"
        )
    assert "disabled by policy" in str(exc_info.value)


def test_sync_token_verification(mock_dataset):
    """
    Verification Gate: Ensure mismatched confirmation token halts execution before S3 calls.
    """
    enabled_config = AWSConfig(enabled=True, bucket_name="test-lakehouse-bucket", region="us-east-1")
    adapter = S3StorageAdapter(config=enabled_config)

    with pytest.raises(ValueError) as exc_info:
        adapter.sync_dataset_to_s3(
            dataset_id=mock_dataset,
            provided_token="WRONG_TOKEN",
            valid_token="CORRECT_TOKEN"
        )
    assert "Invalid confirmation token" in str(exc_info.value)


def test_mocked_s3_upload_execution(mock_dataset):
    """
    Verification Gate: Verify upload logic with mocked boto3 S3 client (zero AWS charges).
    """
    enabled_config = AWSConfig(enabled=True, bucket_name="my-academic-bucket", region="us-east-1", prefix="archives/")
    adapter = S3StorageAdapter(config=enabled_config)

    mock_s3 = MagicMock()
    adapter._s3_client = mock_s3

    token = "TEST99"
    result = adapter.sync_dataset_to_s3(
        dataset_id=mock_dataset,
        provided_token=token,
        valid_token=token
    )

    assert result["status"] == "success"
    assert result["bucket"] == "my-academic-bucket"
    assert result["total_files"] >= 2

    # Check upload_file was called with ServerSideEncryption
    assert mock_s3.upload_file.call_count >= 2
    for call in mock_s3.upload_file.call_args_list:
        args, kwargs = call
        assert args[1] == "my-academic-bucket"
        assert "archives/test-s3-guardrail-001/" in args[2]
        assert kwargs["ExtraArgs"]["ServerSideEncryption"] == "AES256"
