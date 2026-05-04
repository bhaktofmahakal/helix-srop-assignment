"""
Unit tests for RAG retrieval.
"""

import pytest

from app.rag.ingest import chunk_markdown


@pytest.mark.asyncio
async def test_search_docs_returns_results_with_chunk_ids(monkeypatch):
    """search_docs must return chunk IDs and scores in [0, 1]."""
    from app.rag import embeddings as embeddings_module
    from app.rag import vector_store as vector_store_module

    async def fake_embed_query(query: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    class FakeStore:
        async def query(self, query_embedding, k: int, where=None):
            return {
                "ids": [["chunk_test_001", "chunk_test_002"]],
                "distances": [[0.1, 0.4]],
                "documents": [["doc1", "doc2"]],
                "metadatas": [[{"source": "x"}, {"source": "y"}]],
            }

    monkeypatch.setattr(embeddings_module, "embed_query", fake_embed_query)
    monkeypatch.setattr(vector_store_module, "get_vector_store", lambda: FakeStore())

    from app.agents.tools.search_docs import search_docs

    results = await search_docs("rotate deploy key", k=3)
    assert len(results) > 0
    assert all(r.chunk_id for r in results)
    assert all(0.0 <= r.score <= 1.0 for r in results)


def test_chunker_produces_non_empty_chunks():
    """Chunker must not produce empty strings."""
    text = "# Header\n\nSome content.\n\n## Section 2\n\nMore content here."
    chunks = chunk_markdown(text, chunk_size=100, overlap=20)
    assert len(chunks) > 0
    assert all(c.strip() for c in chunks)
