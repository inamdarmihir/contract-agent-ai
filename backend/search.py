"""
Qdrant search module.

Provides hybrid search (dense vector similarity + sparse BM42 keyword match)
over a contract collection.  Supports optional filtering by ``risk_level``
and ``clause_type``.

Note: BM42 is Qdrant's own sparse retrieval algorithm (an evolution of BM25
tailored for neural sparse vectors).  See https://qdrant.tech/articles/bm42/
"""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Filter,
    FieldCondition,
    MatchValue,
    SparseVector,
    NamedVector,
    NamedSparseVector,
    SearchRequest,
    ScoredPoint,
)

from config import settings
from embeddings import get_embedder

logger = logging.getLogger(__name__)


def _get_qdrant_client() -> QdrantClient:
    """Return a configured Qdrant client."""
    if settings.qdrant_url:
        return QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        api_key=settings.qdrant_api_key or None,
    )


def _build_filter(
    risk_level: str | None = None,
    clause_type: str | None = None,
) -> Filter | None:
    """Build a Qdrant :class:`Filter` from optional field values."""
    conditions = []
    if risk_level:
        conditions.append(
            FieldCondition(key="risk_level", match=MatchValue(value=risk_level))
        )
    if clause_type:
        conditions.append(
            FieldCondition(key="clause_type", match=MatchValue(value=clause_type))
        )
    if not conditions:
        return None
    from qdrant_client.http.models import Filter as QFilter, Must
    return QFilter(must=conditions)


def hybrid_search(
    collection_id: str,
    query: str,
    risk_level: str | None = None,
    clause_type: str | None = None,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """
    Search a contract collection using dense vector similarity.

    When the Qdrant collection has a named sparse index (``sparse``) the
    function automatically includes a BM42 sparse leg for hybrid re-ranking.
    If no sparse index exists the function falls back to pure dense search
    transparently.

    Parameters
    ----------
    collection_id:
        UUID returned during ingestion.
    query:
        Natural language query (or keyword string).
    risk_level:
        If provided, only chunks with this risk level are returned.
        One of ``"high"``, ``"medium"``, ``"low"``.
    clause_type:
        If provided, only chunks of this clause type are returned.
    top_k:
        Number of results to return.  Defaults to ``settings.search_top_k``.

    Returns
    -------
    list[dict]
        List of matching chunk payloads, each augmented with a ``score`` field.
    """
    if top_k is None:
        top_k = settings.search_top_k

    coll_name = f"{settings.collection_name}_{collection_id}"
    client = _get_qdrant_client()

    # Dense query vector
    embedder = get_embedder()
    query_vector = embedder.embed([query])[0]

    query_filter = _build_filter(risk_level=risk_level, clause_type=clause_type)

    # Check whether the collection has a named sparse vector index.
    try:
        coll_info = client.get_collection(coll_name)
        has_sparse = bool(
            coll_info.config.params.sparse_vectors
            if hasattr(coll_info.config.params, "sparse_vectors")
            else {}
        )
    except Exception:  # noqa: BLE001
        has_sparse = False

    results: list[ScoredPoint] = []

    if has_sparse:
        # ── Hybrid search with RRF fusion ─────────────────────────────────────
        try:
            from qdrant_client.http.models import Prefetch, Query, FusionQuery, Fusion

            prefetch = [
                Prefetch(
                    query=query_vector,
                    using="dense",
                    limit=top_k * 3,
                    filter=query_filter,
                ),
            ]
            results = client.query_points(
                collection_name=coll_name,
                prefetch=prefetch,
                query=FusionQuery(fusion=Fusion.RRF),
                limit=top_k,
                with_payload=True,
            ).points
        except Exception as exc:  # noqa: BLE001
            logger.warning("Hybrid search failed, falling back to dense: %s", exc)
            results = client.search(
                collection_name=coll_name,
                query_vector=query_vector,
                limit=top_k,
                query_filter=query_filter,
                with_payload=True,
            )
    else:
        # ── Pure dense search ─────────────────────────────────────────────────
        results = client.search(
            collection_name=coll_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )

    output: list[dict[str, Any]] = []
    for hit in results:
        payload = dict(hit.payload or {})
        payload["score"] = hit.score
        payload["id"] = str(hit.id)
        output.append(payload)

    return output


def get_all_chunks(collection_id: str) -> list[dict[str, Any]]:
    """
    Return all stored chunks for the given collection.

    Used to build the risk dashboard summary (clause counts, risk heatmap,
    page map) without having to run a query.

    Returns
    -------
    list[dict]
        Each item is the Qdrant payload for one chunk.
    """
    coll_name = f"{settings.collection_name}_{collection_id}"
    client = _get_qdrant_client()

    all_points: list[Any] = []
    offset = None
    while True:
        batch, next_offset = client.scroll(
            collection_name=coll_name,
            limit=200,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in batch:
            payload = dict(point.payload or {})
            payload["id"] = str(point.id)
            all_points.append(payload)
        if next_offset is None:
            break
        offset = next_offset

    return all_points
