"""
search_docs tool — used by KnowledgeAgent.

Queries the vector store for relevant documentation chunks.
Returns chunk IDs, scores, and content so the agent can cite sources.

Optional LLM-as-judge reranking after initial vector search.
"""

from dataclasses import dataclass
from typing import Any

from app.rag.embeddings import embed_query
from app.rag.rerank import rerank_chunks
from app.rag.rerank import DocChunk as DocChunkBase
from app.rag.vector_store import get_vector_store


class DocChunk(DocChunkBase):
    """DocChunk with vector search scores."""

    pass


async def search_docs(
    query: str,
    k: int = 5,
    product_area: str | None = None,
    enable_rerank: bool = False,
) -> list[DocChunk]:
    """
    Search the vector store for top-k relevant chunks.

    Args:
        query: natural language query from the user
        k: number of chunks to return
        product_area: optional metadata filter (e.g. "security", "ci-cd")
        enable_rerank: whether to apply LLM-as-judge reranking

    Returns:
        List of DocChunk ordered by descending similarity score.
        If enable_rerank=True, includes rerank_score and rerank_latency_ms.
    """
    store = get_vector_store()
    query_embedding = await embed_query(query)
    where = {"product_area": product_area} if product_area else None

    results = await store.query(query_embedding=query_embedding, k=k, where=where)
    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    chunks: list[DocChunk] = []
    for chunk_id, distance, doc, meta in zip(ids, distances, documents, metadatas):
        score = max(0.0, min(1.0, 1.0 - float(distance)))
        chunks.append(DocChunk(chunk_id=chunk_id, score=score, content=doc, metadata=meta))

    chunks = sorted(chunks, key=lambda c: c.score, reverse=True)
    score_threshold = 0.6
    filtered = [c for c in chunks if c.score >= score_threshold]

    if enable_rerank and filtered:
        reranked, latency_ms = await rerank_chunks(query, filtered)
        for chunk in reranked:
            chunk.rerank_latency_ms = latency_ms
            chunk.rerank_score = chunk.score
        return reranked

    return filtered
