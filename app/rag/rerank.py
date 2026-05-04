"""
Reranking module — LLM-as-judge reranker.

After search_docs returns top-k chunks, this module reorders them
by relevance to the user's query using an LLM as judge.
"""

import time
from dataclasses import dataclass

import structlog

from app.settings import settings

log = structlog.get_logger()


@dataclass
class DocChunk:
    chunk_id: str
    score: float
    content: str
    metadata: dict
    rerank_score: float | None = None
    rerank_latency_ms: int | None = None


async def rerank_chunks(
    query: str,
    chunks: list[DocChunk],
    model: str | None = None,
) -> tuple[list[DocChunk], int]:
    """
    Reorder chunks by relevance to the query using an LLM-as-judge.

    Args:
        query: the user's query
        chunks: list of DocChunk from search_docs (already sorted by vector similarity)
        model: optional model override (defaults to settings.groq_model)

    Returns:
        Tuple of (reordered chunks, reranker_latency_ms)
    """
    if not chunks or len(chunks) <= 1:
        return chunks, 0

    start_ms = int(time.monotonic() * 1000)

    prompt = _build_rerank_prompt(query, chunks)

    try:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.groq_api_key)
        response = await client.chat.completions.create(
            model=model or settings.groq_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        scores = _parse_rerank_scores(response.choices[0].message.content or "")
    except Exception as exc:
        log.warning("reranker_failed", error=str(exc), query=query[:100])
        return chunks, 0

    if len(scores) != len(chunks):
        log.warning("reranker_score_mismatch", expected=len(chunks), got=len(scores))
        return chunks, 0

    reranked = sorted(
        zip(chunks, scores),
        key=lambda x: x[1] if x[1] is not None else 0,
        reverse=True,
    )
    reranked_chunks = [chunk for chunk, score in reranked if score is not None and score > 0]
    missed_set = {id(chunk) for chunk, score in reranked if score is None or score == 0}
    reranked_chunks.extend(chunk for chunk in chunks if id(chunk) in missed_set)

    latency_ms = int(time.monotonic() * 1000) - start_ms
    return reranked_chunks, latency_ms


def _build_rerank_prompt(query: str, chunks: list[DocChunk]) -> str:
    lines = [
        f"Query: {query}",
        "",
        "Rate each document's relevance to the query from 0-10.",
        "Output ONLY a JSON list of scores, one per document.",
        "",
    ]
    for i, chunk in enumerate(chunks):
        lines.append(f"Doc {i}: {chunk.content[:200]}...")

    return "\n".join(lines)


def _parse_rerank_scores(text: str) -> list[float | None]:
    import json

    text = text.strip()
    if "[" not in text:
        return []

    try:
        start = text.find("[")
        end = text.rfind("]") + 1
        scores = json.loads(text[start:end])
        return [float(s) if isinstance(s, (int, float)) else None for s in scores]
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("rerank_score_parse_failed", error=str(exc))
        return []
