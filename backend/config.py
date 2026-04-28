"""
Configuration module for the Contract Voice Agent backend.

Loads environment variables and exposes typed settings used throughout
the application.  All credentials are sourced from the environment —
never hard-coded.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── xAI / Grok ────────────────────────────────────────────────────────────
    xai_api_key: str = ""
    xai_base_url: str = "https://api.x.ai/v1"
    xai_text_model: str = "grok-3-mini"
    xai_voice_model: str = "grok-voice-think-fast-1.0"
    xai_realtime_url: str = "wss://api.x.ai/v1/realtime"

    # ── OpenAI (optional — only needed when EMBEDDING_MODEL=text-embedding-3-small) ─
    openai_api_key: str = ""

    # ── Embedding model ───────────────────────────────────────────────────────
    # Set to "BAAI/bge-base-en-v1.5" for fully local inference (default),
    # or "text-embedding-3-small" to use OpenAI embeddings.
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dim: int = 768  # bge-base produces 768-dim; OpenAI small is 1536

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""          # Required only for Qdrant Cloud
    qdrant_url: str = ""              # Override full URL, e.g. https://<cluster>.qdrant.io
    collection_name: str = "contracts"

    # ── Chunking ──────────────────────────────────────────────────────────────
    chunk_size: int = 512             # tokens per chunk
    chunk_overlap: int = 64           # token overlap between consecutive chunks

    # ── Search ────────────────────────────────────────────────────────────────
    search_top_k: int = 3             # number of chunks returned per query

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # ── Misc ──────────────────────────────────────────────────────────────────
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached singleton settings object."""
    return Settings()


# Convenience alias used by other modules
settings = get_settings()
