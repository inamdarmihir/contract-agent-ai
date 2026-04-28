<div align="center">

# ⚖️ Contract Voice Agent

> Open-source voice AI agent that lets you upload a PDF contract, then **ask questions about it by voice**. The agent pre-analyses every clause for risk, explains complex terms in plain language, and answers follow-up questions conversationally — no typing required.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org)
[![FastAPI 0.111.0+](https://img.shields.io/badge/FastAPI-0.111.0%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Qdrant 1.9.0+](https://img.shields.io/badge/Qdrant-1.9.0%2B-FA0F4E?logo=qdrant&logoColor=white)](https://qdrant.tech/)
[![React 18.3.1](https://img.shields.io/badge/React-18.3.1-61DAFB?logo=react&logoColor=black)](https://reactjs.org/)
[![Vite 5.3.1](https://img.shields.io/badge/Vite-5.3.1-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)

</div>

---

## ✨ Features

| Feature | Details |
|---|---|
| **Pre-analysed risk** | Every clause tagged `high / medium / low` before you speak |
| **Voice-first** | Real-time voice I/O via xAI Grok Voice API (WebSocket) |
| **Hybrid search** | Dense embeddings + BM42 keyword match via Qdrant |
| **Risk Dashboard** | Clause-type breakdown, risk heatmap, top-5 flagged clauses |
| **Self-hostable** | All components run locally; contracts never leave your machine |
| **Local embeddings** | `BAAI/bge-base-en-v1.5` by default — no OpenAI key needed for embeddings |

---

## 🏗️ Architecture

```
PDF upload
    │
    ▼
pdfplumber  ──── text + page numbers ────► LlamaIndex SentenceSplitter
                                                │
                                        clause-level chunks
                                                │
                                  BAAI/bge-base-en-v1.5 embeddings
                                                │
                                    ┌───────────▼───────────┐
                                    │   Qdrant collection   │
                                    │  (vector + payload)   │
                                    └───────────┬───────────┘
                                                │
                                      Grok text API
                                    (risk tagging pass)
                                                │
                                    ┌───────────▼───────────┐
                                    │  payload: risk_level  │
                                    │  risk_reason          │
                                    │  plain_english        │
                                    └───────────┬───────────┘
                                                │
                                    Risk Dashboard (React)
                                                │
                            ┌───────────────────▼────────────────────┐
                            │         User speaks a question          │
                            └───────────────────┬────────────────────┘
                                                │
                                    FastAPI WebSocket proxy
                                                │
                            ┌───────────────────▼────────────────────┐
                            │   xAI Grok Voice API (WebSocket)        │
                            │   calls search_contract tool            │
                            └───────────────────┬────────────────────┘
                                                │
                                    Hybrid Qdrant search
                               (dense similarity + BM42 keywords)
                                                │
                                    top-3 chunks + metadata
                                                │
                            ┌───────────────────▼────────────────────┐
                            │   Grok synthesises voice response       │
                            └────────────────────────────────────────┘
```

---

## 🚀 One-Command Setup

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- An [xAI API key](https://console.x.ai/)

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/inamdarmihir/contract-agent-ai.git
cd contract-agent-ai

# 2. Create your environment file
cp .env.example .env
# Edit .env and add your XAI_API_KEY

# 3. Start everything
docker compose up
```

Then open **<http://localhost:3000>** in your browser, upload a PDF contract, and start talking. 🎙️

> **First run note:** The backend Docker image pre-downloads the `BAAI/bge-base-en-v1.5` embedding model during build (~440 MB). This happens once; subsequent starts are fast.

---

## 🔧 Configuration

All configuration is done via environment variables (copy `.env.example` → `.env`):

| Variable | Default | Description |
|---|---|---|
| `XAI_API_KEY` | *(required)* | Your xAI API key for Grok voice + text |
| `EMBEDDING_MODEL` | `BAAI/bge-base-en-v1.5` | Embedding model (see below) |
| `QDRANT_HOST` | `localhost` | Qdrant server hostname |
| `QDRANT_PORT` | `6333` | Qdrant server port |
| `QDRANT_URL` | *(empty)* | Full Qdrant URL (overrides host/port) |
| `QDRANT_API_KEY` | *(empty)* | API key for Qdrant Cloud |
| `COLLECTION_NAME` | `contracts` | Qdrant collection name prefix |
| `OPENAI_API_KEY` | *(empty)* | Required only for OpenAI embeddings |

---

## 🔄 Swapping the Embedding Model

### Option A — Local model (default, no API key)

```env
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
```

The `sentence-transformers` library downloads and caches the model locally. No external API calls are made for embedding.

### Option B — OpenAI embeddings

```env
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=sk-...
```

> ⚠️ OpenAI's `text-embedding-3-small` produces 1536-dimensional vectors.  
> You must also set `EMBEDDING_DIM=1536` so Qdrant creates collections with the correct vector size.

---

## ☁️ Using Qdrant Cloud

1. Create a free cluster at [cloud.qdrant.io](https://cloud.qdrant.io).
2. Copy the cluster URL and API key.
3. Update your `.env`:

```env
QDRANT_URL=https://<cluster-id>.us-east4-0.gcp.cloud.qdrant.io
QDRANT_API_KEY=your_qdrant_cloud_api_key
# Leave QDRANT_HOST / QDRANT_PORT blank — QDRANT_URL takes precedence
```

The rest of the application works exactly the same.

---

## 📁 Project Structure

```
contract-voice-agent/
├── backend/
│   ├── main.py            # FastAPI app — all HTTP + WebSocket endpoints
│   ├── ingest.py          # PDF parsing → chunking → embedding → Qdrant upload
│   ├── risk_analyzer.py   # One-time Grok risk-tagging pass over every chunk
│   ├── search.py          # Hybrid Qdrant search (dense + BM42)
│   ├── voice_session.py   # xAI WebSocket session + ephemeral token
│   ├── embeddings.py      # Unified Embedder (local bge or OpenAI)
│   ├── config.py          # Typed settings from env vars (pydantic-settings)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── UploadZone.jsx    # PDF drag-and-drop
│   │   │   ├── RiskDashboard.jsx # Visual risk breakdown
│   │   │   ├── VoiceAgent.jsx    # WebSocket + mic + audio playback
│   │   │   └── ClauseViewer.jsx  # Clause detail inspector
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── index.html
│   ├── vite.config.js
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 🛠️ Local Development (without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy and configure env
cp ../.env.example ../.env     # edit as needed

uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev    # starts on http://localhost:3000
```

Make sure Qdrant is running:

```bash
docker run -p 6333:6333 qdrant/qdrant
```

---

## 🤝 Contributing

We welcome contributions! Here is how to add a new **clause type detector**.

### Adding a New Clause Type

1. **Open `backend/ingest.py`** and locate the `_CLAUSE_TYPE_KEYWORDS` dictionary.

2. **Add your new type** with a list of trigger keywords:

   ```python
   _CLAUSE_TYPE_KEYWORDS: dict[str, list[str]] = {
       ...
       "arbitration": ["arbitration", "arbitrate", "dispute resolution", "adr"],
   }
   ```

3. **Update the `clause_type` enum** in `backend/voice_session.py` inside `build_session_config()` so the voice agent can filter by it:

   ```python
   "enum": [
       "liability", "termination", "payment", "IP",
       "confidentiality", "auto-renewal", "indemnification",
       "arbitration",   # ← add here
       "other",
   ],
   ```

4. **Add a chart colour** in `frontend/src/components/RiskDashboard.jsx` inside `clauseTypeColor()`:

   ```js
   arbitration: '#06b6d4',
   ```

5. **Write a test** in `backend/tests/` (see existing test structure).

6. Open a pull request describing the new clause type, the keywords used, and any edge cases.

---

## 🗺️ Roadmap (v2)

- [ ] **Speaker diarisation** — detect which party each clause favours
- [ ] **Negotiation mode** — suggest alternative wording for high-risk clauses
- [ ] **Multi-contract comparison** — diff two versions of the same contract
- [ ] **PDF export** — generate a risk-summary report with plain-English explanations

---

## 📄 License

MIT © [inamdarmihir](https://github.com/inamdarmihir)
