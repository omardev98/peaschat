"""
routes.py - All API endpoints
──────────────────────────────
POST /api/upload          upload PDF or image, get document_id
POST /api/ask             streaming RAG answer (SSE) via active provider
GET  /api/documents       list indexed document IDs
GET  /api/ollama-status   check Ollama health + model availability
GET  /api/health          simple liveness check
"""

import json
import logging
import os
import time
import uuid
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, stream_with_context

from config import UPLOAD_DIR, ALLOWED_EXTENSIONS, IMAGE_EXTENSIONS
from app.services.document_parser import parse_document
from app.services.vector_store    import build_and_save, list_documents, similarity_search
from app.services.ollama_check    import check_ollama
import database as db

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__)


# ── Helpers ────────────────────────────────────────────────────────────────

def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _err(msg: str, status: int = 400):
    logger.warning("API error (%d): %s", status, msg)
    return jsonify({"error": msg}), status


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


# ── Health ─────────────────────────────────────────────────────────────────

@api_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# ── Ollama status ──────────────────────────────────────────────────────────

@api_bp.route("/ollama-status", methods=["GET"])
def ollama_status():
    s     = check_ollama()
    ready = s["ollama_running"] and s["llm_model"] and s["embed_model"]
    return jsonify(s), (200 if ready else 503)


# ── Upload ─────────────────────────────────────────────────────────────────

