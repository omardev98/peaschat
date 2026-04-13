"""
routes/public_api_routes.py — Public-facing API (like Groq / OpenAI style).

Blueprint prefix: /v1

Endpoints:
  GET  /v1/health                   — public health check (no auth)
  GET  /v1/providers/active         — currently active provider info (auth required)
  POST /v1/chat                     — send message + optional file, get AI response (auth required)

Authentication:
  Authorization: Bearer lc_xxxxxxxx
  OR
  X-API-Key: lc_xxxxxxxx

File support (in-memory, not saved to disk):
  .pdf              → pdfplumber text extraction
  .png .jpg .jpeg
  .webp .bmp .tiff  → pytesseract OCR
  .txt              → plain UTF-8 read
"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, stream_with_context

import database as db
from core.api_key_auth import require_api_key
from core.provider_factory import get_provider_with_fallback

logger = logging.getLogger(__name__)

public_api_bp = Blueprint("public_api", __name__, url_prefix="/v1")

# Supported file extensions (mirrors core/file_extractor.py)
_PDF_EXT   = {"pdf"}
_IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif"}
_TEXT_EXT  = {"txt", "csv", "json", "md", "log", "yaml", "yml", "xml", "html"}
_WORD_EXT  = {"doc", "docx"}
_EXCEL_EXT = {"xls", "xlsx"}
_ALL_EXT   = _PDF_EXT | _IMAGE_EXT | _TEXT_EXT | _WORD_EXT | _EXCEL_EXT


# ── Health ─────────────────────────────────────────────────────────────────

@public_api_bp.route("/health", methods=["GET"])
def health():
    """Public health check — no API key required."""
    return jsonify({"status": "ok", "version": "1.0"})


# ── Active provider ────────────────────────────────────────────────────────

@public_api_bp.route("/providers/active", methods=["GET"])
@require_api_key
def active_provider():
    """Return info about the currently active AI provider."""
    config = db.get_active_provider()
    if not config:
        return jsonify({"error": "No AI provider is active. Go to /settings."}), 503
    return jsonify({
        "provider": config["slug"],
        "name":     config["name"],
        "model":    config["model"],
    })


# ── Chat ───────────────────────────────────────────────────────────────────

@public_api_bp.route("/chat", methods=["POST"])
@require_api_key
def chat():
    """
    Send a message (+ optional file) to the active AI provider.

    Accepts:
      multipart/form-data  fields: message (str), file (optional), stream ("true"/"false")
      application/json     body:   {"message": str, "stream": bool}

    Returns:
      Non-streaming: JSON response
      Streaming:     text/event-stream (SSE)
    """
    # ── Parse request ────────────────────────────────────────────────────
    # Accept: multipart/form-data, application/x-www-form-urlencoded, application/json
    is_form = bool(request.form) or bool(request.files)

    if is_form:
        message    = (request.form.get("message") or "").strip()
        stream_raw = (request.form.get("stream") or "false").lower()
        do_stream  = stream_raw in ("true", "1", "yes")
        uploaded   = request.files.get("file")
    else:
        body       = request.get_json(force=True, silent=True) or {}
        message    = (body.get("message") or "").strip()
        do_stream  = bool(body.get("stream", False))
        uploaded   = None

    if not message:
        return jsonify({"error": "message field is required"}), 422

    # ── Extract text from file (in-memory) ───────────────────────────────
    file_context = ""
    file_name    = None
    if uploaded and uploaded.filename:
        ext = Path(uploaded.filename).suffix.lower().lstrip(".")
        if ext not in _ALL_EXT:
            return jsonify({"error": f"Unsupported file type: .{ext}. "
                                     f"Supported: {', '.join(sorted(_ALL_EXT))}"}), 415
        file_name = uploaded.filename
        try:
            from core.file_extractor import extract_text_from_file
            file_context = extract_text_from_file(uploaded)
        except Exception as exc:
            logger.warning("File extraction failed: %s", exc)
            return jsonify({"error": f"Could not read file: {exc}"}), 422

    # ── Build prompt ─────────────────────────────────────────────────────
    if file_context:
        prompt = f"{message}\n\n---\nContent to analyze:\n{file_context}"
    else:
        prompt = message

    # ── Get active provider ───────────────────────────────────────────────
    try:
        provider, slug = get_provider_with_fallback()
    except Exception as exc:
        return jsonify({"error": f"No AI provider is active: {exc}"}), 503

    model     = provider.model
    t_start   = time.time()
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")

    log_ctx = {
        "endpoint":  "/v1/chat",
        "question":  message,
        "file_name": file_name,
        "has_file":  bool(file_context),
        "ip":        client_ip,
        "t_start":   t_start,
    }

    # ── Respond ───────────────────────────────────────────────────────────
    if do_stream:
        return _stream_response(provider, prompt, slug, model, log_ctx)
    else:
        return _full_response(provider, prompt, slug, model, log_ctx)


# ── Helpers ────────────────────────────────────────────────────────────────


def _full_response(provider, prompt: str, slug: str, model: str, log_ctx: dict | None = None) -> Response:
    """Collect the full streamed response and return as JSON."""
    t_start = log_ctx["t_start"] if log_ctx else time.time()
    try:
        parts  = list(provider.stream(question=prompt, context="", history=[]))
        answer = "".join(parts)
    except Exception as exc:
        logger.error("Provider error: %s", exc)
        if log_ctx:
            db.insert_log(
                endpoint    = log_ctx["endpoint"],
                question    = log_ctx["question"],
                status      = "error",
                error       = str(exc),
                provider    = slug,
                model       = model,
                file_name   = log_ctx["file_name"],
                has_file    = log_ctx["has_file"],
                ip          = log_ctx["ip"],
                duration_ms = int((time.time() - t_start) * 1000),
            )
        return jsonify({"error": f"Provider error: {exc}"}), 500

    if log_ctx:
        db.insert_log(
            endpoint    = log_ctx["endpoint"],
            question    = log_ctx["question"],
            answer      = answer,
            provider    = slug,
            model       = model,
            file_name   = log_ctx["file_name"],
            has_file    = log_ctx["has_file"],
            ip          = log_ctx["ip"],
            duration_ms = int((time.time() - t_start) * 1000),
        )

    return jsonify({
        "id":       f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object":   "chat.completion",
        "created":  int(time.time()),
        "provider": slug,
        "model":    model,
        "message": {
            "role":    "assistant",
            "content": answer,
        },
        "usage": {
            "note": "Token counts are unavailable for local/proxied providers."
        },
    })


def _stream_response(provider, prompt: str, slug: str, model: str, log_ctx: dict | None = None) -> Response:
    """Return an SSE stream of tokens."""
    t_start = log_ctx["t_start"] if log_ctx else time.time()

    def generate():
        parts = []
        try:
            for token in provider.stream(question=prompt, context="", history=[]):
                parts.append(token)
                yield f'data: {{"delta": {_json_str(token)}, "done": false}}\n\n'

            if log_ctx:
                db.insert_log(
                    endpoint    = log_ctx["endpoint"],
                    question    = log_ctx["question"],
                    answer      = "".join(parts),
                    provider    = slug,
                    model       = model,
                    file_name   = log_ctx["file_name"],
                    has_file    = log_ctx["has_file"],
                    ip          = log_ctx["ip"],
                    duration_ms = int((time.time() - t_start) * 1000),
                )

            yield (
                f'data: {{"delta": "", "done": true, '
                f'"provider": {_json_str(slug)}, "model": {_json_str(model)}}}\n\n'
            )
        except Exception as exc:
            logger.error("Stream error: %s", exc)
            if log_ctx:
                db.insert_log(
                    endpoint    = log_ctx["endpoint"],
                    question    = log_ctx["question"],
                    status      = "error",
                    error       = str(exc),
                    provider    = slug,
                    model       = model,
                    file_name   = log_ctx["file_name"],
                    has_file    = log_ctx["has_file"],
                    ip          = log_ctx["ip"],
                    duration_ms = int((time.time() - t_start) * 1000),
                )
            yield f'data: {{"error": {_json_str(str(exc))}, "done": true}}\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":  "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _json_str(s: str) -> str:
    """Minimal JSON string encoding (handles quotes and backslashes)."""
    import json
    return json.dumps(s)
