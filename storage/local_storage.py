"""
EduPulse Analytics - Local Storage Engine
Implements file-first repository management with atomic writes and path sandboxing.
"""
import os
import json
import shutil
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from werkzeug.utils import secure_filename
from config.settings import StorageConfig, get_config

logger = logging.getLogger(__name__)


class LocalStorage:
    """
    Manages local filesystem data persistence for raw uploads, validated datasets,
    Parquet partitions, and cryptographic JSON audit manifests.
    """
    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or get_config().storage
        self.config.ensure_directories()

    def resolve_safe_path(self, base_dir: Path, requested_name: str) -> Path:
        """
        Enforces path sandboxing to protect against directory traversal attacks (CWE-22).
        """
        base = base_dir.resolve()
        target = (base / requested_name).resolve()
        if not str(target).startswith(str(base)):
            logger.error(f"Directory traversal attempt detected: {requested_name}")
            raise PermissionError(f"Security Alert: Directory traversal detected for path: {requested_name}")
        return target

    def compute_sha256(self, file_path: Path) -> str:
        """Computes SHA-256 checksum of a file in streaming chunks."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def atomic_write(self, target_path: Path, content: Union[str, bytes]) -> Path:
        """
        Performs an atomic write: writes to a temporary file in data/temp/
        then replaces the target file via os.replace to prevent partial writes.
        Includes Windows-compatible retry logic for transient file locks.
        """
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.config.temp_dir / f"tmp_{target_path.stem}_{os.urandom(6).hex()}{target_path.suffix}"
        
        mode = "wb" if isinstance(content, bytes) else "w"
        encoding = None if isinstance(content, bytes) else "utf-8"
        
        with open(temp_file, mode, encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        for attempt in range(10):
            try:
                os.replace(temp_file, target_path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.05)

        return target_path

    def atomic_write_json(self, target_path: Path, data: Dict[str, Any]) -> Path:
        """Atomically serializes Python dictionary to a formatted JSON file."""
        json_content = json.dumps(data, indent=2, ensure_ascii=False)
        return self.atomic_write(target_path, json_content)

    def read_json(self, target_path: Path) -> Optional[Dict[str, Any]]:
        """Reads and parses a JSON file safely with transient lock retry."""
        if not target_path.exists():
            return None
        for attempt in range(10):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (PermissionError, json.JSONDecodeError):
                if attempt == 9:
                    return None
                time.sleep(0.05)
        return None

    def save_raw_upload(
        self,
        dataset_id: str,
        original_filename: str,
        file_bytes: bytes
    ) -> Tuple[Path, str, int]:
        """
        Permanently saves untouched raw upload to data/raw/RAW_{dataset_id}.{ext}.
        Returns: (stored_path, sha256_checksum, file_size_bytes)
        """
        safe_name = secure_filename(original_filename)
        ext = Path(safe_name).suffix.lower() or ".csv"
        target_name = f"RAW_{dataset_id}{ext}"
        target_path = self.resolve_safe_path(self.config.raw_dir, target_name)

        self.atomic_write(target_path, file_bytes)
        file_size = len(file_bytes)
        checksum = self.compute_sha256(target_path)

        logger.info(f"Raw file saved: {target_name} ({file_size} bytes, SHA256: {checksum[:12]}...)")
        return target_path, checksum, file_size

    def save_validated_dataset(self, dataset_id: str, csv_content: str) -> Path:
        """
        Saves cleaned, schema-normalized tabular records to data/validated/VAL_{dataset_id}.csv.
        """
        target_name = f"VAL_{dataset_id}.csv"
        target_path = self.resolve_safe_path(self.config.validated_dir, target_name)
        self.atomic_write(target_path, csv_content)
        logger.info(f"Validated dataset saved: {target_name}")
        return target_path

    def save_manifest(self, dataset_id: str, manifest_data: Dict[str, Any]) -> Path:
        """
        Saves cryptographic audit manifest to data/manifests/MAN_{dataset_id}.json.
        """
        target_name = f"MAN_{dataset_id}.json"
        target_path = self.resolve_safe_path(self.config.manifests_dir, target_name)
        self.atomic_write_json(target_path, manifest_data)
        logger.info(f"Import Manifest saved: {target_name}")
        return target_path

    def get_manifest(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves an existing import manifest by dataset_id."""
        target_name = f"MAN_{dataset_id}.json"
        try:
            target_path = self.resolve_safe_path(self.config.manifests_dir, target_name)
            return self.read_json(target_path)
        except PermissionError:
            return None

    def list_manifests(self) -> List[Dict[str, Any]]:
        """
        Lists all registered dataset manifests ordered by import timestamp descending.
        """
        manifests = []
        for file in sorted(self.config.manifests_dir.glob("MAN_*.json"), key=os.path.getmtime, reverse=True):
            try:
                data = self.read_json(file)
                if data:
                    manifests.append(data)
            except Exception as e:
                logger.warning(f"Error reading manifest {file.name}: {e}")
        return manifests

    def save_draft(self, draft_id: str, draft_data: Dict[str, Any]) -> Path:
        """
        Saves an in-progress class marks entry draft to data/drafts/DRAFT_{draft_id}.json.
        """
        target_name = f"DRAFT_{draft_id}.json"
        target_path = self.resolve_safe_path(self.config.drafts_dir, target_name)
        self.atomic_write_json(target_path, draft_data)
        logger.info(f"Draft saved: {target_name}")
        return target_path

    def get_draft(self, draft_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves an existing draft by draft_id."""
        target_name = f"DRAFT_{draft_id}.json"
        try:
            target_path = self.resolve_safe_path(self.config.drafts_dir, target_name)
            return self.read_json(target_path)
        except PermissionError:
            return None

    def list_drafts(self) -> List[Dict[str, Any]]:
        """Lists all existing drafts ordered by modification time descending."""
        drafts = []
        for file in sorted(self.config.drafts_dir.glob("DRAFT_*.json"), key=os.path.getmtime, reverse=True):
            try:
                data = self.read_json(file)
                if data:
                    drafts.append(data)
            except Exception as e:
                logger.warning(f"Error reading draft {file.name}: {e}")
        return drafts

    def delete_draft(self, draft_id: str) -> bool:
        """Deletes a draft file."""
        target_name = f"DRAFT_{draft_id}.json"
        try:
            target_path = self.resolve_safe_path(self.config.drafts_dir, target_name)
            if target_path.exists():
                target_path.unlink()
                logger.info(f"Draft deleted: {target_name}")
                return True
        except Exception as e:
            logger.error(f"Error deleting draft {draft_id}: {e}")
        return False

    def delete_dataset(self, dataset_id: str) -> bool:
        """
        Permanently removes a dataset and all its associated artifacts:
        - Cryptographic audit manifest (data/manifests/MAN_{dataset_id}.json)
        - Validated tabular dataset (data/validated/VAL_{dataset_id}.csv)
        - Untouched raw upload (data/raw/RAW_{dataset_id}.*)
        - Pre-computed analytical snapshot cache (data/analytics/AGG_{dataset_id}.json)
        - Processed Parquet partition directory (data/processed/PROC_{dataset_id})
        - Generated reports (data/reports/REP_{dataset_id}.*)
        """
        deleted_any = False
        try:
            # 1. Manifest
            man_name = f"MAN_{dataset_id}.json"
            man_path = self.resolve_safe_path(self.config.manifests_dir, man_name)
            if man_path.exists():
                man_path.unlink()
                deleted_any = True

            # 2. Validated CSV
            val_name = f"VAL_{dataset_id}.csv"
            val_path = self.resolve_safe_path(self.config.validated_dir, val_name)
            if val_path.exists():
                val_path.unlink()
                deleted_any = True

            # 3. Raw uploads matching RAW_{dataset_id}.*
            for raw_file in self.config.raw_dir.glob(f"RAW_{dataset_id}.*"):
                try:
                    raw_file.unlink()
                    deleted_any = True
                except Exception as e:
                    logger.warning(f"Could not remove raw file {raw_file.name}: {e}")

            # 4. Analytics cache AGG_{dataset_id}.json
            agg_name = f"AGG_{dataset_id}.json"
            agg_path = self.resolve_safe_path(self.config.analytics_dir, agg_name)
            if agg_path.exists():
                agg_path.unlink()
                deleted_any = True

            # 5. Processed Parquet directory PROC_{dataset_id}
            proc_dir = self.config.processed_dir / f"PROC_{dataset_id}"
            if proc_dir.exists() and proc_dir.is_dir():
                shutil.rmtree(proc_dir, ignore_errors=True)
                deleted_any = True

            # 6. Generated Reports REP_{dataset_id}.*
            for rep_file in self.config.reports_dir.glob(f"REP_{dataset_id}.*"):
                try:
                    rep_file.unlink()
                    deleted_any = True
                except Exception as e:
                    logger.warning(f"Could not remove report file {rep_file.name}: {e}")

            if deleted_any:
                # Also unlink from batch projects in projects.json
                try:
                    projects_file = self.config.data_dir / "projects.json"
                    if projects_file.exists():
                        projects_data = self.read_json(projects_file)
                        if projects_data and isinstance(projects_data, list):
                            dirty = False
                            for p in projects_data:
                                if dataset_id in p.get("dataset_ids", []):
                                    p["dataset_ids"].remove(dataset_id)
                                    p["updated_at"] = datetime.now().isoformat()
                                    dirty = True
                            if dirty:
                                self.atomic_write_json(projects_file, projects_data)
                except Exception:
                    pass

                logger.info(f"Dataset {dataset_id} and all associated artifacts permanently removed.")
                return True
        except Exception as e:
            logger.error(f"Error removing dataset {dataset_id}: {e}")
            raise e
        return False

    def delete_all_datasets(self) -> int:
        """
        Permanently removes all datasets and their associated artifacts across:
        manifests, validated datasets, raw uploads, analytics caches, processed partitions, and reports.
        Returns the number of datasets deleted.
        """
        dataset_ids = set()

        for man_file in self.config.manifests_dir.glob("MAN_*.json"):
            ds_id = man_file.name[4:-5]
            if ds_id:
                dataset_ids.add(ds_id)

        for val_file in self.config.validated_dir.glob("VAL_*.csv"):
            ds_id = val_file.name[4:-4]
            if ds_id:
                dataset_ids.add(ds_id)

        for raw_file in self.config.raw_dir.glob("RAW_*.*"):
            stem = raw_file.stem
            if stem.startswith("RAW_"):
                ds_id = stem[4:]
                if ds_id:
                    dataset_ids.add(ds_id)

        count = 0
        for ds_id in dataset_ids:
            try:
                if self.delete_dataset(ds_id):
                    count += 1
            except Exception as e:
                logger.warning(f"Error deleting dataset {ds_id} during delete_all: {e}")

        # In addition, ensure all residual or orphaned files are cleaned
        for agg_file in self.config.analytics_dir.glob("AGG_*.json"):
            try:
                agg_file.unlink()
            except Exception as e:
                logger.warning(f"Could not remove residual analytics file {agg_file.name}: {e}")

        for proc_dir in self.config.processed_dir.glob("PROC_*"):
            if proc_dir.is_dir():
                try:
                    shutil.rmtree(proc_dir, ignore_errors=True)
                except Exception as e:
                    logger.warning(f"Could not remove residual processed dir {proc_dir.name}: {e}")

        for rep_file in self.config.reports_dir.glob("REP_*.*"):
            try:
                rep_file.unlink()
            except Exception as e:
                logger.warning(f"Could not remove residual report file {rep_file.name}: {e}")

        logger.info(f"Purged all datasets: {count} datasets removed.")
        return count


