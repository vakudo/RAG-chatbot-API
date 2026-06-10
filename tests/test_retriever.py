from langchain_core.documents import Document

from backend import retriever


def _doc(doc_id: str, chunk: int, text: str) -> Document:
    return Document(
        page_content=text,
        metadata={"doc_id": doc_id, "chunk_index": chunk, "filename": "f.txt"},
    )


def test_rrf_merge_prefers_chunks_found_by_both_searches(monkeypatch):
    shared = _doc("d1", 0, "shared hit")
    vector_only = _doc("d1", 1, "vector hit")
    fulltext_only = _doc("d2", 0, "fulltext hit")

    class FakeStore:
        def similarity_search(self, q, k, filter=None):
            return [vector_only, shared]

    monkeypatch.setattr(retriever, "get_vectorstore", lambda: FakeStore())
    monkeypatch.setattr(
        retriever, "_fulltext_search", lambda q, ids, k: [fulltext_only, shared]
    )

    results = retriever.retrieve("query")

    assert results[0].page_content == "shared hit"
    contents = {d.page_content for d in results}
    assert contents == {"shared hit", "vector hit", "fulltext hit"}


def test_retrieve_deduplicates_by_doc_and_chunk(monkeypatch):
    a = _doc("d1", 0, "same chunk")
    b = _doc("d1", 0, "same chunk")

    class FakeStore:
        def similarity_search(self, q, k, filter=None):
            return [a]

    monkeypatch.setattr(retriever, "get_vectorstore", lambda: FakeStore())
    monkeypatch.setattr(retriever, "_fulltext_search", lambda q, ids, k: [b])

    results = retriever.retrieve("query")
    assert len(results) == 1
