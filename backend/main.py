import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.chat import stream_answer
from backend.config import settings
from backend.ingestion import ingest_file, load_index

app = FastAPI(title="RAG Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".pdf", ".txt"}


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    doc_id: str | None = None
    history: list[Message] = []
    model: str | None = None


@app.post("/upload")
def upload(file: UploadFile = File(...)):
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Only PDF and TXT files are supported")

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
    return StreamingResponse(
        stream_answer(req.question, req.doc_id, history, req.model),
        media_type="text/event-stream",
    )


# Curated catalog of chat models that run reasonably on a 16 GB CPU machine.
MODEL_CATALOG = [
    {"name": "llama3.2", "size": "2.0 GB", "description": "Meta Llama 3.2 3B"},
    {"name": "llama3.2:1b", "size": "1.3 GB", "description": "Meta Llama 3.2 1B, fastest"},
    {"name": "qwen2.5:0.5b", "size": "0.4 GB", "description": "Qwen 2.5 0.5B, tiny"},
    {"name": "qwen2.5:3b", "size": "1.9 GB", "description": "Qwen 2.5 3B"},
    {"name": "qwen2.5:7b", "size": "4.7 GB", "description": "Qwen 2.5 7B, best quality"},
    {"name": "gemma2:2b", "size": "1.6 GB", "description": "Google Gemma 2 2B"},
    {"name": "mistral", "size": "4.1 GB", "description": "Mistral 7B"},
    {"name": "phi3.5", "size": "2.2 GB", "description": "Microsoft Phi 3.5 3.8B"},
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
        {"name": n, "size": "", "description": "", "installed": True}
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
