"""
Vector store using Supabase pgvector.
"""

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool

from app.settings import settings


def _to_vector_str(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


@dataclass
class VectorStore:
    engine: Any

    async def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        async with self.engine.begin() as conn:
            for chunk_id, embedding, content, metadata in zip(
                ids, embeddings, documents, metadatas
            ):
                vec_str = _to_vector_str(embedding)
                metadata_json = json.dumps(metadata) if metadata else "{}"
                stmt = text(f"""
                    INSERT INTO embeddings (chunk_id, embedding, content, metadata)
                    VALUES (:chunk_id, CAST(:embedding AS vector(384)), :content, CAST(:metadata AS jsonb))
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        content = EXCLUDED.content,
                        metadata = EXCLUDED.metadata
                """)
                await conn.execute(
                    stmt,
                    {
                        "chunk_id": chunk_id,
                        "embedding": vec_str,
                        "content": content,
                        "metadata": metadata_json,
                    },
                )

    async def query(
        self,
        query_embedding: list[float],
        k: int,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        vec_str = _to_vector_str(query_embedding)
        async with self.engine.begin() as conn:
            result = await conn.execute(
                text("""
                    SELECT chunk_id, 1 - (embedding <=> CAST(:query_embedding AS vector(384))) as score, content, metadata
                    FROM embeddings
                    ORDER BY embedding <=> CAST(:query_embedding AS vector(384))
                    LIMIT :k
                """),
                {"query_embedding": vec_str, "k": k},
            )
            rows = result.fetchall()
            return {
                "ids": [[r.chunk_id for r in rows]],
                "distances": [[1 - r.score for r in rows]],
                "documents": [[r.content for r in rows]],
                "metadatas": [[r.metadata for r in rows]],
            }

    async def close(self) -> None:
        await self.engine.dispose()


_engine = None


def get_vector_store() -> VectorStore:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            poolclass=NullPool,
            echo=False,
        )
    return VectorStore(engine=_engine)
