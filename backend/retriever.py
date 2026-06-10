from functools import lru_cache

from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_postgres import PGVector

from backend.config import settings
from backend.db import connect


@lru_cache(maxsize=1)
def get_vectorstore() -> PGVector:
    return PGVector(
        embeddings=OllamaEmbeddings(
            model=settings.embed_model, base_url=settings.ollama_base_url
        ),
        collection_name=settings.collection_name,
        connection=settings.pg_conn,
        use_jsonb=True,
    )


def _fulltext_search(
    question: str, doc_ids: list[str] | None, k: int
) -> list[Document]:
    sql = """
        SELECT document, cmetadata
        FROM langchain_pg_embedding
        WHERE collection_id = (
            SELECT uuid FROM langchain_pg_collection WHERE name = %(collection)s
        )
        AND to_tsvector('simple', document)
            @@ websearch_to_tsquery('simple', %(q)s)
    """
    params = {"collection": settings.collection_name, "q": question}
    if doc_ids:
        sql += " AND cmetadata->>'doc_id' = ANY(%(doc_ids)s)"
        params["doc_ids"] = doc_ids
    sql += """
        ORDER BY ts_rank(
            to_tsvector('simple', document),
            websearch_to_tsquery('simple', %(q)s)
        ) DESC
        LIMIT %(k)s
    """
    params["k"] = k
    try:
        with connect() as conn:
            rows = conn.execute(sql, params).fetchall()
    except Exception:
        # tables may not exist yet before the first ingestion
        return []
    return [Document(page_content=r[0], metadata=r[1]) for r in rows]


def _chunk_key(doc: Document) -> tuple:
    return (doc.metadata.get("doc_id"), doc.metadata.get("chunk_index"))


def retrieve(question: str, doc_ids: list[str] | None = None) -> list[Document]:
    """Hybrid retrieval: vector + full-text, merged with reciprocal rank fusion."""
    pool = settings.top_k * 2
    doc_filter = {"doc_id": {"$in": doc_ids}} if doc_ids else None
    vector_hits = get_vectorstore().similarity_search(
        question, k=pool, filter=doc_filter
    )
    fulltext_hits = _fulltext_search(question, doc_ids, pool)

    scores: dict[tuple, float] = {}
    by_key: dict[tuple, Document] = {}
    for hits in (vector_hits, fulltext_hits):
        for rank, doc in enumerate(hits):
            key = _chunk_key(doc)
            by_key.setdefault(key, doc)
            scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank)

    ranked = sorted(scores, key=scores.get, reverse=True)
    return [by_key[key] for key in ranked[: settings.top_k]]
