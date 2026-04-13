"""
ollama_check.py
───────────────
Utility that verifies Ollama is running and required models are pulled.
Used by routes.py (/api/ollama-status) and diagnose.py.
"""

import logging
from typing import Dict, Any

import requests

from config import OLLAMA_BASE_URL, OLLAMA_LLM_MODEL, OLLAMA_EMBED_MODEL

logger = logging.getLogger(__name__)


def _has_model(models: list, name: str) -> bool:
    """
    Check whether *name* appears in the model list.
    Ollama may suffix models with ':latest' so we match both
    exact name and 'name:*' prefix.
    """
    for m in models:
        model_name = m.get("name", "")
        if model_name == name or model_name.startswith(name + ":"):
            return True
    return False


def check_ollama() -> Dict[str, Any]:
    """
    Returns a status dict:
    {
        "ollama_running": bool,
        "llm_model":      bool,   # OLLAMA_LLM_MODEL available
        "embed_model":    bool,   # OLLAMA_EMBED_MODEL available
        "models":         list,   # all available model names
        "base_url":       str,
        "errors":         list[str],
    }
    """
    status: Dict[str, Any] = {
        "ollama_running": False,
        "llm_model":      False,
        "embed_model":    False,
        "models":         [],
        "base_url":       OLLAMA_BASE_URL,
        "llm_model_name":   OLLAMA_LLM_MODEL,
        "embed_model_name": OLLAMA_EMBED_MODEL,
        "errors":         [],
    }

    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        r.raise_for_status()
        status["ollama_running"] = True

        model_list = r.json().get("models", [])
        status["models"] = [m["name"] for m in model_list]

        status["llm_model"]   = _has_model(model_list, OLLAMA_LLM_MODEL)
        status["embed_model"] = _has_model(model_list, OLLAMA_EMBED_MODEL)

        if not status["llm_model"]:
            status["errors"].append(
                f"LLM model '{OLLAMA_LLM_MODEL}' not found. "
                f"Run:  ollama pull {OLLAMA_LLM_MODEL}"
            )
        if not status["embed_model"]:
            status["errors"].append(
                f"Embedding model '{OLLAMA_EMBED_MODEL}' not found. "
                f"Run:  ollama pull {OLLAMA_EMBED_MODEL}"
            )

    except requests.exceptions.ConnectionError:
        status["errors"].append(
            f"Ollama is not running at {OLLAMA_BASE_URL}. "
            "Start it with:  ollama serve"
        )
    except requests.exceptions.Timeout:
        status["errors"].append(
            f"Ollama did not respond in time at {OLLAMA_BASE_URL}."
        )
    except Exception as exc:
        status["errors"].append(f"Unexpected error checking Ollama: {exc}")

    return status
