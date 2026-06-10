# RAG Chatbot API

Chat with your documents (RAG): upload PDF, DOCX, Excel, CSV, TXT, Markdown or HTML files (or paste a URL), ask questions, and get answers grounded strictly in the document content — streamed in real time, with source citations.

Runs **fully free and local**: LLM and embeddings via [Ollama](https://ollama.com), vector store via Postgres + [pgvector](https://github.com/pgvector/pgvector).

Features: hybrid retrieval (vector + full-text with RRF) with local cross-encoder reranking, follow-up question rewriting, source citations with full-chunk viewer, suggested questions per document, OCR fallback for scanned PDFs, multiple persistent conversations (rename/search/export), multi-document filtering, batch upload and folder watching, model gallery with one-click downloads, Markdown answers, copy/regenerate, voice input, dark/light theme, optional token auth.

## Stack

- **FastAPI** — backend API (Python 3.12+)
- **Ollama** — `llama3.2` (chat) and `nomic-embed-text` (embeddings), local, no API keys
- **LangChain** + `langchain-postgres` — RAG pipeline and vector store integration
- **Postgres + pgvector** — vector storage and similarity search (in Docker)
- **PyMuPDF** — PDF parsing; **openpyxl** — Excel parsing
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

Or, once dependencies are installed, start everything with one command:

```powershell
.\start.ps1
```

Open **http://localhost:5173** — upload a PDF, TXT or Excel file in the sidebar, pick a model, and ask questions in the chat.

Swagger API docs: http://localhost:8000/docs

> The first answer may take 10–30 seconds: the model loads into memory and runs on CPU.

## API

### `POST /upload`

Upload a document (multipart/form-data, `file` field; PDF, DOCX, XLSX/XLSM, CSV, TXT, MD, HTML). The file is saved to `uploads/`, split into chunks (1000 chars, 200 overlap), embedded, and stored in pgvector. Tabular formats (Excel, CSV, DOCX tables) are flattened into `header: value` lines per row, so chunks stay self-describing for similarity search.

```bash
curl -X POST http://localhost:8000/upload -F "file=@sample.txt"
```

```json
{ "doc_id": "321bba78-...", "filename": "sample.txt", "chunks_count": 1 }
```

### `POST /upload-url`

Ingest a page or file by URL: `{"url": "https://example.com/report.pdf"}`. The content type is detected automatically (PDF/HTML/text).

### `GET /documents` · `DELETE /documents/{doc_id}`

List all ingested documents, or delete one (removes its chunks from pgvector, the file from `uploads/`, and the registry entry).

```json
[{ "doc_id": "321bba78-...", "filename": "sample.txt", "chunks_count": 1 }]
```

### `POST /chat`

Ask a question about your documents. The response is a `text/event-stream` (SSE): first an event with the retrieved sources, then the answer tokens.

```bash
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the project budget?", "doc_ids": null, "history": [], "model": null, "conversation_id": null}'
```

```
data: {"sources": [{"doc_id": "...", "filename": "sample.txt", "chunk_index": 0, "snippet": "..."}]}
data: {"content": "The"}
data: {"content": " budget"}
...
data: [DONE]
```

- `doc_ids` — restrict search to specific documents (omit for all)
- `history` — previous messages; follow-up questions are rewritten into standalone search queries using it
- `model` — override the default LLM for this request
- `conversation_id` — persist the exchange into a conversation (see below)

The model answers **only from the document content**; if the answer is not there, it says so explicitly.

### Conversations

- `GET /conversations` — list (newest first; titled by the first question)
- `POST /conversations` — create
- `GET /conversations/{id}/messages` — full message history with sources
- `PATCH /conversations/{id}` — rename (`{"title": "..."}`)
- `DELETE /conversations/{id}` — delete with messages

Stored in Postgres (`conversations` + `messages` tables, created automatically on startup).

### More

- `GET /chunks/{doc_id}/{chunk_index}` — full text of a retrieved chunk (used by the source viewer)
- `POST /documents/{doc_id}/suggest` — LLM-generated starter questions for a document

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
| `RERANK` | `true` | rerank retrieved chunks with a local cross-encoder (flashrank) |
| `WATCH_DIR` | _(empty)_ | folder to watch; new/changed files are ingested automatically |
| `API_TOKEN` | _(empty)_ | when set, all API requests must send `Authorization: Bearer <token>` (in the UI, set it via DevTools: `localStorage.setItem('api_token', '...')`) |

Want better answers? Pull a larger model: `ollama pull qwen2.5:7b` and set `LLM_MODEL=qwen2.5:7b` in `.env` (slower on CPU).

## Running everything in Docker

```powershell
docker compose up --build
```

Starts Postgres and the app (port 8000). The Docker image builds the Vue frontend and serves it from FastAPI, so **http://localhost:8000** is the full app — no separate frontend process. Ollama must be running on the host — the container reaches it via `host.docker.internal`.

## How it works

1. **Ingestion**: document → text (PyMuPDF for PDF, openpyxl for Excel, python-docx for DOCX, BeautifulSoup for HTML) → chunks (`RecursiveCharacterTextSplitter`) → embeddings (Ollama) → pgvector. Each chunk carries metadata: `doc_id`, `filename`, `chunk_index`. The document registry lives in `uploads/index.json`.
2. **Retrieval**: follow-up questions are first rewritten into standalone queries by the LLM. Then hybrid search runs: vector similarity (pgvector) + full-text (`tsvector`), merged with reciprocal rank fusion; the candidates are reranked by a local cross-encoder (flashrank, ~4 MB ONNX model) and the top-5 win. Markdown documents are chunked along their headings; scanned PDFs go through OCR (RapidOCR) when no text layer is found.
3. **Chat**: system prompt with the retrieved context + last 6 history messages + question → answer streamed from the selected model via Ollama's OpenAI-compatible API. Sources (file, chunk, snippet) are sent to the client before the answer and rendered as chips under each reply.

## Tests & eval

```powershell
.\.venv\Scripts\python.exe -m pytest tests\     # unit tests (no DB/Ollama needed)
.\.venv\Scripts\python.exe eval\run_eval.py     # answer-quality eval against the live API
```

Unit tests cover text extraction for every format, the RRF merge logic, and API validation. The eval runs `eval/questions.json` through `/chat` and checks expected keywords — extend it with your own documents and questions. CI (GitHub Actions) runs pytest and the frontend build on every push.
