"""
database.py - SQLite provider configuration store
==================================================
DB file: ./data/docagent.db
All provider configs (API keys, models, active state) live here.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_PATH: Path | None = None

# ── Default provider seed data ─────────────────────────────────────────────
# Free-tier notes are preserved as comments.

_DEFAULT_PROVIDERS: list[dict] = [
    # Ollama: unlimited, local only, no key needed
    {
        "name": "Ollama (local)",
        "slug": "ollama",
        "api_key": None,
        "base_url": "http://localhost:11434",
        "model": "llama3",
        "is_active": 1,
        "is_enabled": 1,
    },
    # Groq: free tier — 14,400 req/day, fastest cloud inference
    {
        "name": "Groq",
        "slug": "groq",
        "api_key": None,
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.1-8b-instant",
        "is_active": 0,
        "is_enabled": 1,
    },
    # OpenRouter: free models available (mistral-7b, gemma, llama3 etc.)
    {
        "name": "OpenRouter",
        "slug": "openrouter",
        "api_key": None,
        "base_url": "https://openrouter.ai/api/v1",
        "model": "mistralai/mistral-7b-instruct:free",
        "is_active": 0,
        "is_enabled": 1,
    },
    # Google Gemini: 15 RPM, 1M TPM free with Google API key
    {
        "name": "Google Gemini",
        "slug": "gemini",
        "api_key": None,
        "base_url": None,
        "model": "gemini-2.0-flash",
        "is_active": 0,
        "is_enabled": 1,
    },
    # HuggingFace: free inference API (rate limited)
    {
        "name": "HuggingFace",
        "slug": "huggingface",
        "api_key": None,
        "base_url": "https://api-inference.huggingface.co",
        "model": "HuggingFaceH4/zephyr-7b-beta",
        "is_active": 0,
        "is_enabled": 1,
    },
    # Mistral AI: free trial credits
    {
        "name": "Mistral AI",
        "slug": "mistral",
        "api_key": None,
        "base_url": "https://api.mistral.ai/v1",
        "model": "mistral-small-latest",
        "is_active": 0,
        "is_enabled": 1,
    },
    # Together AI: $1 free credit on signup
    {
        "name": "Together AI",
        "slug": "together",
        "api_key": None,
        "base_url": "https://api.together.xyz/v1",
        "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "is_active": 0,
        "is_enabled": 1,
    },
    # Cohere: 1000 req/month trial
    {
        "name": "Cohere",
        "slug": "cohere",
        "api_key": None,
        "base_url": "https://api.cohere.ai/v1",
        "model": "command-r",
        "is_active": 0,
        "is_enabled": 1,
    },
    # Perplexity: paid only ($5 minimum)
    {
        "name": "Perplexity",
        "slug": "perplexity",
        "api_key": None,
        "base_url": "https://api.perplexity.ai",
        "model": "sonar-small-online",
        "is_active": 0,
        "is_enabled": 1,
    },
]


def _db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        data_dir = Path(__file__).parent / "data"
        data_dir.mkdir(exist_ok=True)
        _DB_PATH = data_dir / "docagent.db"
    return _DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


# ── Init ───────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create tables and seed default provider rows if missing."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS providers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                slug        TEXT    UNIQUE NOT NULL,
                api_key     TEXT,
                base_url    TEXT,
                model       TEXT    NOT NULL,
                is_active   INTEGER DEFAULT 0,
                is_enabled  INTEGER DEFAULT 1,
                created_at  TEXT    DEFAULT (datetime('now')),
                updated_at  TEXT    DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT    NOT NULL,
                key_hash     TEXT    NOT NULL UNIQUE,
                key_prefix   TEXT    NOT NULL,
                is_active    INTEGER DEFAULT 1,
                created_at   TEXT    DEFAULT (datetime('now')),
                last_used_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS request_logs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint     TEXT    NOT NULL DEFAULT '/api/ask',
                question     TEXT    NOT NULL,
                answer       TEXT,
                provider     TEXT,
                model        TEXT,
                file_name    TEXT,
                has_file     INTEGER DEFAULT 0,
                history_len  INTEGER DEFAULT 0,
                duration_ms  INTEGER,
                status       TEXT    DEFAULT 'ok',
                error        TEXT,
                ip           TEXT,
                created_at   TEXT    DEFAULT (datetime('now'))
            )
        """)
        for p in _DEFAULT_PROVIDERS:
            exists = conn.execute(
                "SELECT id FROM providers WHERE slug = ?", (p["slug"],)
            ).fetchone()
            if not exists:
                conn.execute(
                    """INSERT INTO providers
                       (name, slug, api_key, base_url, model, is_active, is_enabled)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (p["name"], p["slug"], p["api_key"], p["base_url"],
                     p["model"], p["is_active"], p["is_enabled"]),
                )
        conn.commit()
    logger.info("Database ready: %s", _db_path())


# ── Queries ────────────────────────────────────────────────────────────────

def get_all_providers() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM providers ORDER BY id").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_provider_by_slug(slug: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM providers WHERE slug = ?", (slug,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_active_provider() -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM providers WHERE is_active = 1 LIMIT 1"
        ).fetchone()
    return _row_to_dict(row) if row else None


def upsert_provider(
    slug: str,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> dict:
    """Update an existing provider. Returns the updated row."""
    with _connect() as conn:
        if not conn.execute(
            "SELECT id FROM providers WHERE slug = ?", (slug,)
        ).fetchone():
            raise ValueError(f"Provider '{slug}' not found.")

        updates: list[str] = ["updated_at = datetime('now')"]
        params: list[Any] = []

        if api_key is not None:
            updates.append("api_key = ?")
            params.append(api_key.strip() if api_key.strip() else None)
        if model is not None and model.strip():
            updates.append("model = ?")
            params.append(model.strip())
        if base_url is not None:
            updates.append("base_url = ?")
            params.append(base_url.strip() if base_url.strip() else None)

        params.append(slug)
        conn.execute(
            f"UPDATE providers SET {', '.join(updates)} WHERE slug = ?",
            params,
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM providers WHERE slug = ?", (slug,)
        ).fetchone()
    return _row_to_dict(row)


def set_active_provider(slug: str) -> None:
    """Set exactly one provider as active; clears all others."""
    with _connect() as conn:
        if not conn.execute(
            "SELECT id FROM providers WHERE slug = ?", (slug,)
        ).fetchone():
            raise ValueError(f"Provider '{slug}' not found.")
        conn.execute("UPDATE providers SET is_active = 0")
        conn.execute(
            "UPDATE providers SET is_active = 1, updated_at = datetime('now') "
            "WHERE slug = ?",
            (slug,),
        )
        conn.commit()
    logger.info("Active provider -> '%s'", slug)


def delete_provider(slug: str) -> None:
    """
    Reset a provider's api_key to NULL and deactivate it.
    Does not remove the row so the UI always shows all providers.
    """
    with _connect() as conn:
        active = conn.execute(
            "SELECT slug FROM providers WHERE is_active = 1"
        ).fetchone()
        if active and active["slug"] == slug:
            raise ValueError("Cannot reset the currently active provider.")
        conn.execute(
            "UPDATE providers SET api_key = NULL, is_active = 0, "
            "updated_at = datetime('now') WHERE slug = ?",
            (slug,),
        )
        conn.commit()
    logger.info("Provider '%s' reset to defaults.", slug)


# ── API Key management ─────────────────────────────────────────────────────

def _hash_key(raw_key: str) -> str:
    """Return SHA-256 hex digest of a raw API key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def create_api_key(name: str) -> dict:
    """
    Generate a new API key, store its SHA-256 hash, return the raw key ONCE.
    Format: lc_<48 URL-safe base64 chars>
    """
    raw_key = "lc_" + secrets.token_urlsafe(36)  # 36 bytes → 48 base64 chars
    key_hash = _hash_key(raw_key)
    key_prefix = raw_key[:10]  # "lc_" + 7 chars — enough to identify

    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO api_keys (name, key_hash, key_prefix) VALUES (?, ?, ?)",
            (name.strip(), key_hash, key_prefix),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM api_keys WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()

    result = _row_to_dict(row)
    result["key"] = raw_key   # raw key returned ONCE — never stored
    del result["key_hash"]    # never expose the hash
    return result


def list_api_keys() -> list[dict]:
    """Return all API keys without the hash field."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, name, key_prefix, is_active, created_at, last_used_at "
            "FROM api_keys ORDER BY id DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def validate_api_key(raw_key: str) -> bool:
    """
    Hash the incoming key, look it up, check is_active=1,
    update last_used_at on success. Return True/False.
    """
    if not raw_key or not raw_key.startswith("lc_"):
        return False
    key_hash = _hash_key(raw_key)
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, is_active FROM api_keys WHERE key_hash = ?", (key_hash,)
        ).fetchone()
        if not row or not row["is_active"]:
            return False
        conn.execute(
            "UPDATE api_keys SET last_used_at = datetime('now') WHERE id = ?",
            (row["id"],),
        )
        conn.commit()
    return True


def revoke_api_key(key_id: int) -> bool:
    """Set is_active=0 for the given key id. Returns True if found."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE api_keys SET is_active = 0 WHERE id = ?", (key_id,)
        )
        conn.commit()
    return cur.rowcount > 0


