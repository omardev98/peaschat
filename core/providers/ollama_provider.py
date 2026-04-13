"""
core/providers/ollama_provider.py — Local Ollama LLM provider.
No API key required. Streams via NDJSON.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Generator

import requests

from core.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class OllamaProvider(BaseProvider):

    def __init__(
        self,
        api_key: str = "",
        model: str = "llama3",
        base_url: str | None = None,
    ) -> None:
        super().__init__(api_key, model, base_url)
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")

    # ── Internal ───────────────────────────────────────────────────────────

    def _post(self, messages: list[dict], stream: bool) -> requests.Response:
        return requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model":   self.model,
                "messages": messages,
                "stream":  stream,
                "options": {"temperature": 0.2},
            },
            stream=stream,
            timeout=300,
        )

    # ── BaseProvider ───────────────────────────────────────────────────────

    def generate(self, question: str, context: str, history: list[dict]) -> str:
        msgs = self.build_messages(question, context, history)
        try:
            r = self._post(msgs, stream=False)
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
        except requests.ConnectionError:
            raise RuntimeError("Cannot reach Ollama. Is 'ollama serve' running?")
        except requests.Timeout:
            raise RuntimeError("Ollama timed out. Try a shorter question.")
        except Exception as exc:
            raise RuntimeError(f"Ollama error: {exc}") from exc

    def stream(
        self,
        question: str,
        context: str,
        history: list[dict],
    ) -> Generator[str, None, None]:
        msgs = self.build_messages(question, context, history)
        try:
            r = self._post(msgs, stream=True)
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                data  = json.loads(line)
                token = data.get("message", {}).get("content", "")
                if token:
                    yield token
                if data.get("done"):
                    break
        except requests.ConnectionError:
            raise RuntimeError("Cannot reach Ollama. Is 'ollama serve' running?")
        except requests.Timeout:
            raise RuntimeError("Ollama timed out.")
        except Exception as exc:
            raise RuntimeError(f"Ollama error: {exc}") from exc

    def test_connection(self) -> dict:
        start = time.time()
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            latency = int((time.time() - start) * 1000)
            models  = [m["name"] for m in r.json().get("models", [])]
            pulled  = any(
                m == self.model or m.startswith(self.model + ":")
                for m in models
            )
            if not pulled:
                return {
                    "ok": False,
                    "latency_ms": latency,
                    "error": (
                        f"Model '{self.model}' not pulled. "
                        f"Run: ollama pull {self.model}"
                    ),
                }
            return {"ok": True, "latency_ms": latency, "error": None}
        except requests.ConnectionError:
            return {
                "ok": False,
                "latency_ms": 0,
                "error": "Cannot reach Ollama. Is 'ollama serve' running?",
            }
        except Exception as exc:
            return {"ok": False, "latency_ms": 0, "error": str(exc)}
