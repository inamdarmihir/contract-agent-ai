"""
PDF ingestion pipeline.

Workflow:
1. Extract text from PDF using ``pdfplumber``, preserving page numbers and
   attempting to detect section/clause headers.
2. Chunk the extracted text at clause boundaries using LlamaIndex.
3. Embed each chunk with the configured embedding model.
4. Upload vectors + metadata to a per-document Qdrant collection.

The caller receives the ``collection_id`` (a UUID) that uniquely identifies
this contract inside Qdrant.  All subsequent search and voice-session calls
reference that ID.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

import pdfplumber
from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from config import settings
from embeddings import get_embedder

# ── helpers ───────────────────────────────────────────────────────────────────

# Regex patterns to detect common contract section headers.
_HEADER_PATTERNS = [
    re.compile(
        r"^(?:section|article|clause|exhibit|schedule|appendix|addendum)\s*[\d\.]+|"
        r"^(?:section|article|clause|exhibit|schedule|appendix|addendum)\s+[A-Z][\.\s]",
        re.IGNORECASE,
    ),
    re.compile(r"^\d+[\.\)]\s+[A-Z][A-Za-z ]{3,}$"),  # "1. Definitions"
    re.compile(r"^[A-Z][A-Z\s]{4,}$"),                  # "LIMITATION OF LIABILITY"
]

_CLAUSE_TYPE_KEYWORDS: dict[str, list[str]] = {
    "liability": ["liabil", "limitation of liability", "consequential"],
    # auto-renewal must be checked before termination: "auto-renew" text also
    # contains "cancel" / "terminat" keywords so the more specific type wins.
    "auto-renewal": ["auto-renew", "automatic renewal", "evergreen"],
    "termination": ["terminat", "cancel", "expir"],
    "payment": ["payment", "invoice", "fee", "price", "cost", "billing"],
    "IP": ["intellectual property", "copyright", "patent", "trademark", "ownership"],
    "confidentiality": ["confidential", "non-disclosure", "nda", "proprietary"],
    "indemnification": ["indemnif", "hold harmless", "defend"],
}


def _detect_clause_type(text: str) -> str:
    """Return the most likely clause type for the given text snippet."""
    text_lower = text.lower()
    for clause_type, keywords in _CLAUSE_TYPE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return clause_type
    return "other"


def _is_header_line(line: str) -> bool:
    """Return True if *line* looks like a section heading."""
    stripped = line.strip()
    return any(p.match(stripped) for p in _HEADER_PATTERNS)


def _extract_pages(pdf_path: Path) -> list[dict[str, Any]]:
    """
    Extract text from every page of the PDF.

    Returns a list of page dicts::

        [{"page_number": 1, "text": "...", "headers": ["DEFINITIONS", ...]}, ...]
    """
    pages: list[dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_obj in pdf.pages:
            raw = page_obj.extract_text() or ""
            lines = raw.splitlines()
            headers = [line.strip() for line in lines if _is_header_line(line)]
            pages.append(
                {
                    "page_number": page_obj.page_number,
                    "text": raw,
                    "headers": headers,
                }
            )
    return pages


def _build_llama_documents(pages: list[dict[str, Any]]) -> list[Document]:
    """Convert extracted page dicts to LlamaIndex :class:`Document` objects."""
    docs: list[Document] = []
    for page in pages:
        if not page["text"].strip():
            continue
        docs.append(
            Document(
                text=page["text"],
                metadata={
                    "page_number": page["page_number"],
                    "headers": "; ".join(page["headers"]),
                },
            )
        )
    return docs


def _chunk_documents(docs: list[Document]) -> list[Any]:
    """
    Split LlamaIndex documents into clause-level chunks.

    Uses :class:`SentenceSplitter` with configured chunk_size / overlap so
    that splits happen at sentence boundaries rather than arbitrary character
    positions.
    """
    splitter = SentenceSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    return splitter.get_nodes_from_documents(docs, show_progress=False)


# ── public API ────────────────────────────────────────────────────────────────


def ingest_pdf(pdf_path: Path | str) -> str:
    """
    Full ingestion pipeline for a single PDF contract.

    Steps:
    1. Extract text per page.
    2. Build LlamaIndex documents.
    3. Chunk at sentence/clause boundaries.
    4. Embed chunks.
    5. Create a Qdrant collection and upload points (without risk scores —
       those are filled in by :mod:`risk_analyzer` after this call).

    Parameters
    ----------
    pdf_path:
        Path to the PDF file on disk.

    Returns
    -------
    str
        The ``collection_id`` (UUID string) for the newly created collection.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    collection_id = str(uuid.uuid4())

    # ── 1. Extract pages ──────────────────────────────────────────────────────
    pages = _extract_pages(pdf_path)

    # ── 2-3. Build docs and chunk ─────────────────────────────────────────────
    docs = _build_llama_documents(pages)
    nodes = _chunk_documents(docs)

    if not nodes:
        raise ValueError("No text could be extracted from the PDF.")

    # ── 4. Embed ──────────────────────────────────────────────────────────────
    embedder = get_embedder()
    texts = [node.get_content() for node in nodes]
    vectors = embedder.embed(texts)

    # ── 5. Qdrant upload ──────────────────────────────────────────────────────
    client = _get_qdrant_client()

    # Create a uniquely named collection for this contract.
    coll_name = f"{settings.collection_name}_{collection_id}"
    client.create_collection(
        collection_name=coll_name,
        vectors_config=VectorParams(
            size=settings.embedding_dim,
            distance=Distance.COSINE,
        ),
    )

    points: list[PointStruct] = []
    for idx, (node, vector) in enumerate(zip(nodes, vectors)):
        text = node.get_content()
        page_num = node.metadata.get("page_number", 0)
        headers = node.metadata.get("headers", "")
        section_title = headers.split(";")[0].strip() if headers else ""

        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "text": text,
                    "page_number": page_num,
                    "section_title": section_title,
                    "clause_type": _detect_clause_type(text),
                    # risk fields are populated later by risk_analyzer
                    "risk_level": "unknown",
                    "risk_reason": "",
                    "plain_english": "",
                    "chunk_index": idx,
                },
            )
        )

    # Upload in batches of 100 to avoid memory spikes on large contracts.
    batch_size = 100
    for i in range(0, len(points), batch_size):
        client.upsert(collection_name=coll_name, points=points[i : i + batch_size])

    return collection_id


def _get_qdrant_client() -> QdrantClient:
    """Build and return a :class:`QdrantClient` from settings."""
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
