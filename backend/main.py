import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import conversations as convs
from backend.chat import get_client, stream_answer
from backend.config import settings
from backend.db import connect
from backend.ingestion import (
    ALLOWED_EXTENSIONS,
    extract_text,
    ingest_file,
    load_index,
    remove_document,
)
from backend.watcher import watch_folder

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await asyncio.to_thread(convs.init_db)
    except Exception:
        logger.exception("DB init failed; conversation persistence unavailable")
    watch_task = (
        asyncio.create_task(watch_folder()) if settings.watch_dir else None
    )
    yield
    if watch_task:
        watch_task.cancel()


app = FastAPI(title="RAG Chatbot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def token_auth(request: Request, call_next):
    """Optional bearer-token auth: set API_TOKEN in .env to enable."""
    if settings.api_token and request.method != "OPTIONS":
        is_api = request.url.path.startswith(
            (
                "/upload",
                "/chat",
                "/documents",
                "/models",
                "/conversations",
                "/chunks",
                "/transcribe",
            )
        )
        token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if is_api and token != settings.api_token:
            return JSONResponse({"detail": "Invalid or missing token"}, status_code=401)
    return await call_next(request)

class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    doc_id: str | None = None
    doc_ids: list[str] | None = None
    history: list[Message] = []
    model: str | None = None
    conversation_id: str | None = None
    # false when regenerating an answer, so the question is not saved twice
    save_question: bool = True


@app.post("/upload")
def upload(file: UploadFile = File(...)):
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            "Supported formats: PDF, TXT, MD, CSV, DOCX, XLSX, HTML",
        )

    uploads = Path(settings.uploads_path)
    uploads.mkdir(parents=True, exist_ok=True)
    doc_id = str(uuid.uuid4())
    dest = uploads / f"{doc_id}_{filename}"
    dest.write_bytes(file.file.read())

    try:
        chunks_count = ingest_file(dest, doc_id, filename)
    except ValueError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, str(exc))

    return {"doc_id": doc_id, "filename": filename, "chunks_count": chunks_count}


@app.post("/chat")
async def chat(req: ChatRequest):
    history = [m.model_dump() for m in req.history]
    doc_ids = req.doc_ids or ([req.doc_id] if req.doc_id else None)
    cid = req.conversation_id
    if cid and not await asyncio.to_thread(convs.conversation_exists, cid):
        raise HTTPException(404, "Conversation not found")

    async def sse():
        if cid and req.save_question:
            await asyncio.to_thread(convs.add_message, cid, "user", req.question)
        answer_parts: list[str] = []
        sources: list | None = None
        async for event in stream_answer(req.question, doc_ids, history, req.model):
            if "sources" in event:
                sources = event["sources"]
            if "content" in event:
                answer_parts.append(event["content"])
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"
        if cid and answer_parts:
            await asyncio.to_thread(
                convs.add_message, cid, "assistant", "".join(answer_parts), sources
            )

    return StreamingResponse(sse(), media_type="text/event-stream")


@app.get("/conversations")
def conversations_list():
    return convs.list_conversations()


@app.post("/conversations")
def conversations_create():
    return convs.create_conversation()


@app.get("/conversations/{cid}/messages")
def conversation_messages(cid: str):
    if not convs.conversation_exists(cid):
        raise HTTPException(404, "Conversation not found")
    return convs.get_messages(cid)


class RenameRequest(BaseModel):
    title: str


@app.patch("/conversations/{cid}")
def conversations_rename(cid: str, req: RenameRequest):
    title = req.title.strip()
    if not title:
        raise HTTPException(422, "Title must not be empty")
    if not convs.rename_conversation(cid, title):
        raise HTTPException(404, "Conversation not found")
    return {"id": cid, "title": title}


@app.delete("/conversations/{cid}")
def conversations_delete(cid: str):
    if not convs.delete_conversation(cid):
        raise HTTPException(404, "Conversation not found")
    return {"deleted": cid}


# Curated catalog of chat models that run reasonably on a 16 GB CPU machine.
MODEL_CATALOG = [
    {
        "name": "llama3.2",
        "display_name": "Llama 3.2 (3B)",
        "vendor": "Meta",
        "logo": "🦙",
        "size": "2.0 GB",
        "description": "Balanced quality and speed, good default",
    },
    {
        "name": "llama3.2:1b",
        "display_name": "Llama 3.2 (1B)",
        "vendor": "Meta",
        "logo": "🦙",
        "size": "1.3 GB",
        "description": "Fastest responses, simpler answers",
    },
    {
        "name": "qwen2.5:0.5b",
        "display_name": "Qwen 2.5 (0.5B)",
        "vendor": "Alibaba",
        "logo": "🐉",
        "size": "0.4 GB",
        "description": "Tiny and instant, for quick tests",
    },
    {
        "name": "qwen2.5:3b",
        "display_name": "Qwen 2.5 (3B)",
        "vendor": "Alibaba",
        "logo": "🐉",
        "size": "1.9 GB",
        "description": "Strong multilingual model",
    },
    {
        "name": "qwen2.5:7b",
        "display_name": "Qwen 2.5 (7B)",
        "vendor": "Alibaba",
        "logo": "🐉",
        "size": "4.7 GB",
        "description": "Best answer quality, slower on CPU",
    },
    {
        "name": "gemma2:2b",
        "display_name": "Gemma 2 (2B)",
        "vendor": "Google",
        "logo": "💎",
        "size": "1.6 GB",
        "description": "Compact and capable",
    },
    {
        "name": "mistral",
        "display_name": "Mistral (7B)",
        "vendor": "Mistral AI",
        "logo": "🌪️",
        "size": "4.1 GB",
        "description": "Popular all-rounder, slower on CPU",
    },
    {
        "name": "phi3.5",
        "display_name": "Phi 3.5 (3.8B)",
        "vendor": "Microsoft",
        "logo": "🪟",
        "size": "2.2 GB",
        "description": "Great reasoning for its size",
    },
]


