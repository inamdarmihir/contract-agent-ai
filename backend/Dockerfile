FROM python:3.11-slim

WORKDIR /app

# Install build dependencies for sentence-transformers and pdfplumber.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-download the default embedding model at build time so the first
# upload doesn't stall waiting for a model download.
ENV EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-base-en-v1.5')"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
