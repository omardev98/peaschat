"""
routes/auth_routes.py — Session-based UI authentication.

Endpoints:
  GET  /login            → login page
  POST /api/auth/login   → check credentials, set session
  POST /api/auth/logout  → clear session
  GET  /api/auth/me      → { logged_in: bool, username: str|null }
"""
from __future__ import annotations

from flask import (
    Blueprint, jsonify, redirect, render_template,
    request, session, url_for,
)

from config import ADMIN_USERNAME, ADMIN_PASSWORD

auth_bp = Blueprint("auth", __name__)


# ── Login page ─────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET"])
def login_page():
    if session.get("logged_in"):
        return redirect(url_for("frontend.index"))
    return render_template("login.html")


# ── Login API ──────────────────────────────────────────────────────────────

@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data     = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session.permanent = True
        session["logged_in"] = True
        session["username"]  = username
        return jsonify({"ok": True, "username": username})

    return jsonify({"ok": False, "error": "Identifiants incorrects."}), 401


# ── Logout API ─────────────────────────────────────────────────────────────

@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


# ── Whoami ─────────────────────────────────────────────────────────────────

@auth_bp.route("/api/auth/me", methods=["GET"])
def me():
    return jsonify({
        "logged_in": bool(session.get("logged_in")),
        "username":  session.get("username"),
    })
