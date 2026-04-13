"""
core/api_key_auth.py — Flask decorator for API key authentication.

Accepts key via:
  Authorization: Bearer lc_xxxxx
  X-API-Key: lc_xxxxx
"""
from __future__ import annotations

import functools
import logging

from flask import jsonify, request

import database as db

logger = logging.getLogger(__name__)


def require_api_key(f):
    """Decorator that enforces a valid LocalChat API key on a route."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        raw_key = _extract_key()
        if not raw_key or not db.validate_api_key(raw_key):
            logger.warning("Rejected request — invalid or missing API key (prefix: %s)",
                           raw_key[:10] if raw_key else "none")
            return jsonify({"error": "Unauthorized — provide a valid API key via "
                                     "'Authorization: Bearer lc_...' or 'X-API-Key: lc_...'",
                            "code": 401}), 401
        return f(*args, **kwargs)
    return wrapper


def _extract_key() -> str | None:
    """Pull the raw key from Authorization header or X-API-Key header."""
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    x_key = request.headers.get("X-API-Key", "").strip()
    if x_key:
        return x_key
    return None
