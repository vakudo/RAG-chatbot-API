import json
import threading
from pathlib import Path

import fitz
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openpyxl import load_workbook

from backend.config import settings
from backend.retriever import get_vectorstore

_index_lock = threading.Lock()


def _index_path() -> Path:
    return Path(settings.uploads_path) / "index.json"


def load_index() -> dict:
    path = _index_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_index(index: dict) -> None:
    _index_path().write_text(json.dumps(index, indent=2), encoding="utf-8")


def _extract_xlsx(path: Path) -> str:
    # Rows become "header: value" lines so each chunk stays self-describing
    # after splitting, which keeps similarity search meaningful.
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = []
        for ws in wb.worksheets:
            header = None
            lines = [f"Sheet: {ws.title}"]
            for row in ws.iter_rows(values_only=True):
                cells = ["" if c is None else str(c).strip() for c in row]
                if not any(cells):
                    continue
                if header is None:
                    header = cells
                    continue
                pairs = [f"{h}: {v}" for h, v in zip(header, cells) if v and h]
                if pairs:
                    lines.append("; ".join(pairs))
            if len(lines) > 1:
                sheets.append("\n".join(lines))
        return "\n\n".join(sheets)
    finally:
        wb.close()


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        with fitz.open(path) as doc:
            return "\n".join(page.get_text() for page in doc)
    if suffix in {".xlsx", ".xlsm"}:
        return _extract_xlsx(path)
    return path.read_text(encoding="utf-8", errors="ignore")


def ingest_file(path: Path, doc_id: str, filename: str) -> int:
    text = extract_text(path)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
    )
    chunks = splitter.split_text(text)
    if not chunks:
        raise ValueError("No text could be extracted from the file")

    metadatas = [
        {"doc_id": doc_id, "filename": filename, "chunk_index": i}
        for i in range(len(chunks))
    ]
    get_vectorstore().add_texts(chunks, metadatas=metadatas)

    with _index_lock:
        index = load_index()
        index[doc_id] = {"filename": filename, "chunks_count": len(chunks)}
        _save_index(index)
    return len(chunks)
