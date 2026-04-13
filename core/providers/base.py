"""
core/providers/base.py — Abstract base class for all AI providers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generator


class BaseProvider(ABC):

    SYSTEM_PROMPT = (
        "You are a helpful AI assistant. "
        "When document context is provided, answer using that context. "
        "When no document context is provided, answer from your general knowledge. "
        "If the user writes in French or Arabic, reply in that language."
    )

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
    ) -> None:
        self.api_key  = api_key
        self.model    = model
        self.base_url = base_url

    @abstractmethod
    def generate(
        self,
        question: str,
        context: str,
        history: list[dict],
    ) -> str:
        """Return the full answer as a string."""

    @abstractmethod
    def stream(
        self,
        question: str,
        context: str,
        history: list[dict],
    ) -> Generator[str, None, None]:
        """Yield answer tokens one by one."""

    @abstractmethod
    def test_connection(self) -> dict:
        """Return {"ok": bool, "latency_ms": int, "error": str|None}."""

    def build_messages(
        self,
        question: str,
        context: str,
        history: list[dict],
    ) -> list[dict]:
        """Build an OpenAI-compatible messages list."""
        msgs: list[dict] = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        if context:
            msgs.append({"role": "user",      "content": f"Context from documents:\n\n{context}"})
            msgs.append({"role": "assistant", "content": "Understood. I will use this context to answer."})
        msgs += history[-6:]          # last 3 conversation turns
        msgs.append({"role": "user", "content": question})
        return msgs
