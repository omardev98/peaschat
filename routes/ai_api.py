"""
routes/ai_api.py — Public /api/ai/ask endpoint.

Behaves like a hosted LLM API (Groq / OpenAI style) but routes all
requests through whichever AI provider the admin has activated in
/settings.

Endpoint
--------
POST /api/ai/ask

Authentication
--------------
  Authorization: Bearer lc_<key>
  OR
  X-API-Key: lc_<key>

  Keys are created on the /api-keys page in the LocalChat UI.

Request formats
---------------
JSON body:
  { "message": "Your question here" }

Multipart/form-data (when attaching a file):
  message  = "Your question"
  file     = <file field>   -- PDF, image, TXT, CSV, DOCX …

Response 200
------------
  {
    "answer":        "Full AI response text",
    "provider":      "groq",
    "model":         "llama-3.1-8b-instant",
    "file_included": true
  }

Error shapes
------------
  422  { "error": "message is required" }
  415  { "error": "Unsupported file type: '.xyz' …" }
  503  { "error": "AI provider error", "detail": "…" }
  401  { "error": "Unauthorized …", "code": 401 }
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from core.api_key_auth     import require_api_key
from core.file_extractor   import extract_text_from_file
from core.provider_factory import get_provider_with_fallback

logger = logging.getLogger(__name__)

ai_api_bp = Blueprint("ai_api", __name__)


@ai_api_bp.route("/api/ai/ask", methods=["POST"])
@require_api_key
def public_ask():
    # ── 1. Parse message ──────────────────────────────────────────────────────
    if request.is_json:
        body    = request.get_json(force=True) or {}
        message = (body.get("message") or "").strip()
    else:
        message = (request.form.get("message") or "").strip()

    if not message:
        return jsonify({"error": "message is required"}), 422

    # ── 2. Parse optional file ────────────────────────────────────────────────
    file_context  = ""
    file_included = False
    uploaded      = request.files.get("file")

    if uploaded and uploaded.filename:
        try:
            file_context  = extract_text_from_file(uploaded)
            file_included = True
            logger.info("Extracted file '%s' → %d chars", uploaded.filename, len(file_context))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 415

    # ── 3. Call the active provider ───────────────────────────────────────────
    try:
        provider, slug = get_provider_with_fallback()
        answer = provider.generate(
            question=message,
            context=file_context,   # empty string = no RAG context
            history=[],
        )
    except Exception as exc:
        logger.error("Provider error in /api/ai/ask: %s", exc)
        return jsonify({"error": "AI provider error", "detail": str(exc)}), 503

    return jsonify({
        "answer":        answer,
        "provider":      slug,
        "model":         provider.model,
        "file_included": file_included,
    }), 200
