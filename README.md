# RAG Chatbot API

Chat with your documents (RAG): upload PDF/TXT files, ask questions, and get answers grounded strictly in the document content, streamed in real time.

Runs **fully free and local**: LLM and embeddings via [Ollama](https://ollama.com), vector store via Postgres + [pgvector](https://github.com/pgvector/pgvector).

## Stack

- **FastAPI** — backend API (Python 3.12+)
- **Ollama** — `llama3.2` (chat) and `nomic-embed-text` (embeddings), local, no API keys
- **LangChain** + `langchain-postgres` — RAG pipeline and vector store integration
- **Postgres + pgvector** — vector storage and similarity search (in Docker)
- **PyMuPDF** — PDF parsing
- **Vue 3 + Vite** — web UI with streaming chat and a model gallery

## Project structure

```
├── backend/
│   ├── main.py          # FastAPI app and endpoints
│   ├── ingestion.py     # parse → chunk → embed → store in pgvector
│   ├── retriever.py     # similarity search (top-k, doc_id filter)
│   ├── chat.py          # prompt building + streaming via Ollama
│   └── config.py        # settings (pydantic-settings, .env)
├── frontend/            # Vue 3 + Vite app
│   ├── index.html
│   └── src/
│       ├── App.vue              # layout: sidebar + chat
│       ├── api.js               # backend client (SSE/NDJSON streaming)
│       └── components/
│           ├── ModelPicker.vue  # model cards with vendor logos + download
│           └── ChatWindow.vue   # streaming chat
├── uploads/             # uploaded files + index.json (gitignored)
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Quick start

Prerequisites: Python 3.12+, Node.js 18+, Docker Desktop, [Ollama](https://ollama.com/download).

```powershell
# 1. Dependencies
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# 2. Config
copy .env.example .env

# 3. Ollama models (one-time, ~2.3 GB)
ollama pull llama3.2
ollama pull nomic-embed-text

# 4. Database (Postgres + pgvector in Docker)
docker compose up -d db

# 5. Backend
.\.venv\Scripts\uvicorn backend.main:app --reload

# 6. Frontend (in a separate terminal)
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** — upload a PDF or TXT in the sidebar, pick a model, and ask questions in the chat.

Swagger API docs: http://localhost:8000/docs

> The first answer may take 10–30 seconds: the model loads into memory and runs on CPU.

## API

### `POST /upload`

Upload a document (multipart/form-data, `file` field, PDF or TXT). The file is saved to `uploads/`, split into chunks (1000 chars, 200 overlap), embedded, and stored in pgvector.

```bash
curl -X POST http://localhost:8000/upload -F "file=@sample.txt"
```

```json
{ "doc_id": "321bba78-...", "filename": "sample.txt", "chunks_count": 1 }
```

### `POST /chat`

Ask a question about your documents. The response is a `text/event-stream` (SSE). If `doc_id` is omitted, search runs across all documents. `history` holds previous messages (the last 6 are used). Optional `model` overrides the default LLM for this request.

```bash
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the project budget?", "doc_id": null, "history": [], "model": null}'
```

```
data: {"content": "The"}
data: {"content": " budget"}
...
data: [DONE]
```

The model answers **only from the document content**; if the answer is not there, it says so explicitly.

### `GET /documents`

List all ingested documents:

```json
[{ "doc_id": "321bba78-...", "filename": "sample.txt", "chunks_count": 1 }]
```

### `GET /models`

A curated catalog of chat models (plus anything else you have pulled into Ollama), each marked as installed or not. The UI renders this as a gallery of model cards with vendor logos.

```json
{
  "models": [
    { "name": "llama3.2", "size": "2.0 GB", "description": "Meta Llama 3.2 3B", "installed": true },
    { "name": "qwen2.5:7b", "size": "4.7 GB", "description": "Qwen 2.5 7B, best quality", "installed": false }
  ],
  "default": "llama3.2"
}
```

### `POST /models/pull`

Download a model into Ollama. Streams pull progress as NDJSON (proxied from Ollama), so the UI can render a live progress bar. In the sidebar, model cards that are not installed show a **Download** button that calls this endpoint.

```bash
curl -N -X POST http://localhost:8000/models/pull \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen2.5:3b"}'
```

```
{"status":"pulling manifest"}
{"status":"pulling c5396e06af29","total":397807936,"completed":131072000}
...
{"status":"success"}
```

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama address |
| `LLM_MODEL` | `llama3.2` | chat model |
| `EMBED_MODEL` | `nomic-embed-text` | embedding model |
| `CHUNK_SIZE` | `1000` | chunk size (characters) |
| `CHUNK_OVERLAP` | `200` | chunk overlap |
| `TOP_K` | `5` | number of chunks injected into context |
| `PG_CONN` | `postgresql+psycopg://rag:rag@localhost:5432/rag` | Postgres connection string |

Want better answers? Pull a larger model: `ollama pull qwen2.5:7b` and set `LLM_MODEL=qwen2.5:7b` in `.env` (slower on CPU).

## Running everything in Docker

```powershell
docker compose up --build
```

Starts Postgres and the API (port 8000). Ollama must be running on the host — the container reaches it via `host.docker.internal`. The frontend is started separately (step 6 above).

## How it works

1. **Ingestion**: PDF/TXT → text (PyMuPDF) → chunks (`RecursiveCharacterTextSplitter`) → embeddings (Ollama) → pgvector. Each chunk carries metadata: `doc_id`, `filename`, `chunk_index`. The document registry lives in `uploads/index.json`.
2. **Chat**: the question is embedded → top-5 similar chunks fetched from pgvector (filtered by `doc_id` if provided) → system prompt with context + last 6 history messages + question → answer streamed from `llama3.2` via Ollama's OpenAI-compatible API.
