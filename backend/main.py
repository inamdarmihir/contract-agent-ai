"""
FastAPI backend for the Contract Voice Agent.

Endpoints
---------
POST /upload
    Accept a PDF file, run the ingestion pipeline, trigger async risk
    analysis, and return the ``collection_id``.

GET /contracts/{collection_id}/analysis
    Return risk analysis results (clause counts, risk heatmap, top flagged
    clauses) for a previously ingested contract.

GET /contracts/{collection_id}/chunks
    Return all stored chunks with metadata (used by the Risk Dashboard).

POST /contracts/{collection_id}/search
    Perform hybrid semantic + keyword search over a contract collection.

POST /voice/session
    Create an ephemeral xAI voice session token for the browser.

WebSocket /voice/proxy/{collection_id}
    Optional WebSocket proxy so browsers can reach the xAI realtime API
    through the backend when direct access is restricted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

import websockets
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from ingest import ingest_pdf
from risk_analyzer import analyse_collection
from search import get_all_chunks, hybrid_search
from voice_session import create_ephemeral_token

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Contract Voice Agent API",
    description=(
        "Backend API for the open-source voice contract analysis agent. "
        "Upload a PDF contract, analyse risks, and query it by voice."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store: collection_id -> analysis status/results
# In production, replace this with Redis or a lightweight DB.
_analysis_store: dict[str, dict[str, Any]] = {}


# ── Pydantic models ────────────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    """Request body for the /search endpoint."""

    query: str
    risk_level: str | None = None
    clause_type: str | None = None
    top_k: int = settings.search_top_k


class VoiceSessionRequest(BaseModel):
    """Request body for creating a voice session."""

    collection_id: str


# ── Background tasks ──────────────────────────────────────────────────────────


def _run_analysis(collection_id: str) -> None:
    """
    Background task: run risk analysis for the given collection and cache results.

    This is intentionally synchronous so it can be handed off to FastAPI's
    ``BackgroundTasks`` without requiring a separate worker.
    """
    try:
        _analysis_store[collection_id] = {"status": "processing"}
        results = analyse_collection(collection_id)
        _analysis_store[collection_id] = {"status": "complete", "data": results}
        logger.info("Risk analysis complete for %s", collection_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Risk analysis failed for %s: %s", collection_id, exc)
        _analysis_store[collection_id] = {
            "status": "error",
            "message": str(exc),
        }


# ── Routes ─────────────────────────────────────────────────────────────────────


@app.post("/upload", summary="Upload a PDF contract for analysis")
async def upload_contract(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF contract file"),
) -> dict[str, Any]:
    """
    Accept a PDF upload, run the ingestion pipeline, and kick off async
    risk analysis in the background.

    Returns the ``collection_id`` immediately so the frontend can display
    a loading state while risk analysis proceeds.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Save upload to a temp file.
    tmp_dir = tempfile.mkdtemp(prefix="contract_")
    tmp_path = Path(tmp_dir) / (file.filename or "contract.pdf")
    try:
        with tmp_path.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)

        collection_id = ingest_pdf(tmp_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc
    finally:
        # Clean up temp files regardless of success/failure.
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Trigger async risk analysis (non-blocking).
    background_tasks.add_task(_run_analysis, collection_id)

    return {
        "collection_id": collection_id,
        "filename": file.filename,
        "status": "ingested",
        "message": "PDF ingested. Risk analysis is running in the background.",
    }


@app.get(
    "/contracts/{collection_id}/analysis",
    summary="Get risk analysis results",
)
async def get_analysis(collection_id: str) -> dict[str, Any]:
    """
    Return the risk analysis results for a previously ingested contract.

    The response includes a ``status`` field:
    - ``"processing"`` — analysis is still running.
    - ``"complete"``   — results are ready (see ``data`` field).
    - ``"error"``      — analysis failed (see ``message`` field).
    - ``"not_found"``  — no analysis job found for this collection_id.
    """
    result = _analysis_store.get(collection_id)
    if result is None:
        return {"status": "not_found"}
    return result


@app.get(
    "/contracts/{collection_id}/chunks",
    summary="Get all chunks for the risk dashboard",
)
async def get_chunks(collection_id: str) -> dict[str, Any]:
    """
    Return every stored chunk with metadata for a given contract.

    The frontend uses this to build the clause-type breakdown, risk heatmap,
    and page map shown in the Risk Dashboard *before* the user speaks.
    """
    try:
        chunks = get_all_chunks(collection_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"collection_id": collection_id, "chunks": chunks}


@app.post(
    "/contracts/{collection_id}/search",
    summary="Hybrid semantic + keyword search",
)
async def search_contract(
    collection_id: str,
    body: SearchRequest,
) -> dict[str, Any]:
    """
    Perform hybrid (dense + sparse BM42) search over a contract collection.

    Optional ``risk_level`` and ``clause_type`` filters narrow the result set.
    """
    try:
        results = hybrid_search(
            collection_id=collection_id,
            query=body.query,
            risk_level=body.risk_level,
            clause_type=body.clause_type,
            top_k=body.top_k,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"results": results}


@app.post("/voice/session", summary="Create an ephemeral xAI voice session token")
async def create_voice_session(body: VoiceSessionRequest) -> dict[str, Any]:
    """
    Request a short-lived ephemeral token from xAI for a browser voice session.

    The token is safe to expose to the client — it grants access only to the
    realtime API for the configured session and expires automatically.
    """
    try:
        token_data = await create_ephemeral_token(body.collection_id)
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to create voice session: {exc}"
        ) from exc
    return token_data


