"""
Embedding helper module.

Provides a unified :class:`Embedder` interface that works with:

* **Local model** (default): ``BAAI/bge-base-en-v1.5`` via
  ``sentence-transformers`` — no external API call needed.
* **OpenAI model**: ``text-embedding-3-small`` — requires ``OPENAI_API_KEY``.

Switch between them by setting ``EMBEDDING_MODEL`` in the environment.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from config import settings


class Embedder(Protocol):
    """Duck-type protocol for embedders."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return a list of embedding vectors, one per input text."""
        ...


# ── Local (sentence-transformers) ────────────────────────────────────────────


class LocalEmbedder:
    """
    Embedder backed by a local HuggingFace model via ``sentence-transformers``.

    The model is loaded once and cached for the lifetime of the process.
    """

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore

        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of text strings and return their float vectors."""
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return [e.tolist() for e in embeddings]


# ── OpenAI embeddings ────────────────────────────────────────────────────────


class OpenAIEmbedder:
    """
    Embedder backed by OpenAI's ``text-embedding-3-small`` (or similar).

    Requires ``OPENAI_API_KEY`` to be set.
    """

    def __init__(self, model_name: str) -> None:
        import openai  # type: ignore

        if not settings.openai_api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY must be set when using OpenAI embeddings."
            )
        self._client = openai.OpenAI(api_key=settings.openai_api_key)
        self._model = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of text strings using the OpenAI Embeddings API."""
        response = self._client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in response.data]


# ── Factory ───────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """
    Return the appropriate embedder based on ``EMBEDDING_MODEL`` config.

    The embedder is instantiated once and cached for the process lifetime.
    """
    model = settings.embedding_model
    if model.startswith("text-embedding"):
        return OpenAIEmbedder(model)
    return LocalEmbedder(model)
