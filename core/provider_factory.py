"""
core/provider_factory.py — Reads the active provider from DB, returns the adapter.

FREE API REFERENCE:
  Provider        Free Tier                  Get Key URL
  --------------- -------------------------- -----------------------------------------
  Ollama          Unlimited, local only      https://ollama.com  (install desktop app)
  Groq            14,400 req/day, fastest    https://console.groq.com/keys
  OpenRouter      Free models available      https://openrouter.ai/keys
  Google Gemini   15 RPM, 1M TPM free        https://aistudio.google.com/app/apikey
  HuggingFace     Rate-limited inference     https://huggingface.co/settings/tokens
  Mistral AI      Free trial credits         https://console.mistral.ai/api-keys
  Together AI     $1 free credit             https://api.together.ai/settings/api-keys
  Cohere          1000 req/month trial       https://dashboard.cohere.com/api-keys
  Perplexity      Paid only ($5 min)         https://www.perplexity.ai/settings/api

Recommended FREE stack for development:
  Primary  : Groq  (fastest, generous free tier)
  Fallback : Ollama (always works, no key needed)
  RAG docs : OpenRouter (free mistral-7b works well for RAG)
"""
from __future__ import annotations

import logging

import database as db
from core.providers.base             import BaseProvider
from core.providers.ollama_provider  import OllamaProvider
from core.providers.groq_provider    import GroqProvider
from core.providers.openrouter_provider import OpenRouterProvider
from core.providers.gemini_provider  import GeminiProvider
from core.providers.huggingface_provider import HuggingFaceProvider
from core.providers.mistral_provider import MistralProvider
from core.providers.together_provider import TogetherProvider
from core.providers.cohere_provider  import CohereProvider
from core.providers.perplexity_provider import PerplexityProvider

logger = logging.getLogger(__name__)

PROVIDER_MAP: dict[str, type[BaseProvider]] = {
    "ollama":      OllamaProvider,
    "groq":        GroqProvider,
    "openrouter":  OpenRouterProvider,
    "gemini":      GeminiProvider,
    "huggingface": HuggingFaceProvider,
    "mistral":     MistralProvider,
    "together":    TogetherProvider,
    "cohere":      CohereProvider,
    "perplexity":  PerplexityProvider,
}

# Fall back to Ollama when the active cloud provider has no API key set.
FALLBACK_TO_OLLAMA: bool = True


def get_provider(slug: str | None = None) -> BaseProvider:
    """
    Instantiate and return a provider.

    Args:
        slug: If given, use this provider regardless of active setting
              (used by the /test endpoint).
              If None, use the active provider from the database.
    """
    if slug:
        config = db.get_provider_by_slug(slug)
        if not config:
            raise ValueError(f"Provider '{slug}' not found.")
    else:
        config = db.get_active_provider()
        if not config:
            raise ValueError("No active provider configured. Go to /settings.")

    cls = PROVIDER_MAP.get(config["slug"])
    if not cls:
        raise ValueError(f"Unknown provider slug: '{config['slug']}'")

    return cls(
        api_key=config.get("api_key") or "",
        model=config["model"],
        base_url=config.get("base_url"),
    )


def get_provider_with_fallback() -> tuple[BaseProvider, str]:
    """
    Return (provider_instance, slug).

    If FALLBACK_TO_OLLAMA is True and the active cloud provider has no key,
    automatically falls back to the Ollama provider from the database.
    """
    config = db.get_active_provider()

    if not config:
        if FALLBACK_TO_OLLAMA:
            logger.warning("No active provider — falling back to Ollama.")
            ollama_cfg = db.get_provider_by_slug("ollama") or {}
            return (
                OllamaProvider(
                    api_key="",
                    model=ollama_cfg.get("model", "llama3"),
                    base_url=ollama_cfg.get("base_url"),
                ),
                "ollama",
            )
        raise ValueError("No active provider configured. Go to /settings.")

    slug = config["slug"]

    # Non-Ollama provider without a key → fall back silently
    if FALLBACK_TO_OLLAMA and slug != "ollama" and not config.get("api_key"):
        logger.warning(
            "Provider '%s' has no API key — falling back to Ollama.", slug
        )
        ollama_cfg = db.get_provider_by_slug("ollama") or {}
        return (
            OllamaProvider(
                api_key="",
                model=ollama_cfg.get("model", "llama3"),
                base_url=ollama_cfg.get("base_url"),
            ),
            "ollama",
        )

    return get_provider(), slug
