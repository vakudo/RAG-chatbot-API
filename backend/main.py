import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend import conversations as convs
from backend.chat import stream_answer
from backend.config import settings
from backend.ingestion import ingest_file, load_index, remove_document

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await asyncio.to_thread(convs.init_db)
    except Exception:
        logger.exception("DB init failed; conversation persistence unavailable")
    yield


app = FastAPI(title="RAG Chatbot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {
    ".pdf", ".txt", ".md", ".csv", ".docx", ".xlsx", ".xlsm", ".html", ".htm",
}


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
        if cid:
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
