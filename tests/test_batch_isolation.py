"""
EduPulse Analytics - Batch Project Isolation & Dataset Count Verification Tests
Verifies strict data partitioning between cohorts (e.g. 2023-2027 vs 2024-2027)
and confirms dataset counts accurately increment without cross-cohort contamination.
"""
import pytest
from app import create_app
from services.project_service import ProjectService
from services.analytics_service import AnalyticsService


@pytest.fixture
def app_client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        with app.app_context():
            yield client


def test_batch_dataset_counts_and_isolation(app_client):
    ps = ProjectService()
    projects = ps.get_all_projects()

    # Find 2023-2027 and 2024-2027 projects
    p_2023 = next((p for p in projects if "2023" in p.get("name", "")), None)
    p_2024 = next((p for p in projects if "2024" in p.get("name", "")), None)

    assert p_2023 is not None, "2023-2027 project must exist"
    assert p_2024 is not None, "Batch 2024 - 2027 (CSE) project must exist"

    # Dataset count must reflect actual linked datasets: 6 for 2023, 0 for 2024
    assert p_2023["dataset_count"] == 6, f"Expected 6 datasets for 2023 batch, got {p_2023['dataset_count']}"
    assert p_2024["dataset_count"] == 0, f"Expected 0 datasets for 2024 batch, got {p_2024['dataset_count']}"

    # 1. Test Dashboard for 2024 batch: Must NOT display 2023 batch datasets
    res_2024 = app_client.get(f"/dashboard/?project_id={p_2024['project_id']}")
    assert res_2024.status_code == 200
    html_2024 = res_2024.data.decode("utf-8")
    assert "No Analytical Data Available" in html_2024 or "No academic datasets have been uploaded yet" in html_2024
    # Must NOT show the 355 students from 2023 batch
    assert "Across 355 students" not in html_2024
    assert "93.34%" not in html_2024

    # 2. Test Dashboard for 2023 batch: MUST display 2023 datasets and analytics
    res_2023 = app_client.get(f"/dashboard/?project_id={p_2023['project_id']}")
    assert res_2023.status_code == 200
    html_2023 = res_2023.data.decode("utf-8")
    assert "Total Students" in html_2023
    assert "355" in html_2023

    # 3. Test Academic Analysis for 2024 batch: Empty state
    res_aa_2024 = app_client.get(f"/academic-analysis/?project_id={p_2024['project_id']}")
    assert res_aa_2024.status_code == 200
    html_aa_2024 = res_aa_2024.data.decode("utf-8")
    assert "No Datasets Uploaded" in html_aa_2024 or "No Subject Records Found" in html_aa_2024

    # 4. Test Reports for 2024 batch: Empty state
    res_rep_2024 = app_client.get(f"/reports/?project_id={p_2024['project_id']}")
    assert res_rep_2024.status_code == 200
    html_rep_2024 = res_rep_2024.data.decode("utf-8")
    assert "No Reports Available" in html_rep_2024 or "No Processed Datasets Found" in html_rep_2024

    # 5. Test AnalyticsService scoping directly
    analytics_svc = AnalyticsService()
    dids_2024 = ps.get_project_dataset_ids(p_2024["project_id"])
    assert len(dids_2024) == 0, f"2024 batch must have 0 dataset IDs, got {dids_2024}"

    analytics_2024 = analytics_svc.get_dataset_analytics("ALL", project_id=p_2024["project_id"])
    assert analytics_2024 is None, "Analytics for empty cohort must return None"
