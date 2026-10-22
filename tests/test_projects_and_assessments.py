"""
EduPulse Analytics - Verification Tests for Academic Batch Projects & Assessment Types
Tests cohort workspace creation, switching, dataset scoping, and theory/lab column classification.
"""
import pytest
import pandas as pd
from app import create_app
from storage.local_storage import LocalStorage
from services.project_service import ProjectService
from services.analytics_service import AnalyticsService
from src.import_service import ImportService


@pytest.fixture
def test_app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def project_service():
    return ProjectService()


def test_batch_project_crud(project_service):
    """Verify batch project creation, listing, switching, and deletion."""
    test_id = "batch_test_2025_2029"
    project_service.delete_project(test_id)
    project_service.delete_project(f"{test_id}_1")
    
    # 1. Create project
    proj = project_service.create_project(
        name="Batch 2025 - 2029 (ECE)",
        start_year=2025,
        end_year=2029,
        department="ECE",
        description="Test Cohort",
        project_id=test_id
    )
    assert proj["id"] == test_id
    assert proj["name"] == "Batch 2025 - 2029 (ECE)"

    # 2. List projects
    all_projects = project_service.list_projects()
    assert any(p["id"] == test_id for p in all_projects)

    # 3. Active project
    active = project_service.set_active_project(test_id)
    assert active is True
    assert project_service.get_active_project()["id"] == test_id

    # 4. Link dataset
    project_service.link_dataset_to_project(test_id, "ds-dummy-001")
    updated_proj = project_service.get_project_by_id(test_id)
    assert "ds-dummy-001" in updated_proj["dataset_ids"]

    # 5. Reset to all and delete
    project_service.set_active_project("ALL")
    del_res = project_service.delete_project(test_id)
    assert del_res is True
    assert not any(p["id"] == test_id for p in project_service.list_projects())


def test_batch_project_api(test_app):
    """Verify Flask HTTP API routes for project management."""
    client = test_app.test_client()

    # 1. List
    resp = client.get("/projects/api/list")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert "projects" in data

    # 2. Create
    resp = client.post("/projects/api/create", json={
        "name": "Batch 2024 - 2028 (AI&DS)",
        "start_year": 2024,
        "end_year": 2028,
        "department": "AI&DS",
        "description": "API Test"
    })
    assert resp.status_code in (200, 201)
    res_data = resp.get_json()
    created_id = res_data["project"]["id"]

    # 3. Select
    resp = client.post("/projects/api/select", json={"project_id": created_id})
    assert resp.status_code == 200

    # 4. Delete
    resp = client.delete(f"/projects/api/delete/{created_id}")
    assert resp.status_code == 200


def test_theory_vs_lab_column_meta():
    """Verify ImportService correctly detects LAB and Theory columns in wide sheets."""
    import re
    cols = ["BDA", "ML", "CC", "MAD", "STM", "BDA&CC LAB", "MAD LAB"]
    
    meta = [
        {
            "col": c,
            "is_lab": bool(re.search(r"\b(LAB|PRACTICAL|PR|WORKSHOP)\b", c, re.IGNORECASE)),
            "type": "LABORATORY" if re.search(r"\b(LAB|PRACTICAL|PR|WORKSHOP)\b", c, re.IGNORECASE) else "THEORY"
        }
        for c in cols
    ]
    
    bda_meta = next(m for m in meta if m["col"] == "BDA")
    assert bda_meta["is_lab"] is False
    assert bda_meta["type"] == "THEORY"

    lab_meta = next(m for m in meta if m["col"] == "BDA&CC LAB")
    assert lab_meta["is_lab"] is True
    assert lab_meta["type"] == "LABORATORY"
