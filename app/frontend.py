"""
frontend.py - Serves the SPA at GET /
Flask app handles static/ and templates/ from project root.
"""
from functools import wraps

from flask import Blueprint, redirect, render_template, request, session, url_for

frontend_bp = Blueprint("frontend", __name__)


# ── Auth guard ─────────────────────────────────────────────────────────────

def login_required(f):
    """Redirect to /login if the user is not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("auth.login_page", next=request.path))
        return f(*args, **kwargs)
    return decorated


# ── Pages ──────────────────────────────────────────────────────────────────

@frontend_bp.route("/", methods=["GET"])
@login_required
def index():
    return render_template("index.html")


@frontend_bp.route("/api-keys", methods=["GET"])
@login_required
def api_keys_page():
    return render_template("api-keys.html")