@api_bp.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return _err("No 'file' field in the request.")

    f = request.files["file"]
    if not f.filename:
        return _err("No file selected.")
    if not _allowed(f.filename):
        ext = f.filename.rsplit(".", 1)[-1] if "." in f.filename else "?"
        return _err(
            f"File type '.{ext}' is not supported. "
            f"Allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )

    doc_id    = str(uuid.uuid4())
    ext       = Path(f.filename).suffix.lower()
    save_path = os.path.join(UPLOAD_DIR, doc_id + ext)
    file_type = "image" if ext.lstrip(".") in IMAGE_EXTENSIONS else "pdf"

    try:
        f.save(save_path)
        logger.info("Saved '%s' -> %s", f.filename, save_path)
    except Exception as exc:
        return _err(f"Could not save file: {exc}", 500)

    try:
        chunks = parse_document(save_path)
    except (ValueError, RuntimeError) as exc:
        os.remove(save_path)
        return _err(str(exc))
    except Exception as exc:
        os.remove(save_path)
        return _err(f"Parsing error: {exc}", 500)

    try:
        build_and_save(doc_id, chunks)
    except RuntimeError as exc:
        return _err(str(exc), 502)
    except Exception as exc:
        return _err(f"Indexing error: {exc}", 500)

    logger.info("Indexed '%s' as %s (%d chunks)", f.filename, doc_id, len(chunks))
    return jsonify({
        "document_id": doc_id,
        "filename":    f.filename,
        "file_type":   file_type,
        "chunks":      len(chunks),
        "message":     "File processed successfully",
    }), 201


# ── Ask (streaming SSE via provider factory) ───────────────────────────────

@api_bp.route("/ask", methods=["POST"])
def ask():
    """
    Streaming QA via Server-Sent Events.

    Accepts JSON body OR multipart/form-data (with optional file):

    JSON:
        { "document_id": "...", "question": "...", "history": [...] }

    Multipart (file upload):
        question    = "Summarize this"
        file        = <PDF / image / txt>
        document_id = (optional, combine file + RAG)

    Response (SSE):
        data: {"token": "Hello"}
        ...
        data: {"done": true, "provider": "groq", "model": "llama3-8b-8192",
               "name": "Groq"}
        data: {"error": "..."}   <- on failure
    """
    is_form = bool(request.form) or bool(request.files)

    if is_form:
        question = (request.form.get("question") or request.form.get("message") or "").strip()
        doc_id   = (request.form.get("document_id") or "").strip()
        history  = []
        uploaded = request.files.get("file")
    else:
        body = request.get_json(force=True, silent=True)
        if not body:
            return _err("Request body must be JSON or multipart/form-data.")
        question = (body.get("question") or body.get("message") or "").strip()
        doc_id   = (body.get("document_id") or "").strip()
        history  = body.get("history", [])
        uploaded = None

    if not question:
        return _err("'question' or 'message' must not be empty.")

    # Extract text from uploaded file (in-memory, never saved)
    file_context = ""
    if uploaded and uploaded.filename:
        try:
            from core.file_extractor import extract_text_from_file
            file_context = extract_text_from_file(uploaded)
            logger.info("File extracted for /api/ask: %s (%d chars)",
                        uploaded.filename, len(file_context))
        except ValueError as exc:
            return _err(str(exc), 415)
        except Exception as exc:
            return _err(f"Could not read file: {exc}", 422)

    logger.info("Ask doc='%s' file=%s q='%s...'",
                doc_id[:8] if doc_id else "none",
                bool(file_context), question[:60])

    client_ip   = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    file_name   = (uploaded.filename if uploaded and uploaded.filename else None)
    history_len = len(history) if isinstance(history, list) else 0
    t_start     = time.time()

    def generate():
        from core.provider_factory import get_provider_with_fallback

        answer_parts: list[str] = []
        log_provider = None
        log_model    = None
        log_status   = "ok"
        log_error    = None

        try:
            provider, slug = get_provider_with_fallback()
        except ValueError as exc:
            err_msg = str(exc)
            yield _sse({"error": err_msg})
            db.insert_log(question=question, status="error", error=err_msg,
                          ip=client_ip, file_name=file_name, has_file=bool(file_context),
                          history_len=history_len,
                          duration_ms=int((time.time() - t_start) * 1000))
            return

        log_provider = slug
        log_model    = provider.model

        # Build context: file text + optional RAG from document_id
        context_parts = []
        if file_context:
            context_parts.append(f"[Attached file content]\n{file_context}")
        if doc_id:
            try:
                chunks = similarity_search(doc_id, question)
                if chunks:
                    context_parts.append("[Relevant document excerpts]\n" +
                                         "\n\n---\n\n".join(chunks))
            except FileNotFoundError:
                err_msg = f"Document '{doc_id}' not found. Please upload it again."
                yield _sse({"error": err_msg})
                db.insert_log(question=question, status="error", error=err_msg,
                              provider=log_provider, model=log_model,
                              ip=client_ip, file_name=file_name, has_file=bool(file_context),
                              history_len=history_len,
                              duration_ms=int((time.time() - t_start) * 1000))
                return
            except Exception as exc:
                err_msg = f"Retrieval error: {exc}"
                yield _sse({"error": err_msg})
                db.insert_log(question=question, status="error", error=err_msg,
                              provider=log_provider, model=log_model,
                              ip=client_ip, file_name=file_name, has_file=bool(file_context),
                              history_len=history_len,
                              duration_ms=int((time.time() - t_start) * 1000))
                return

        context = "\n\n".join(context_parts)

        try:
            for token in provider.stream(question, context, history):
                answer_parts.append(token)
                yield _sse({"token": token})
        except RuntimeError as exc:
            log_status = "error"
            log_error  = str(exc)
            yield _sse({"error": log_error})
        except Exception as exc:
            log_status = "error"
            log_error  = "Provider unreachable. Check your API key in Settings."
            logger.error("Stream error: %s", exc)
            yield _sse({"error": log_error})

        # Fetch provider name for the done badge
        provider_name = slug
        try:
            cfg = db.get_provider_by_slug(slug)
            if cfg:
                provider_name = cfg["name"]
        except Exception:
            pass

        # Save log
        db.insert_log(
            question    = question,
            answer      = "".join(answer_parts),
            provider    = provider_name,
            model       = log_model,
            file_name   = file_name,
            has_file    = bool(file_context),
            history_len = history_len,
            duration_ms = int((time.time() - t_start) * 1000),
            status      = log_status,
            error       = log_error,
            ip          = client_ip,
        )

        if log_status == "ok":
            yield _sse({"done": True, "provider": slug, "model": provider.model, "name": provider_name})

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Documents list ─────────────────────────────────────────────────────────

@api_bp.route("/documents", methods=["GET"])
def documents():
    try:
        docs = list_documents()
    except Exception as exc:
        return _err(f"Could not list documents: {exc}", 500)
    return jsonify({"documents": docs, "count": len(docs)}), 200
