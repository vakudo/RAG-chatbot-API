import uuid
from pathlib import Path

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
        stream_answer(req.question, req.doc_id, history),
        media_type="text/event-stream",
    )


@app.get("/documents")
def documents():
    return [
        {"doc_id": doc_id, **meta} for doc_id, meta in load_index().items()
    ]
