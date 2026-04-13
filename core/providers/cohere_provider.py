"""
core/providers/cohere_provider.py — Cohere provider.
1000 req/month trial. Get key: https://dashboard.cohere.com/api-keys
Cohere supports native document grounding.
"""
from __future__ import annotations

import logging
import time
from typing import Generator

from core.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class CohereProvider(BaseProvider):

    def __init__(
        self,
        api_key: str,
        model: str = "command-r",
        base_url: str | None = None,
    ) -> None:
        super().__init__(api_key, model, base_url)

    def _client(self):
        try:
            import cohere
        except ImportError:
            raise RuntimeError("cohere package not installed. Run: pip install cohere")
        return cohere.Client(api_key=self.api_key)

    def _chat_history(self, history: list[dict]) -> list[dict]:
        result = []
        for m in history[-6:]:
            role = "USER" if m["role"] == "user" else "CHATBOT"
            result.append({"role": role, "message": m["content"]})
        return result

    def generate(self, question: str, context: str, history: list[dict]) -> str:
        try:
            resp = self._client().chat(
                model=self.model,
                message=question,
                chat_history=self._chat_history(history),
                preamble=f"{self.SYSTEM_PROMPT}\n\nContext:\n{context}",
                temperature=0.2,
            )
            return resp.text.strip()
        except Exception as exc:
            raise self._wrap(exc)

    def stream(
        self,
        question: str,
        context: str,
        history: list[dict],
    ) -> Generator[str, None, None]:
        try:
            for event in self._client().chat_stream(
                model=self.model,
                message=question,
                chat_history=self._chat_history(history),
                preamble=f"{self.SYSTEM_PROMPT}\n\nContext:\n{context}",
                temperature=0.2,
            ):
                token = getattr(event, "text", None)
                if token:
                    yield token
        except Exception as exc:
            raise self._wrap(exc)

    def test_connection(self) -> dict:
        start = time.time()
        try:
            self._client().chat(
                model=self.model,
                message="hi",
                max_tokens=1,
            )
            return {"ok": True, "latency_ms": int((time.time() - start) * 1000), "error": None}
        except Exception as exc:
            return {"ok": False, "latency_ms": 0, "error": str(self._wrap(exc))}

    @staticmethod
    def _wrap(exc: Exception) -> RuntimeError:
        msg = str(exc)
        if "401" in msg or "unauthorized" in msg.lower() or "invalid api key" in msg.lower():
            return RuntimeError("Invalid Cohere API key. Check Settings.")
        if "429" in msg or "rate" in msg.lower():
            return RuntimeError("Cohere rate limit exceeded. Try again later.")
        if "model" in msg.lower() and "not found" in msg.lower():
            return RuntimeError("Model not available. Check model name in Settings.")
        return RuntimeError(f"Cohere error: {exc}")
