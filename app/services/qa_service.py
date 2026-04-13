"""
qa_service.py
─────────────
Streaming RAG pipeline using Ollama (100% local, no API key).

Flow:
  1. similarity_search → top-K relevant chunks from FAISS
  2. Build RAG prompt with context
  3. Call Ollama /api/chat with stream=True
  4. Yield SSE tokens to the Flask route

The caller (routes.py) wraps the generator in a Flask Response with
content_type="text/event-stream".
"""

import json
import logging
from typing import Generator, List

import requests

from config import OLLAMA_BASE_URL, OLLAMA_LLM_MODEL
from app.services.vector_store import similarity_search

logger = logging.getLogger(__name__)

# ── Prompts ────────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are a document assistant. "
    "Answer the user question using ONLY the context below. "
    "If the answer is not found in the context, respond with exactly: "
    "'Information not found in document'. "
    "Do not use knowledge from your training data."
)

_HUMAN_TEMPLATE = """\
Context extracted from the document:
{context}

User question: {question}

Answer:"""


def _build_prompt(chunks: List[str], question: str) -> str:
    context = "\n\n---\n\n".join(chunks)
    return _HUMAN_TEMPLATE.format(context=context, question=question)


# ── Streaming Ollama call ──────────────────────────────────────────────────

def stream_answer(document_id: str, question: str) -> Generator[str, None, None]:
    """
    Full streaming RAG pipeline.
    Yields Server-Sent Event strings:
        "data: {\"token\": \"Hello\"}\n\n"
        ...
        "data: {\"done\": true}\n\n"
        "data: {\"error\": \"...\"}\n\n"   ← on failure
    """
    if not question.strip():
        yield _sse({"error": "Question must not be empty."})
        return

    # 1. Retrieve chunks
    try:
        chunks = similarity_search(document_id, question)
    except FileNotFoundError as exc:
        yield _sse({"error": str(exc), "status": 404})
        return
    except RuntimeError as exc:
        # Ollama connection problem during embedding
        yield _sse({"error": str(exc), "status": 502})
        return

    if not chunks:
        yield _sse({"token": "Information not found in document"})
        yield _sse({"done": True})
        return

    # 2. Build prompt
    prompt = _build_prompt(chunks, question)

    # 3. Stream from Ollama
    url     = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": OLLAMA_LLM_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        "stream":  True,
        "options": {"temperature": 0.1, "num_predict": 1024},
    }

    try:
        with requests.post(url, json=payload, stream=True, timeout=300) as resp:
            if resp.status_code != 200:
                yield _sse({"error": f"Ollama returned HTTP {resp.status_code}: {resp.text}"})
                return

            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                token = data.get("message", {}).get("content", "")
                if token:
                    yield _sse({"token": token})

                if data.get("done"):
                    yield _sse({"done": True})
                    return

    except requests.exceptions.ConnectionError:
        yield _sse({
            "error": (
                f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. "
                "Start it with: ollama serve"
            ),
            "status": 502,
        })
    except requests.exceptions.Timeout:
        yield _sse({"error": "Ollama timed out. The model may still be loading.", "status": 504})
    except Exception as exc:
        logger.exception("Unexpected error in stream_answer")
        yield _sse({"error": f"Unexpected error: {exc}", "status": 500})


# ── Non-streaming fallback (used by test_api.py) ───────────────────────────

def answer_question(document_id: str, question: str) -> str:
    """
    Synchronous wrapper — collects the full streamed answer into a string.
    Used by the test script and diagnose tool.
    """
    full = []
    for sse_line in stream_answer(document_id, question):
        if not sse_line.startswith("data: "):
            continue
        payload = json.loads(sse_line[6:])
        if "error" in payload:
            raise RuntimeError(payload["error"])
        if "token" in payload:
            full.append(payload["token"])
        if payload.get("done"):
            break
    return "".join(full)


# ── Helper ─────────────────────────────────────────────────────────────────

def _sse(obj: dict) -> str:
    """Format a dict as a Server-Sent Event line."""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"
