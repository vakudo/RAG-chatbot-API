import asyncio
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

REWRITE_PROMPT = """Given the conversation history and a follow-up question, \
rewrite the question as a single standalone search query that contains all the \
context needed to find the answer. Reply with the rewritten query only, no \
explanations, in the same language as the question.

History:
{history}

Follow-up question: {question}

Standalone query:"""

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


async def rewrite_question(question: str, history: list[dict], model: str) -> str:
    """Make short follow-ups ("how much?") searchable on their own."""
    lines = "\n".join(f"{m['role']}: {m['content']}" for m in history[-6:])
    try:
        resp = await get_client().chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": REWRITE_PROMPT.format(history=lines, question=question),
                }
            ],
            max_tokens=120,
            temperature=0,
        )
        rewritten = (resp.choices[0].message.content or "").strip().strip('"')
        return rewritten or question
    except Exception:
        return question


async def stream_answer(
    question: str,
    doc_ids: list[str] | None,
    history: list[dict],
    model: str | None = None,
) -> AsyncIterator[dict]:
    """Yields {"sources": [...]} once, then {"content": "..."} chunks."""
    llm = model or settings.llm_model

    search_query = question
    if history:
        search_query = await rewrite_question(question, history, llm)

    docs = await asyncio.to_thread(retrieve, search_query, doc_ids)

    sources = [
        {
            "doc_id": d.metadata.get("doc_id"),
            "filename": d.metadata.get("filename"),
            "chunk_index": d.metadata.get("chunk_index"),
            "snippet": d.page_content[:200],
        }
        for d in docs
    ]
    yield {"sources": sources}

    context = "\n\n---\n\n".join(d.page_content for d in docs)
    if not context:
        context = "(no relevant context found)"

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT.format(context=context)}]
        + [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
        + [{"role": "user", "content": question}]
    )

    stream = await get_client().chat.completions.create(
        model=llm, messages=messages, stream=True
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield {"content": delta}
