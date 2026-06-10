"""Optional folder watcher: set WATCH_DIR in .env and every supported file
dropped into that folder is ingested automatically (re-ingested on change)."""

import asyncio
import json
import logging
import shutil
import uuid
from pathlib import Path

from backend.config import settings
from backend.ingestion import (
    ALLOWED_EXTENSIONS,
    ingest_file,
    load_index,
    remove_document,
)

logger = logging.getLogger(__name__)

POLL_SECONDS = 10


def _state_path() -> Path:
    return Path(settings.uploads_path) / "watch_state.json"


def _scan_once(state: dict) -> bool:
    """Ingest new/changed files; returns True if state changed."""
    folder = Path(settings.watch_dir)
    if not folder.is_dir():
        return False
    changed = False
    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        mtime = f.stat().st_mtime
        if state.get(f.name) == mtime:
            continue
        # drop the previous version of this file, if any
        for doc_id, meta in list(load_index().items()):
            if meta["filename"] == f.name:
                remove_document(doc_id)
        doc_id = str(uuid.uuid4())
        uploads = Path(settings.uploads_path)
        uploads.mkdir(parents=True, exist_ok=True)
        dest = uploads / f"{doc_id}_{f.name}"
        shutil.copy2(f, dest)
        try:
            count = ingest_file(dest, doc_id, f.name)
            logger.info("watch: ingested %s (%s chunks)", f.name, count)
        except ValueError:
            dest.unlink(missing_ok=True)
            logger.warning("watch: no text in %s, skipped", f.name)
        state[f.name] = mtime
        changed = True
    return changed


async def watch_folder() -> None:
    state = {}
    if _state_path().exists():
        try:
            state = json.loads(_state_path().read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    logger.info("watching folder %s", settings.watch_dir)
    while True:
        try:
            if await asyncio.to_thread(_scan_once, state):
                _state_path().write_text(json.dumps(state), encoding="utf-8")
        except Exception:
            logger.exception("watch: scan failed")
        await asyncio.sleep(POLL_SECONDS)