def delete_api_key(key_id: int) -> bool:
    """Permanently delete a key. Returns True if found."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        conn.commit()
    return cur.rowcount > 0


# ── Request logs ───────────────────────────────────────────────────────────

def insert_log(
    question:    str,
    answer:      str | None  = None,
    provider:    str | None  = None,
    model:       str | None  = None,
    file_name:   str | None  = None,
    has_file:    bool        = False,
    history_len: int         = 0,
    duration_ms: int | None  = None,
    status:      str         = "ok",
    error:       str | None  = None,
    ip:          str | None  = None,
    endpoint:    str         = "/api/ask",
) -> int:
    """Insert one log row. Returns the new row id."""
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO request_logs
               (endpoint, question, answer, provider, model,
                file_name, has_file, history_len, duration_ms,
                status, error, ip)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (endpoint, question[:2000], (answer or "")[:4000],
             provider, model, file_name,
             1 if has_file else 0, history_len,
             duration_ms, status, error, ip),
        )
        conn.commit()
    return cur.lastrowid


def get_logs(
    limit:    int = 200,
    offset:   int = 0,
    search:   str = "",
    endpoint: str = "",
) -> tuple[list[dict], int]:
    """Return (rows, total_count). Rows ordered newest first."""
    with _connect() as conn:
        conditions = []
        params: list = []

        if search:
            like = f"%{search}%"
            conditions.append(
                "(question LIKE ? OR answer LIKE ? OR provider LIKE ? OR endpoint LIKE ?)"
            )
            params.extend([like, like, like, like])

        if endpoint:
            conditions.append("endpoint = ?")
            params.append(endpoint)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        total = conn.execute(
            f"SELECT COUNT(*) FROM request_logs {where}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"SELECT * FROM request_logs {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    return [_row_to_dict(r) for r in rows], total


def delete_log(log_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM request_logs WHERE id = ?", (log_id,))
        conn.commit()
    return cur.rowcount > 0


def clear_logs() -> int:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM request_logs")
        conn.commit()
    return cur.rowcount
