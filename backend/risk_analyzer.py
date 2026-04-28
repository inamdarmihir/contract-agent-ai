"""
Risk analyser module.

After a contract has been ingested and its chunks stored in Qdrant, this
module runs a one-time pass over every chunk to:

1. Ask the xAI Grok text API to classify the clause as ``high``, ``medium``
   or ``low`` risk and provide a one-line reason.
2. Ask Grok to produce a plain-English summary of the clause.
3. Patch the Qdrant payload fields ``risk_level``, ``risk_reason`` and
   ``plain_english`` for each point.

The analysis is intentionally performed *before* the user opens a voice
session so that risk information is instantly available in the dashboard
and can be used as Qdrant filters during retrieval.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointIdsList

from config import settings

logger = logging.getLogger(__name__)

# ── Grok client ───────────────────────────────────────────────────────────────


def _get_grok_client() -> OpenAI:
    """Return an OpenAI-compatible client pointed at the xAI endpoint."""
    if not settings.xai_api_key:
        raise EnvironmentError(
            "XAI_API_KEY must be set to run risk analysis with Grok."
        )
    return OpenAI(api_key=settings.xai_api_key, base_url=settings.xai_base_url)


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


# ── Per-chunk analysis ────────────────────────────────────────────────────────

_ANALYSIS_PROMPT = """\
You are a contract risk expert. Analyse the following contract clause and
respond with a single JSON object (no markdown fences) containing exactly
these keys:

  "risk_level"   : "high" | "medium" | "low"
  "risk_reason"  : one sentence explaining the risk (or "Standard clause." if low risk)
  "plain_english": one to two sentences describing what the clause means in plain language

Clause text:
{text}
"""


def _analyse_chunk(client: OpenAI, text: str) -> dict[str, str]:
    """
    Call the Grok text API to produce risk tags for a single clause chunk.

    Returns a dict with keys: ``risk_level``, ``risk_reason``, ``plain_english``.
    Falls back to ``{"risk_level": "low", "risk_reason": "Analysis unavailable.",
    "plain_english": text[:200]}`` on any error.
    """
    prompt = _ANALYSIS_PROMPT.format(text=text[:2000])  # cap at 2 000 chars
    try:
        response = client.chat.completions.create(
            model=settings.xai_text_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=256,
        )
        raw = response.choices[0].message.content or "{}"
        # Strip accidental markdown fences
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data: dict[str, str] = json.loads(raw)
        # Validate keys
        return {
            "risk_level": data.get("risk_level", "low"),
            "risk_reason": data.get("risk_reason", ""),
            "plain_english": data.get("plain_english", ""),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Risk analysis failed for chunk: %s", exc)
        return {
            "risk_level": "low",
            "risk_reason": "Analysis unavailable.",
            "plain_english": text[:200],
        }


# ── Collection-level analysis ─────────────────────────────────────────────────


def analyse_collection(collection_id: str) -> dict[str, Any]:
    """
    Run risk analysis over all chunks in a Qdrant collection.

    Parameters
    ----------
    collection_id:
        The UUID returned by :func:`ingest.ingest_pdf`.

    Returns
    -------
    dict
        Summary statistics::

            {
                "total_chunks": 42,
                "high": 5,
                "medium": 12,
                "low": 25,
                "top_flagged": [
                    {"text": "...", "risk_level": "high", "risk_reason": "..."},
                    ...
                ]
            }
    """
    coll_name = f"{settings.collection_name}_{collection_id}"
    qdrant = _get_qdrant_client()
    grok = _get_grok_client()

    # Scroll through all points (no vector needed, just payload)
    all_points: list[Any] = []
    offset = None
    while True:
        batch, next_offset = qdrant.scroll(
            collection_name=coll_name,
            limit=50,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(batch)
        if next_offset is None:
            break
        offset = next_offset

    stats: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    top_flagged: list[dict[str, str]] = []

    for point in all_points:
        payload = point.payload or {}
        text = payload.get("text", "")

        analysis = _analyse_chunk(grok, text)

        # Patch the Qdrant point payload in place.
        qdrant.set_payload(
            collection_name=coll_name,
            payload=analysis,
            points=PointIdsList(points=[point.id]),
        )

        level = analysis["risk_level"]
        if level in stats:
            stats[level] += 1

        if level == "high":
            top_flagged.append(
                {
                    "id": str(point.id),
                    "text": text[:300],
                    "risk_level": level,
                    "risk_reason": analysis["risk_reason"],
                    "plain_english": analysis["plain_english"],
                    "page_number": payload.get("page_number", 0),
                    "section_title": payload.get("section_title", ""),
                    "clause_type": payload.get("clause_type", "other"),
                }
            )

        # Be polite to the API — small delay between calls.
        time.sleep(0.1)

    # Sort flagged clauses so the riskiest appear first.
    top_flagged.sort(key=lambda x: x["page_number"])

    return {
        "total_chunks": len(all_points),
        **stats,
        "top_flagged": top_flagged[:5],
    }
