"""
xAI voice session management.

Handles:
* Generating short-lived ephemeral tokens so the browser can connect
  directly to the xAI realtime WebSocket without exposing the master API key.
* Providing the system prompt and session configuration for the voice agent.
* Proxying the WebSocket connection when a direct browser-to-xAI path is
  not available (e.g., behind a firewall).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a contract analysis assistant. Your job is to help the user understand \
the contract they have uploaded.

Rules:
- Always answer in plain, non-legal language anyone can understand
- When a clause is risky, say so clearly and explain exactly why before \
explaining what it means
- Never minimize risk. If something is unusual or one-sided, say that directly
- When asked about a specific clause or term, retrieve the exact text from \
the contract before answering
- Proactively mention related risky clauses the user may not have asked \
about yet
- If a term is standard and unproblematic, say that too — not everything needs alarm
- Keep responses concise for voice: 3-4 sentences max unless the user asks \
for more detail
- If you don't find the term in the contract, say so rather than guessing
"""


# ── Session configuration ─────────────────────────────────────────────────────


def build_session_config(collection_id: str) -> dict[str, Any]:
    """
    Return the session configuration payload sent to the xAI realtime API.

    The ``file_search`` tool is wired to the caller's Qdrant collection so the
    voice model can retrieve relevant clauses before answering.

    Parameters
    ----------
    collection_id:
        UUID of the contract's Qdrant collection.
    """
    return {
        "model": settings.xai_voice_model,
        "modalities": ["text", "audio"],
        "instructions": SYSTEM_PROMPT,
        "voice": "alloy",
        "input_audio_format": "pcm16",
        "output_audio_format": "pcm16",
        "input_audio_transcription": {"model": "whisper-1"},
        "turn_detection": {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 500,
        },
        "tools": [
            {
                "type": "function",
                "name": "search_contract",
                "description": (
                    "Search the uploaded contract for clauses relevant to the "
                    "user's question.  Always call this before answering."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query derived from the user's question.",
                        },
                        "risk_level": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": (
                                "Filter by risk level. Use 'high' when the user "
                                "asks what to worry about."
                            ),
                        },
                        "clause_type": {
                            "type": "string",
                            "enum": [
                                "liability",
                                "termination",
                                "payment",
                                "IP",
                                "confidentiality",
                                "auto-renewal",
                                "indemnification",
                                "other",
                            ],
                            "description": "Filter by clause type.",
                        },
                    },
                    "required": ["query"],
                },
            }
        ],
        "tool_choice": "auto",
        "temperature": 0.8,
        "metadata": {"collection_id": collection_id},
    }


# ── Ephemeral token ───────────────────────────────────────────────────────────


async def create_ephemeral_token(collection_id: str) -> dict[str, Any]:
    """
    Request a short-lived ephemeral token from the xAI API.

    The token is safe to expose to the browser for the duration of a single
    voice session.  It is tied to the session configuration returned by
    :func:`build_session_config`.

    Parameters
    ----------
    collection_id:
        UUID of the contract's Qdrant collection.

    Returns
    -------
    dict
        The token payload from xAI, including ``client_secret.value`` and
        ``expires_at``.

    Raises
    ------
    EnvironmentError
        If ``XAI_API_KEY`` is not configured.
    httpx.HTTPStatusError
        If the xAI API returns a non-2xx status.
    """
    if not settings.xai_api_key:
        raise EnvironmentError(
            "XAI_API_KEY must be set to create voice sessions."
        )

    session_config = build_session_config(collection_id)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.xai_base_url}/realtime/sessions",
            headers={
                "Authorization": f"Bearer {settings.xai_api_key}",
                "Content-Type": "application/json",
            },
            json=session_config,
        )
        resp.raise_for_status()
        return resp.json()
