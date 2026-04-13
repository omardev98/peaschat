"""
core/providers/openrouter_provider.py — OpenRouter (OpenAI-compatible).
Free models available: mistral-7b, gemma, llama3 etc.
Get key: https://openrouter.ai/keys
"""
from __future__ import annotations

import logging
import time
from typing import Generator

from core.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class OpenRouterProvider(BaseProvider):

    def __init__(
        self,
        api_key: str,
        model: str = "mistralai/mistral-7b-instruct:free",
        base_url: str | None = None,
    ) -> None:
        super().__init__(api_key, model, base_url)
        self.base_url = base_url or "https://openrouter.ai/api/v1"
        self._extra_headers = {
            "HTTP-Referer": "http://localhost:7860",
            "X-Title":      "DocAgent",
        }

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers=self._extra_headers,
        )

    def generate(self, question: str, context: str, history: list[dict]) -> str:
        msgs = self.build_messages(question, context, history)
        try:
            resp = self._client().chat.completions.create(
                model=self.model, messages=msgs, temperature=0.2
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            raise self._wrap(exc)

    def stream(
        self,
        question: str,
        context: str,
        history: list[dict],
    ) -> Generator[str, None, None]:
        msgs = self.build_messages(question, context, history)
        try:
            for chunk in self._client().chat.completions.create(
                model=self.model, messages=msgs, temperature=0.2, stream=True
            ):
                token = chunk.choices[0].delta.content or ""
                if token:
                    yield token
        except Exception as exc:
            raise self._wrap(exc)

    def test_connection(self) -> dict:
        start = time.time()
        try:
            self._client().chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            return {"ok": True, "latency_ms": int((time.time() - start) * 1000), "error": None}
        except Exception as exc:
            return {"ok": False, "latency_ms": 0, "error": str(self._wrap(exc))}

    @staticmethod
    def _wrap(exc: Exception) -> RuntimeError:
        msg = str(exc)
        if "401" in msg or "missing authentication" in msg.lower() or "invalid api key" in msg.lower():
            return RuntimeError("Invalid API key. Check Settings.")
        if "429" in msg or "rate limit" in msg.lower():
            return RuntimeError("Rate limit exceeded. Try again later.")
        if "model" in msg.lower():
            return RuntimeError("Model not available on OpenRouter. Check model name.")
        return RuntimeError(f"OpenRouter error: {exc}")
