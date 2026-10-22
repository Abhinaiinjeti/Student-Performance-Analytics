"""
EduPulse Analytics - Authentication Blueprint Routes
Handles user login, session teardown, demo quick-fill, and profile endpoints.
"""
import logging
from urllib.parse import urlparse, urljoin
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from src.auth_service import (
    get_auth_service, login_user, logout_user,
    get_current_user, is_authenticated
)

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)


def is_safe_url(target: str) -> bool:
    """Validates that a redirect target is internal to the application."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Renders the institution login interface and handles credential verification.
    """
    next_page = request.args.get("next") or request.form.get("next") or ""

    # If already logged in on GET, redirect directly to dashboard or target
    if request.method == "GET" and is_authenticated():
        if next_page and is_safe_url(next_page):
            return redirect(next_page)
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        auth_service = get_auth_service()
        user = auth_service.authenticate(identifier, password)

        if user:
            login_user(user, remember=remember)
            logger.info("User logged in successfully: %s (Role: %s)", user["email"], user["role"])
            flash(f"Welcome back, {user['name']}! Signed in as {user['role'].title()}.", "success")

            if next_page and is_safe_url(next_page):
                return redirect(next_page)
            return redirect(url_for("dashboard.index"))
        else:
            logger.warning("Failed login attempt for identifier: %s", identifier)
            flash("Invalid username/email or password. Please verify your credentials.", "danger")
            return render_template("login.html", identifier=identifier, next=next_page), 401

    return render_template("login.html", next=next_page)


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Terminates the active user session and redirects to the login screen."""
    user = get_current_user()
    if user:
        logger.info("User logged out: %s", user.get("email"))
    logout_user()
    flash("You have been signed out safely.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/api/me", methods=["GET"])
def api_current_user():
    """Returns the profile of the currently authenticated user in JSON format."""
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False, "user": None}), 200
    return jsonify({
        "authenticated": True,
        "user": user
    }), 200
