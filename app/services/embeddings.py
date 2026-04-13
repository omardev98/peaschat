"""
embeddings.py
─────────────
Custom Ollama embeddings using direct HTTP calls.
No langchain-ollama package required — works with any Ollama version.

Implements the duck-typed interface expected by langchain's FAISS:
  .embed_documents(texts)  -> List[List[float]]
  .embed_query(text)       -> List[float]
"""

import logging
from typing import List

import requests

from config import OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL

logger = logging.getLogger(__name__)

try:
    from langchain_core.embeddings import Embeddings as _Base
except ImportError:
    _Base = object


class OllamaEmbeddings(_Base):
    """
    Generates embeddings by calling Ollama's local embedding endpoint.
    Supports both the new /api/embed (Ollama >=0.1.26) and
    the legacy /api/embeddings endpoint automatically.
    """

    def __init__(
        self,
        model:    str = OLLAMA_EMBED_MODEL,
        base_url: str = OLLAMA_BASE_URL,
    ):
        self.model    = model
        self.base_url = base_url.rstrip("/")

    # ── LangChain FAISS interface ─────────────────────────────────────────

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of document chunks."""
        embeddings = []
        for i, text in enumerate(texts, 1):
            logger.debug("Embedding chunk %d/%d …", i, len(texts))
            embeddings.append(self._embed_one(text))
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string."""
        return self._embed_one(text)

    # ── Internal ──────────────────────────────────────────────────────────

    def _embed_one(self, text: str) -> List[float]:
        """
        Try the new /api/embed endpoint first (Ollama >=0.1.26).
        Fall back to the legacy /api/embeddings endpoint.
        """
        # ── New API: POST /api/embed ───────────────────────────────────────
        try:
            r = requests.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": text},
                timeout=60,
            )
            if r.status_code == 200:
                data = r.json()
                # New API returns {"embeddings": [[...float...]]}
                if "embeddings" in data and data["embeddings"]:
                    return data["embeddings"][0]
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Make sure Ollama is running:  ollama serve"
            ) from exc
        except Exception:
            pass  # fall through to legacy endpoint

        # ── Legacy API: POST /api/embeddings ──────────────────────────────
        try:
            r = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=60,
            )
            r.raise_for_status()
            data = r.json()
            # Legacy API returns {"embedding": [...float...]}
            if "embedding" in data:
                return data["embedding"]
            raise RuntimeError(f"Unexpected Ollama response: {data}")
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Make sure Ollama is running:  ollama serve"
            ) from exc
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Embedding failed: {exc}") from exc
