"""
core/providers/gemini_provider.py — Google Gemini provider (REST API).

Uses the Gemini REST API directly via `requests` — no SDK needed.
Works with Python 3.7+.

Free tier: 15 RPM, 1M TPM.
Get key:   https://aistudio.google.com/app/apikey

REST docs: https://ai.google.dev/api/rest
"""
from __future__ import annotations

import json
import logging
import time
from typing import Generator

import requests

from core.providers.base import BaseProvider

logger = logging.getLogger(__name__)

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(BaseProvider):

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        base_url: str | None = None,
    ) -> None:
        super().__init__(api_key, model, base_url)

    # ── Internal helpers ───────────────────────────────────────────────────

    def _url(self, action: str, stream: bool = False) -> str:
        url = f"{_BASE}/{self.model}:{action}?key={self.api_key}"
        if stream:
            url += "&alt=sse"
        return url

    def _body(self, prompt: str) -> dict:
        return {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 8192,
            },
        }

    def _build_prompt(self, question: str, context: str, history: list) -> str:
        lines = [self.SYSTEM_PROMPT, ""]
        if context:
            lines += [f"Context from documents:\n{context}", ""]
        for m in history[-6:]:
            role = "User" if m["role"] == "user" else "Assistant"
            lines.append(f"{role}: {m['content']}")
        lines.append(f"User: {question}")
        lines.append("Assistant:")
        return "\n".join(lines)

    def _raise_for_error(self, resp: requests.Response) -> None:
        if resp.status_code == 200:
            return
        try:
            detail = resp.json().get("error", {})
            msg = detail.get("message", resp.text)
            code = detail.get("code", resp.status_code)
        except Exception:
            msg = resp.text
            code = resp.status_code
        raise RuntimeError(self._classify(msg, code))

    @staticmethod
    def _classify(msg: str, code: int = 0) -> str:
        m = msg.lower()
        if code in (401, 403) or any(k in m for k in ("api key", "api_key", "credential", "invalid")):
            return "Invalid Gemini API key. Check Settings."
        if code == 429 or any(k in m for k in ("quota", "rate limit", "resource_exhausted")):
            return "Gemini rate limit exceeded. Try again later."
        if code == 404 or any(k in m for k in ("not found", "does not exist")):
            return (
                "Gemini model not found. "
                "Change model to 'gemini-2.0-flash' or 'gemini-2.0-flash-lite' in Settings."
            )
        return f"Gemini error {code}: {msg}"

    # ── BaseProvider interface ─────────────────────────────────────────────

    def generate(self, question: str, context: str, history: list) -> str:
        prompt = self._build_prompt(question, context, history)
        try:
            resp = requests.post(
                self._url("generateContent"),
                json=self._body(prompt),
                timeout=60,
            )
            self._raise_for_error(resp)
            data = resp.json()
            return (
                data["candidates"][0]["content"]["parts"][0]["text"]
            ).strip()
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Gemini error: {exc}") from exc

    def stream(
        self,
        question: str,
        context: str,
        history: list,
    ) -> Generator[str, None, None]:
        prompt = self._build_prompt(question, context, history)
        try:
            resp = requests.post(
                self._url("streamGenerateContent", stream=True),
                json=self._body(prompt),
                stream=True,
                timeout=120,
            )
            self._raise_for_error(resp)

            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                # SSE lines start with "data: "
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if payload in ("", "[DONE]"):
                    continue
                try:
                    chunk = json.loads(payload)
                    text = (
                        chunk.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                    )
                    if text:
                        yield text
                except (json.JSONDecodeError, IndexError, KeyError):
                    continue
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Gemini stream error: {exc}") from exc

    def test_connection(self) -> dict:
        start = time.time()
        try:
            resp = requests.post(
                self._url("generateContent"),
                json=self._body("hi"),
                timeout=15,
            )
            self._raise_for_error(resp)
            return {
                "ok": True,
                "latency_ms": int((time.time() - start) * 1000),
                "error": None,
            }
        except RuntimeError as exc:
            return {"ok": False, "latency_ms": 0, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "latency_ms": 0, "error": f"Gemini error: {exc}"}
