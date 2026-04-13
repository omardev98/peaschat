"""
routes/logs_routes.py — Request logs viewer.

Endpoints:
  GET  /logs                 → logs HTML page  (login required)
  GET  /api/logs             → JSON list of logs  (login required)
  DELETE /api/logs/<id>      → delete one log  (login required)
  DELETE /api/logs           → clear all logs  (login required)
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

import database as db
from app.frontend import login_required

logs_bp = Blueprint("logs", __name__)


# ── Page ───────────────────────────────────────────────────────────────────

@logs_bp.route("/logs", methods=["GET"])
@login_required
def logs_page():
    return render_template("logs.html")


# ── API ────────────────────────────────────────────────────────────────────

@logs_bp.route("/api/logs", methods=["GET"])
@login_required
def list_logs():
    limit    = min(int(request.args.get("limit",  100)), 500)
    offset   = int(request.args.get("offset", 0))
    search   = request.args.get("search",   "").strip()
    endpoint = request.args.get("endpoint", "").strip()

    rows, total = db.get_logs(limit=limit, offset=offset, search=search, endpoint=endpoint)
    return jsonify({"logs": rows, "total": total, "limit": limit, "offset": offset})


@logs_bp.route("/api/logs/<int:log_id>", methods=["DELETE"])
@login_required
def delete_log(log_id: int):
    found = db.delete_log(log_id)
    if not found:
        return jsonify({"error": "Log not found"}), 404
    return jsonify({"ok": True})


@logs_bp.route("/api/logs", methods=["DELETE"])
@login_required
def clear_logs():
    count = db.clear_logs()
    return jsonify({"ok": True, "deleted": count})
