"""
vector_store.py
───────────────
Manages per-document FAISS indexes.
Uses our custom OllamaEmbeddings (calls nomic-embed-text locally).

Layout on disk:
    data/<document_id>/index.faiss
    data/<document_id>/index.pkl
"""

import logging
from pathlib import Path
from typing import List, Optional

from langchain_community.vectorstores import FAISS

from config import DATA_DIR, TOP_K_CHUNKS
from app.services.embeddings import OllamaEmbeddings

logger = logging.getLogger(__name__)

# Singleton — one embedding model instance per process
_embeddings: Optional[OllamaEmbeddings] = None


def _get_embeddings() -> OllamaEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OllamaEmbeddings()
        logger.info(
            "Ollama embeddings initialised (model=%s)",
            _embeddings.model,
        )
    return _embeddings


def _index_dir(document_id: str) -> Path:
    path = Path(DATA_DIR) / document_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_exists(document_id: str) -> bool:
    d = _index_dir(document_id)
    return (d / "index.faiss").exists() and (d / "index.pkl").exists()


# ── Public API ─────────────────────────────────────────────────────────────

def build_and_save(document_id: str, chunks: List[str]) -> None:
    """Embed chunks and persist FAISS index for document_id."""
    if not chunks:
        raise ValueError("Cannot index an empty chunk list.")

    emb = _get_embeddings()
    logger.info("Building FAISS index for '%s' (%d chunks)…", document_id, len(chunks))

    store = FAISS.from_texts(chunks, emb)
    store.save_local(str(_index_dir(document_id)))
    logger.info("FAISS index saved for '%s'", document_id)


def load_store(document_id: str) -> FAISS:
    """Load and return the FAISS store for document_id."""
    if not _index_exists(document_id):
        raise FileNotFoundError(
            f"No vector index found for document_id='{document_id}'. "
            "Upload the document first."
        )
    store = FAISS.load_local(
        str(_index_dir(document_id)),
        _get_embeddings(),
        allow_dangerous_deserialization=True,
    )
    logger.info("Loaded FAISS index for '%s'", document_id)
    return store


def similarity_search(document_id: str, query: str) -> List[str]:
    """Return the top-K most relevant chunks for query."""
    store = load_store(document_id)
    docs  = store.similarity_search(query, k=TOP_K_CHUNKS)
    chunks = [d.page_content for d in docs]
    logger.info(
        "Similarity search '%s': %d chunk(s) returned", document_id, len(chunks)
    )
    return chunks


def list_documents() -> List[str]:
    """Return all document IDs that have a persisted FAISS index."""
    p = Path(DATA_DIR)
    if not p.exists():
        return []
    return [
        d.name for d in p.iterdir()
        if d.is_dir() and (d / "index.faiss").exists()
    ]
