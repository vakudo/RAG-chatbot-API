import asyncio
import json
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from backend.config import settings
from backend.retriever import retrieve

SYSTEM_PROMPT = """You are a helpful assistant that answers questions using ONLY the provided context.

Rules:
- Answer strictly from the context below. Do not use outside knowledge.
- If the answer is not contained in the context, reply exactly: \
"I could not find the answer in the provided documents."

Context:
{context}"""

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        # Ollama exposes an OpenAI-compatible API; the key is required by the
        # client but ignored by the server
        _client = AsyncOpenAI(
            base_url=f"{settings.ollama_base_url}/v1", api_key="ollama"
        )
    return _client


async def stream_answer(
    question: str,
    doc_id: str | None,
    history: list[dict],
    model: str | None = None,
) -> AsyncIterator[str]:
    docs = await asyncio.to_thread(retrieve, question, doc_id)
    context = "\n\n---\n\n".join(d.page_content for d in docs)
    if not context:
        context = "(no relevant context found)"

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT.format(context=context)}]
        + [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
        + [{"role": "user", "content": question}]
    )

    stream = await get_client().chat.completions.create(
        model=model or settings.llm_model, messages=messages, stream=True
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield f"data: {json.dumps({'content': delta})}\n\n"
    yield "data: [DONE]\n\n"
