"""
routes/provider_routes.py — CRUD API for AI provider configuration
                           + Settings page route.

Endpoints (no prefix — paths are absolute):
  GET    /settings                    → settings HTML page
  GET    /api/providers               → list all providers
  GET    /api/providers/<slug>        → single provider
  PUT    /api/providers/<slug>        → update api_key / model / base_url
  POST   /api/providers/<slug>/activate → set as active
  POST   /api/providers/<slug>/test   → test connection
  DELETE /api/providers/<slug>        → reset to defaults (api_key=NULL)
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, render_template, request

import database as db
from app.frontend import login_required
from core.provider_factory import PROVIDER_MAP, get_provider

logger = logging.getLogger(__name__)

provider_bp = Blueprint("providers", __name__)


# ── Helpers ────────────────────────────────────────────────────────────────

def mask_key(key: str | None) -> str:
    """Return masked key for safe external display. Empty string = not set."""
    if not key:
        return ""
    if len(key) < 8:
        return "••••••••"
    return "••••••••" + key[-4:]


def _safe(provider: dict) -> dict:
    """Strip the raw API key; replace with masked version."""
    return {**provider, "api_key": mask_key(provider.get("api_key"))}


def _err(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


# ── Settings page ──────────────────────────────────────────────────────────

@provider_bp.route("/settings")
@login_required
def settings_page():
    return render_template("settings.html")


# ── REST ───────────────────────────────────────────────────────────────────

@provider_bp.route("/api/providers", methods=["GET"])
def list_providers():
    return jsonify([_safe(p) for p in db.get_all_providers()])


@provider_bp.route("/api/providers/<slug>", methods=["GET"])
def get_one(slug: str):
    p = db.get_provider_by_slug(slug)
    if not p:
        return _err(f"Provider '{slug}' not found.", 404)
    return jsonify(_safe(p))


@provider_bp.route("/api/providers/<slug>", methods=["PUT"])
def update_provider(slug: str):
    if slug not in PROVIDER_MAP:
        return _err(f"Unknown provider '{slug}'.")
    body = request.get_json(silent=True) or {}
    try:
        updated = db.upsert_provider(
            slug=slug,
            api_key=body.get("api_key"),
            model=body.get("model"),
            base_url=body.get("base_url"),
        )
        return jsonify(_safe(updated))
    except ValueError as exc:
        return _err(str(exc))


@provider_bp.route("/api/providers/<slug>/activate", methods=["POST"])
def activate_provider(slug: str):
    if slug not in PROVIDER_MAP:
        return _err(f"Unknown provider '{slug}'.")
    try:
        db.set_active_provider(slug)
        return jsonify({"active": slug})
    except ValueError as exc:
        return _err(str(exc))


@provider_bp.route("/api/providers/<slug>/test", methods=["POST"])
def test_provider(slug: str):
    if slug not in PROVIDER_MAP:
        return _err(f"Unknown provider '{slug}'.")
    try:
        provider = get_provider(slug)
        result   = provider.test_connection()
        return jsonify(result)
    except Exception as exc:
        return jsonify({"ok": False, "latency_ms": 0, "error": str(exc)})


@provider_bp.route("/api/providers/<slug>", methods=["DELETE"])
def reset_provider(slug: str):
    try:
        db.delete_provider(slug)
        return jsonify({"message": f"Provider '{slug}' reset to defaults."})
    except ValueError as exc:
        return _err(str(exc))


@provider_bp.route("/api/active-provider", methods=["GET"])
def active_provider_info():
    """Quick endpoint used by the chat UI to show the current provider badge."""
    config = db.get_active_provider()
    if not config:
        return jsonify({"provider": None, "name": None, "model": None})
    return jsonify({
        "provider": config["slug"],
        "name":     config["name"],
        "model":    config["model"],
    })


# ── API Key admin management ───────────────────────────────────────────────

@provider_bp.route("/api/api-keys", methods=["GET"])
def list_api_keys():
    """List all API keys (no raw keys — show prefix only)."""
    return jsonify(db.list_api_keys())


@provider_bp.route("/api/api-keys", methods=["POST"])
def create_api_key():
    """Create a new API key. Returns the raw key ONCE — copy it now."""
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return _err("name is required")
    try:
        key_data = db.create_api_key(name)
        return jsonify(key_data), 201
    except Exception as exc:
        return _err(str(exc))


@provider_bp.route("/api/api-keys/<int:key_id>", methods=["DELETE"])
def delete_api_key(key_id: int):
    """Permanently delete an API key."""
    deleted = db.delete_api_key(key_id)
    if not deleted:
        return _err(f"API key {key_id} not found.", 404)
    return jsonify({"message": f"API key {key_id} deleted."})


@provider_bp.route("/api/api-keys/<int:key_id>/revoke", methods=["POST"])
def revoke_api_key(key_id: int):
    """Revoke (disable) an API key without deleting it."""
    revoked = db.revoke_api_key(key_id)
    if not revoked:
        return _err(f"API key {key_id} not found.", 404)
    return jsonify({"message": f"API key {key_id} revoked."})
