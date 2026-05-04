"""
CLI utility for ingesting documentation into the vector store.
Supports markdown files with frontmatter extraction and chunking.
"""
import argparse
import asyncio
import hashlib
import re
from pathlib import Path

from app.rag.embeddings import embed_documents
from app.rag.vector_store import get_vector_store


def _extract_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    frontmatter = text[4:end]
    body = text[end + 5 :]
    metadata: dict[str, str | list[str]] = {}
    for line in frontmatter.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if value.startswith("[") and value.endswith("]"):
            items = [item.strip() for item in value[1:-1].split(",") if item.strip()]
            metadata[key] = items
        else:
            metadata[key] = value
    return metadata, body


def _chunk_sentences(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        if not sentence:
            continue
        if current and current_len + len(sentence) > max_chars:
            chunks.append(" ".join(current).strip())
            overlap: list[str] = []
            overlap_len = 0
            for prev in reversed(current):
                overlap.insert(0, prev)
                overlap_len += len(prev)
                if overlap_len >= overlap_chars:
                    break
            current = overlap
            current_len = sum(len(s) for s in current)
        current.append(sentence)
        current_len += len(sentence)
    if current:
        chunks.append(" ".join(current).strip())
    return [c for c in chunks if c]


def chunk_markdown(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    """
    Split markdown text into overlapping chunks.

    Design considerations:
    - Simple character splitting is fast but breaks mid-sentence.
    - Sentence-aware splitting is better for retrieval quality.
    - Heading-aware splitting (split on ## / ###) keeps sections coherent.
    - Overlap helps preserve context at chunk boundaries.

    Choose an approach and document why in the README.
    """
    _, body = _extract_frontmatter(text)
    sections = re.split(r"\n(?=#{2,3} )", body.strip())
    chunks: list[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= chunk_size:
            chunks.append(section)
        else:
            chunks.extend(_chunk_sentences(section, max_chars=chunk_size, overlap_chars=overlap))
    return [c for c in chunks if c.strip()]


def extract_metadata(file_path: Path, text: str) -> dict:
    """
    Extract metadata from a markdown file's frontmatter.

    Expected frontmatter format:
        ---
        title: Deploy Keys
        product_area: security
        tags: [keys, secrets]
        ---

    Returns a dict suitable for vector store metadata filtering.
    """
    metadata, _ = _extract_frontmatter(text)
    title = metadata.get("title") or file_path.stem.replace("-", " ").title()
    product_area = metadata.get("product_area") or "general"
    return {
        "title": title,
        "product_area": product_area,
        "tags": metadata.get("tags", []),
        "source": file_path.name,
    }


async def ingest_directory(docs_path: Path, chunk_size: int, chunk_overlap: int) -> None:
    """
    Walk docs_path, chunk and embed every .md file, upsert into vector store.

    Design considerations:
    - Generate a stable chunk_id (e.g. sha256(file + chunk_index)) for deduplication.
    - Run embeddings in batches to avoid rate limiting.
    - Print progress so the user can see what's happening.
    """
    md_files = sorted(docs_path.rglob("*.md"))
    print(f"Found {len(md_files)} markdown files in {docs_path}")

    store = get_vector_store()
    total_chunks = 0

    for file_path in md_files:
        text = file_path.read_text(encoding="utf-8")
        metadata = extract_metadata(file_path, text)
        chunks = chunk_markdown(text, chunk_size, chunk_overlap)
        print(f"  {file_path.name}: {len(chunks)} chunks")
        if not chunks:
            continue

        relative_path = file_path.relative_to(docs_path).as_posix()
        chunk_ids = [
            "chunk_" + hashlib.sha256(f"{relative_path}::{idx}".encode()).hexdigest()[:16]
            for idx in range(len(chunks))
        ]
        metadatas = [
            {
                **metadata,
                "path": relative_path,
                "chunk_index": idx,
            }
            for idx in range(len(chunks))
        ]

        embeddings: list[list[float]] = []
        batch_size = 20
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            embeddings.extend(await embed_documents(batch))

        await store.upsert(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )
        total_chunks += len(chunks)

    print(f"Ingest complete. Upserted {total_chunks} chunks.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest docs into the vector store")
    parser.add_argument("--path", type=Path, required=True, help="Directory containing .md files")
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--chunk-overlap", type=int, default=120)
    args = parser.parse_args()

    asyncio.run(ingest_directory(args.path, args.chunk_size, args.chunk_overlap))


if __name__ == "__main__":
    main()