async def _installed_models() -> set[str]:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.ollama_base_url}/api/tags", timeout=10
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(503, f"Ollama is not reachable: {exc}")
    names = set()
    for m in resp.json().get("models", []):
        names.add(m["name"])
        if m["name"].endswith(":latest"):
            names.add(m["name"].removesuffix(":latest"))
    return names


@app.get("/models")
async def models():
    installed = await _installed_models()
    catalog = [{**m, "installed": m["name"] in installed} for m in MODEL_CATALOG]
    catalog_names = {m["name"] for m in MODEL_CATALOG}
    # models the user pulled themselves, outside the catalog
    extra = [
        {
            "name": n,
            "display_name": n,
            "vendor": "Ollama",
            "logo": "🤖",
            "size": "",
            "description": "",
            "installed": True,
        }
        for n in sorted(installed)
        if n not in catalog_names
        and not n.endswith(":latest")
        and "embed" not in n.lower()
    ]
    return {"models": catalog + extra, "default": settings.llm_model}


class PullRequest(BaseModel):
    model: str


@app.post("/models/pull")
async def pull_model(req: PullRequest):
    async def progress():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_base_url}/api/pull",
                json={"model": req.model},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        yield line + "\n"

    return StreamingResponse(progress(), media_type="application/x-ndjson")


@app.get("/documents")
def documents():
    return [
        {"doc_id": doc_id, **meta} for doc_id, meta in load_index().items()
    ]


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    if doc_id not in load_index():
        raise HTTPException(404, "Document not found")
    remove_document(doc_id)
    return {"deleted": doc_id}


@app.get("/chunks/{doc_id}/{chunk_index}")
def get_chunk(doc_id: str, chunk_index: int):
    with connect() as conn:
        row = conn.execute(
            "SELECT document FROM langchain_pg_embedding"
            " WHERE cmetadata->>'doc_id' = %s"
            " AND (cmetadata->>'chunk_index')::int = %s",
            (doc_id, chunk_index),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Chunk not found")
    return {"doc_id": doc_id, "chunk_index": chunk_index, "text": row[0]}


SUGGEST_PROMPT = """Below is the beginning of a document. Suggest 3 short, \
specific questions a reader could ask about it. Reply with one question per \
line, no numbering, no explanations, in the language of the document.

Document:
{text}"""


@app.post("/documents/{doc_id}/suggest")
async def suggest_questions(doc_id: str):
    if doc_id not in load_index():
        raise HTTPException(404, "Document not found")
    files = list(Path(settings.uploads_path).glob(f"{doc_id}_*"))
    if not files:
        raise HTTPException(404, "Document file not found")
    text = (await asyncio.to_thread(extract_text, files[0]))[:3000]
    resp = await get_client().chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": SUGGEST_PROMPT.format(text=text)}],
        max_tokens=200,
        temperature=0.4,
    )
    raw = resp.choices[0].message.content or ""
    questions = [
        line.strip().strip("-•").strip().lstrip("0123456789.").strip()
        for line in raw.splitlines()
        if "?" in line
    ]
    return {"questions": questions[:4]}


@lru_cache(maxsize=1)
def _get_whisper():
    from faster_whisper import WhisperModel

    # "base" is multilingual, ~74 MB int8, fast enough on CPU for short queries
    return WhisperModel("base", device="cpu", compute_type="int8",
                        download_root=".whisper")


def _transcribe_bytes(data: bytes) -> str:
    import io

    segments, _info = _get_whisper().transcribe(io.BytesIO(data), vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """Speech-to-text fallback for browsers without the Web Speech API.
    Accepts any audio container MediaRecorder produces (webm/ogg/mp4)."""
    data = await file.read()
    if not data:
        raise HTTPException(422, "Empty audio")
    try:
        text = await asyncio.to_thread(_transcribe_bytes, data)
    except Exception as exc:
        raise HTTPException(500, f"Transcription failed: {exc}")
    return {"text": text}


class UrlRequest(BaseModel):
    url: str


@app.post("/upload-url")
def upload_url(req: UrlRequest):
    try:
        resp = httpx.get(
            req.url, follow_redirects=True, timeout=60,
            headers={"User-Agent": "Mozilla/5.0 (RAG-chatbot)"},
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(422, f"Could not fetch URL: {exc}")

    from urllib.parse import unquote, urlparse

    name = unquote(Path(urlparse(req.url).path).name) or "page"
    ctype = resp.headers.get("content-type", "")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        if "pdf" in ctype:
            name += ".pdf"
        elif "html" in ctype or "<html" in resp.text[:1000].lower():
            name += ".html"
        else:
            name += ".txt"

    uploads = Path(settings.uploads_path)
    uploads.mkdir(parents=True, exist_ok=True)
    doc_id = str(uuid.uuid4())
    dest = uploads / f"{doc_id}_{name}"
    dest.write_bytes(resp.content)

    try:
        chunks_count = ingest_file(dest, doc_id, name)
    except ValueError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, str(exc))

    return {"doc_id": doc_id, "filename": name, "chunks_count": chunks_count}


# In Docker the built frontend is copied next to the backend and served
# directly by FastAPI, so the whole app runs from one container.
# Mounted last: the catch-all must not shadow API routes defined above.
_static_dir = Path(__file__).parent.parent / "frontend" / "dist"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
