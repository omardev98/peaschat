"""
core/providers/huggingface_provider.py — HuggingFace Inference API.
Free tier: rate-limited. Get key: https://huggingface.co/settings/tokens
Note: HF Inference API is text-in/text-out; no true token streaming.
"""
from __future__ import annotations

import logging
import time
from typing import Generator

import requests

from core.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class HuggingFaceProvider(BaseProvider):

    def __init__(
        self,
        api_key: str,
        model: str = "HuggingFaceH4/zephyr-7b-beta",
        base_url: str | None = None,
    ) -> None:
        super().__init__(api_key, model, base_url)
        self.base_url = (base_url or "https://api-inference.huggingface.co").rstrip("/")

    def _build_prompt(self, question: str, context: str, history: list[dict]) -> str:
        lines = [
            f"<|system|>\n{self.SYSTEM_PROMPT}</s>",
            f"<|user|>\nContext from documents:\n{context}</s>",
            "<|assistant|>\nUnderstood. I will answer only from this context.</s>",
        ]
        for m in history[-6:]:
            role = "user" if m["role"] == "user" else "assistant"
            lines.append(f"<|{role}|>\n{m['content']}</s>")
        lines.append(f"<|user|>\n{question}</s>")
        lines.append("<|assistant|>")
        return "\n".join(lines)

    def _call(self, prompt: str, max_new_tokens: int = 512) -> str:
        url     = f"{self.base_url}/models/{self.model}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "inputs":     prompt,
            "parameters": {"max_new_tokens": max_new_tokens, "return_full_text": False},
        }
        r = requests.post(url, headers=headers, json=payload, timeout=60)

        if r.status_code == 401:
            raise RuntimeError("Invalid HuggingFace token. Check Settings.")
        if r.status_code == 429:
            raise RuntimeError("HuggingFace rate limit exceeded. Try again later.")
        if r.status_code == 503:
            raise RuntimeError("HuggingFace model is loading. Please try again in ~30s.")
        r.raise_for_status()

        result = r.json()
        if isinstance(result, list) and result:
            return (result[0].get("generated_text") or "").strip()
        return str(result).strip()

    def generate(self, question: str, context: str, history: list[dict]) -> str:
        try:
            return self._call(self._build_prompt(question, context, history))
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"HuggingFace error: {exc}") from exc

    def stream(
        self,
        question: str,
        context: str,
        history: list[dict],
    ) -> Generator[str, None, None]:
        # HF Inference API has no true streaming — yield full response as one token
        yield self.generate(question, context, history)

    def test_connection(self) -> dict:
        start = time.time()
        try:
            self._call("Hello", max_new_tokens=1)
            return {"ok": True, "latency_ms": int((time.time() - start) * 1000), "error": None}
        except RuntimeError as exc:
            return {"ok": False, "latency_ms": 0, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "latency_ms": 0, "error": f"HuggingFace error: {exc}"}
