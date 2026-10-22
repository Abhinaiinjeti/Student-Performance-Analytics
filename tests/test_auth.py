"""
EduPulse Analytics - Authentication & Role-Based Access Control Verification Tests
Verifies default credential seeding, password hashing, session lifecycle,
and access boundaries between Admin (HOD), Faculty, and Student roles.
"""
import pytest
from app import create_app
from src.auth_service import get_auth_service, AuthService


@pytest.fixture
def test_app():
    app = create_app()
    app.config["TESTING"] = True
    return app


def test_auth_service_seeding_and_credentials():
    """Verify default role accounts are seeded with proper password hashes."""
    auth = get_auth_service()
    
    # 1. Admin authentication
    admin = auth.authenticate("admin@edupulse.edu", "Admin@123")
    assert admin is not None
    assert admin["role"] == "admin"
    assert admin["username"] == "admin"

    # Also supports username login
    admin_by_user = auth.authenticate("admin", "Admin@123")
    assert admin_by_user is not None
    assert admin_by_user["email"] == "admin@edupulse.edu"

    # 2. Faculty authentication
    faculty = auth.authenticate("faculty@edupulse.edu", "Faculty@123")
    assert faculty is not None
    assert faculty["role"] == "faculty"

    # 3. Student authentication
    student = auth.authenticate("student@edupulse.edu", "Student@123")
    assert student is not None
    assert student["role"] == "student"

    # 4. Invalid credentials rejection
    assert auth.authenticate("admin@edupulse.edu", "WrongPassword!") is None
    assert auth.authenticate("nonexistent@edupulse.edu", "Admin@123") is None
    assert auth.authenticate("", "") is None


def test_login_and_logout_flow(test_app):
    """Verify web login, session state, and logout redirects."""
    client = test_app.test_client()

    # Explicit logout first to start clean unauthenticated session
    client.get("/logout")

    # Access protected dashboard -> redirected to login
    res = client.get("/dashboard/", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.location

    # Login with valid faculty credentials
    login_res = client.post("/login", data={
        "identifier": "faculty@edupulse.edu",
        "password": "Faculty@123"
    }, follow_redirects=False)
    assert login_res.status_code == 302
    assert "/dashboard" in login_res.location

    # Dashboard accessible once logged in
    dash_res = client.get("/dashboard/")
    assert dash_res.status_code == 200
    assert b"Faculty" in dash_res.data or b"Dashboard" in dash_res.data

    # Logout
    logout_res = client.get("/logout", follow_redirects=False)
    assert logout_res.status_code == 302
    assert "/login" in logout_res.location


def test_student_role_restrictions(test_app):
    """Verify Student accounts have view-only access and cannot access admin/faculty features."""
    client = test_app.test_client()

    # Login as student
    client.post("/login", data={
        "identifier": "student@edupulse.edu",
        "password": "Student@123"
    })

    # Student can view Dashboard
    res_dash = client.get("/dashboard/")
    assert res_dash.status_code == 200

    # Student can view Academic Analysis
    res_aa = client.get("/academic-analysis/")
    assert res_aa.status_code == 200

    # Student CANNOT access Settings (Admin only) -> redirected
    res_settings = client.get("/settings/", follow_redirects=False)
    assert res_settings.status_code == 302

    # Student CANNOT access Class Marks Entry (Faculty/Admin only) -> redirected
    res_class = client.get("/class-entry/", follow_redirects=False)
    assert res_class.status_code == 302

    # Student CANNOT access Import Wizard -> redirected
    res_import = client.get("/data-management/import", follow_redirects=False)
    assert res_import.status_code == 302
