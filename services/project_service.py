"""
EduPulse Analytics - Academic Project & Batch Workspace Service
Manages institutional student cohorts (e.g., 2023 - 2027 Batch, 2022 - 2026 Batch),
linking multi-semester datasets, internal assessments, and longitudinal student trajectories.
"""
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import pandas as pd

from config.settings import AppConfig, get_config
from storage.local_storage import LocalStorage

logger = logging.getLogger(__name__)


class ProjectService:
    """Manages academic batch projects and dataset groupings."""

    def __init__(self, config: Optional[AppConfig] = None, storage: Optional[LocalStorage] = None):
        self.config = config or get_config()
        self.storage = storage or LocalStorage(self.config.storage)
        self.projects_file = self.config.storage.data_dir / "projects.json"
        self._ensure_projects_file()

    def _ensure_projects_file(self) -> None:
        """Initializes projects.json if it doesn't exist, auto-migrating existing datasets."""
        if not self.projects_file.exists():
            default_projects = self._create_initial_batch_migration()
            self.storage.atomic_write_json(self.projects_file, default_projects)
            logger.info("Initialized projects.json with default batch migration.")

    def _create_initial_batch_migration(self) -> List[Dict[str, Any]]:
        """Creates the initial 2023 - 2027 CSE batch from existing lakehouse datasets."""
        manifests = self.storage.list_manifests()
        dataset_ids = [m["dataset_id"] for m in manifests if "dataset_id" in m]

        default_project = {
            "project_id": "batch_2023_2027_cse",
            "name": "Batch 2023 - 2027 (CSE)",
            "batch": "2023-2027",
            "start_year": 2023,
            "end_year": 2027,
            "department": "Computer Science & Engineering",
            "department_code": "CSE",
            "degree": "B.Tech",
            "regulation": "R20 / Autonomous",
            "description": "Four-Year B.Tech Computer Science & Engineering Undergraduate Cohort",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "is_active": True,
            "dataset_ids": dataset_ids
        }
        return [default_project]

    def get_all_projects(self) -> List[Dict[str, Any]]:
        """Retrieves all registered academic batch projects with live statistics."""
        data = self.storage.read_json(self.projects_file)
        if data is None:
            projects = self._create_initial_batch_migration()
            self.storage.atomic_write_json(self.projects_file, projects)
        else:
            projects = data

        # Enrich each project with live statistics
        manifests = {m["dataset_id"]: m for m in self.storage.list_manifests() if "dataset_id" in m}
        enriched = []
        for p in projects:
            p_copy = dict(p)
            pid = p.get("project_id") or p.get("id")
            p_copy["id"] = pid
            p_copy["project_id"] = pid
            d_ids = p.get("dataset_ids", [])
            p_copy["dataset_ids"] = d_ids
            p_copy["dataset_count"] = len(d_ids)

            # Filter valid existing datasets for statistics
            valid_d_ids = [did for did in d_ids if did in manifests]

            # Calculate total student count and semesters covered
            semesters_found = set()
            total_records = 0
            for did in valid_d_ids:
                m = manifests[did]
                total_records += m.get("row_counts", {}).get("accepted_rows", 0)
                # Try inferring semester
                fn = m.get("source_file", {}).get("original_filename", "")
                sem_match = re.search(r"([1-4])-([1-2])|sem\s*([1-8])|semester\s*([1-8])", fn, re.IGNORECASE)
                if sem_match:
                    for g in sem_match.groups():
                        if g:
                            semesters_found.add(g)

            p_copy["semesters_count"] = len(semesters_found) if semesters_found else max(1, len(valid_d_ids))
            p_copy["total_records"] = total_records
            enriched.append(p_copy)

        return enriched

    def list_projects(self) -> List[Dict[str, Any]]:
        """Alias for get_all_projects."""
        return self.get_all_projects()

    def get_active_project(self) -> Optional[Dict[str, Any]]:
        """Returns the currently active batch project."""
        projects = self.get_all_projects()
        for p in projects:
            if p.get("is_active"):
                return p
        if projects:
            # Fall back to first project and mark active
            projects[0]["is_active"] = True
            self.save_projects(projects)
            return projects[0]
        return None

    def get_project_by_id(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Finds a project by ID."""
        projects = self.get_all_projects()
        for p in projects:
            if p.get("project_id") == project_id or p.get("id") == project_id:
                return p
        return None

    def set_active_project(self, project_id: str) -> bool:
        """Sets the specified project as active."""
        projects = self.storage.read_json(self.projects_file) or []
        found = False
        for p in projects:
            if p.get("project_id") == project_id or p.get("id") == project_id:
                p["is_active"] = True
                found = True
            else:
                p["is_active"] = False

        if found:
            self.save_projects(projects)
            logger.info(f"Switched active project to {project_id}")
        return found

    def save_projects(self, projects: List[Dict[str, Any]]) -> None:
        """Persists the projects list to disk."""
        self.storage.atomic_write_json(self.projects_file, projects)

    def create_project(
        self,
        name: str,
        start_year: int,
        end_year: int,
        department: str = "Computer Science & Engineering",
        department_code: str = "CSE",
        degree: str = "B.Tech",
        regulation: str = "R20 / Autonomous",
        description: str = "",
        set_active: bool = True,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a new batch project."""
        projects = self.storage.read_json(self.projects_file) or []
        
        # Generate safe slug id if not explicitly provided
        if not project_id:
            safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
            project_id = f"batch_{start_year}_{end_year}_{safe_name}"

        # Ensure uniqueness
        existing_ids = {p.get("project_id", p.get("id")) for p in projects}
        counter = 1
        base_id = project_id
        while project_id in existing_ids:
            project_id = f"{base_id}_{counter}"
            counter += 1

        if set_active:
            for p in projects:
                p["is_active"] = False

        new_project = {
            "id": project_id,
            "project_id": project_id,
            "name": name.strip(),
            "batch": f"{start_year}-{end_year}",
            "start_year": int(start_year),
            "end_year": int(end_year),
            "department": department.strip(),
            "department_code": department_code.strip().upper(),
            "degree": degree.strip(),
            "regulation": regulation.strip(),
            "description": description.strip(),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "is_active": set_active,
            "dataset_ids": []
        }

        projects.append(new_project)
        self.save_projects(projects)
        logger.info(f"Created new academic batch project: {name} ({project_id})")
        return new_project

    def link_dataset_to_project(self, project_id: str, dataset_id: str) -> bool:
        """Links a dataset to a batch project and updates dataset manifest."""
        projects = self.storage.read_json(self.projects_file) or []
        found = False
        for p in projects:
            if p.get("project_id") == project_id:
                if "dataset_ids" not in p:
                    p["dataset_ids"] = []
                if dataset_id not in p["dataset_ids"]:
                    p["dataset_ids"].append(dataset_id)
                p["updated_at"] = datetime.now().isoformat()
                found = True

        if found:
            self.save_projects(projects)
            # Also update manifest metadata
            manifest = self.storage.get_manifest(dataset_id)
            if manifest:
                manifest["project_id"] = project_id
                self.storage.save_manifest(dataset_id, manifest)
            logger.info(f"Linked dataset {dataset_id} to project {project_id}")
        return found

    def unlink_dataset_from_project(self, project_id: str, dataset_id: str) -> bool:
        """Unlinks a dataset from a project."""
        projects = self.storage.read_json(self.projects_file) or []
        found = False
        for p in projects:
            if p.get("project_id") == project_id:
                if dataset_id in p.get("dataset_ids", []):
                    p["dataset_ids"].remove(dataset_id)
                    p["updated_at"] = datetime.now().isoformat()
                    found = True

        if found:
            self.save_projects(projects)
            manifest = self.storage.get_manifest(dataset_id)
            if manifest and manifest.get("project_id") == project_id:
                manifest.pop("project_id", None)
                self.storage.save_manifest(dataset_id, manifest)
        return found

    def delete_project(self, project_id: str) -> bool:
        """Deletes a batch project (retains datasets unlinked)."""
        projects = self.storage.read_json(self.projects_file) or []
        initial_len = len(projects)
        projects = [p for p in projects if p.get("project_id") != project_id and p.get("id") != project_id]
        
        if len(projects) < initial_len:
            # Unlink any manifests that pointed to this project
            manifests = self.storage.list_manifests()
            for m in manifests:
                if m.get("project_id") == project_id:
                    m_copy = dict(m)
                    m_copy.pop("project_id", None)
                    self.storage.save_manifest(m["dataset_id"], m_copy)

            # If deleted project was active, make first remaining project active
            if projects and not any(p.get("is_active") for p in projects):
                projects[0]["is_active"] = True
            self.save_projects(projects)
            logger.info(f"Deleted project {project_id}")
            return True
        return False