# ── WebSocket proxy ───────────────────────────────────────────────────────────


@app.websocket("/voice/proxy/{collection_id}")
async def websocket_proxy(websocket: WebSocket, collection_id: str) -> None:
    """
    Optional WebSocket proxy that bridges the browser to the xAI realtime API.

    Use this endpoint when the browser cannot connect directly to
    ``wss://api.x.ai/v1/realtime`` (e.g., behind a corporate firewall or
    when you don't want to expose ephemeral tokens to the client).

    The proxy forwards all messages bidirectionally and injects the
    ``session.update`` message with the correct collection_id on connect.
    """
    await websocket.accept()

    if not settings.xai_api_key:
        await websocket.close(code=1008, reason="XAI_API_KEY not configured")
        return

    realtime_url = (
        f"{settings.xai_realtime_url}?model={settings.xai_voice_model}"
    )
    headers = {
        "Authorization": f"Bearer {settings.xai_api_key}",
        "OpenAI-Beta": "realtime=v1",
    }

    try:
        async with websockets.connect(realtime_url, extra_headers=headers) as xai_ws:
            # Send initial session configuration to xAI.
            from voice_session import build_session_config

            session_cfg = build_session_config(collection_id)
            await xai_ws.send(
                json.dumps({"type": "session.update", "session": session_cfg})
            )

            async def forward_to_xai() -> None:
                """Forward messages from browser → xAI."""
                try:
                    while True:
                        data = await websocket.receive_text()
                        await xai_ws.send(data)
                except WebSocketDisconnect:
                    pass

            async def forward_to_browser() -> None:
                """Forward messages from xAI → browser."""
                try:
                    async for message in xai_ws:
                        await websocket.send_text(
                            message if isinstance(message, str) else message.decode()
                        )
                except Exception:  # noqa: BLE001
                    pass

            await asyncio.gather(forward_to_xai(), forward_to_browser())

    except Exception as exc:  # noqa: BLE001
        logger.error("WebSocket proxy error: %s", exc)
        try:
            await websocket.close(code=1011, reason="Proxy error")
        except Exception:  # noqa: BLE001
            pass


# ── Health check ──────────────────────────────────────────────────────────────


@app.get("/health", summary="Health check")
async def health() -> dict[str, str]:
    """Return a simple liveness indicator."""
    return {"status": "ok", "version": "1.0.0"}
