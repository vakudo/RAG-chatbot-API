from functools import lru_cache

from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_postgres import PGVector

from backend.config import settings


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


def retrieve(question: str, doc_id: str | None = None) -> list[Document]:
    doc_filter = {"doc_id": {"$eq": doc_id}} if doc_id else None
    return get_vectorstore().similarity_search(
        question, k=settings.top_k, filter=doc_filter
    )
