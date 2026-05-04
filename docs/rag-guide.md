---
title: RAG (Retrieval-Augmented Generation) — Concepts and Implementation Guide
product_area: reference
tags: [rag, embeddings, vector-store, chunking, retrieval]
---

# RAG: Retrieval-Augmented Generation

This guide explains the concepts behind RAG and what you need to implement for this assignment. Read it fully before writing code.

---

## What is RAG?

An LLM has a fixed knowledge cutoff. It cannot know your product docs, your company's specific processes, or private data. RAG solves this by:

1. **At ingest time:** converting your documents into vector embeddings and storing them in a vector database.
2. **At query time:** embedding the user's question, finding the most similar document chunks, and injecting them into the LLM's prompt as context.

The LLM then answers using its reasoning ability + the retrieved context, not just training data.

```
User query
    │
    ▼
[Embedding model] → query vector
    │
    ▼
[Vector store] → top-k similar chunks (with IDs + scores)
    │
    ▼
[Prompt assembly]
  "Answer using ONLY this context:
   <chunk 1>
   <chunk 2>
   ...
   User question: {query}"
    │
    ▼
[LLM] → grounded answer with citations
```

---

## Step 1: Chunking

Raw documents are too long to fit in a prompt (and retrieval quality degrades with huge chunks). You must split them first.

### Why chunking matters

- **Too large:** retrieval returns the whole doc → irrelevant noise in prompt → worse answers
- **Too small:** chunks lose context → no sentence makes sense in isolation

### Chunking strategies (choose one, justify in README)

#### A. Fixed-size character chunking
Simple: split every N characters, with M characters overlap between consecutive chunks.

```python
def chunk_fixed(text: str, size: int = 512, overlap: int = 64) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return chunks
```

**Pro:** fast, simple. **Con:** breaks mid-sentence, mid-word, or mid-code-block.

#### B. Sentence-aware chunking
Split on sentence boundaries, accumulate until chunk_size reached, then start new chunk.

```python
import re

def chunk_sentences(text: str, max_chars: int = 512, overlap_sentences: int = 1) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current, current_len = [], [], 0
    for sentence in sentences:
        if current_len + len(sentence) > max_chars and current:
            chunks.append(" ".join(current))
            current = current[-overlap_sentences:]  # keep last N sentences as overlap
            current_len = sum(len(s) for s in current)
        current.append(sentence)
        current_len += len(sentence)
    if current:
        chunks.append(" ".join(current))
    return chunks
```

**Pro:** chunks end on sentence boundaries → more coherent. **Con:** chunk sizes vary widely.

#### C. Heading-aware chunking (best for Markdown docs)
Split on `##` and `###` headings. Each section becomes one or more chunks.

```python
import re

def chunk_by_heading(text: str, max_chars: int = 800) -> list[str]:
    # Split on any markdown heading (## or ###)
    sections = re.split(r'\n(?=#{2,3} )', text)
    chunks = []
    for section in sections:
        if len(section) <= max_chars:
            chunks.append(section.strip())
        else:
            # Sub-chunk long sections by sentence
            chunks.extend(chunk_sentences(section, max_chars=max_chars))
    return [c for c in chunks if c.strip()]
```

**Pro:** preserves heading context, natural section boundaries. **Con:** sections vary wildly in size.

### Stable chunk IDs

Generate a deterministic ID so you can deduplicate on re-ingest:

```python
import hashlib

def make_chunk_id(file_path: str, chunk_index: int) -> str:
    raw = f"{file_path}::{chunk_index}"
    return "chunk_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
```

### Frontmatter extraction

The `docs/` folder uses YAML frontmatter. Extract it for metadata filtering:

```python
import re
import yaml

def extract_frontmatter(text: str) -> tuple[dict, str]:
    """Returns (metadata_dict, body_without_frontmatter)."""
    match = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
    if not match:
        return {}, text
    metadata = yaml.safe_load(match.group(1))
    body = text[match.end():]
    return metadata, body
```

---

## Step 2: Embeddings

An embedding model converts text → a dense vector (list of floats). Similar texts produce vectors that are close in vector space.

### Choosing an embedding model

| Model | Dimensions | Cost | How to use |
|-------|-----------|------|-----------|
| `text-embedding-004` (Google) | 768 | Free tier available | `google.generativeai.embed_content()` |
| `text-embedding-3-small` (OpenAI) | 1536 | $0.02/1M tokens | `openai.embeddings.create()` |
| `all-MiniLM-L6-v2` (local) | 384 | Free | `sentence_transformers.SentenceTransformer` |

**Important:** use the same model at ingest time and query time. Mixing models produces garbage results.

### Embedding at ingest (Google example)

```python
import google.generativeai as genai

genai.configure(api_key=GOOGLE_API_KEY)

def embed_texts(texts: list[str]) -> list[list[float]]:
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=texts,
        task_type="retrieval_document",  # use retrieval_query at query time
    )
    return result["embedding"]
```

### Embedding at query time

```python
def embed_query(query: str) -> list[float]:
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=query,
        task_type="retrieval_query",  # different task type — important for quality
    )
    return result["embedding"]
```

### Batching

Embed in batches to avoid rate limits:

```python
async def embed_in_batches(texts: list[str], batch_size: int = 20) -> list[list[float]]:
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings.extend(embed_texts(batch))
    return embeddings
```

---

## Step 3: Vector Store

Stores embeddings and supports similarity search. You choose one.

### Option A: ChromaDB (easiest to start)

```python
import chromadb

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(
    name="helix_docs",
    metadata={"hnsw:space": "cosine"},  # cosine similarity
)

# Upsert chunks
collection.upsert(
    ids=["chunk_abc123", "chunk_def456"],
    embeddings=[[0.1, 0.2, ...], [0.3, 0.4, ...]],
    documents=["chunk text 1", "chunk text 2"],
    metadatas=[
        {"product_area": "security", "source": "deploy-keys.md", "title": "Deploy Keys"},
        {"product_area": "ci-cd", "source": "builds.md", "title": "Builds"},
    ],
)

# Query
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=5,
    where={"product_area": "security"},  # metadata filter (optional)
)
# results["ids"][0] → list of chunk IDs
# results["distances"][0] → cosine distances (lower = more similar)
# results["documents"][0] → chunk texts
```

Convert distance to score (0=bad, 1=perfect):
```python
score = 1 - distance  # for cosine distance
```

### Option B: LanceDB (good for hybrid search)

```python
import lancedb
import pyarrow as pa

db = lancedb.connect("./lancedb")

schema = pa.schema([
    pa.field("chunk_id", pa.string()),
    pa.field("text", pa.string()),
    pa.field("product_area", pa.string()),
    pa.field("source", pa.string()),
    pa.field("vector", pa.list_(pa.float32(), 768)),
])

table = db.create_table("helix_docs", schema=schema, mode="overwrite")
table.add([{"chunk_id": ..., "text": ..., "vector": ..., ...}])

# Search
results = table.search(query_embedding).limit(5).to_list()
```

### Option C: FAISS (pure in-memory, no persistence without extra code)

```python
import faiss
import numpy as np

dimension = 768
index = faiss.IndexFlatIP(dimension)  # inner product (= cosine if vectors normalized)

# Add vectors
vectors = np.array(embeddings, dtype=np.float32)
faiss.normalize_L2(vectors)
index.add(vectors)

# Search
query_vec = np.array([query_embedding], dtype=np.float32)
faiss.normalize_L2(query_vec)
distances, indices = index.search(query_vec, k=5)
```

FAISS has no built-in persistence — save/load manually:
```python
faiss.write_index(index, "helix.index")
index = faiss.read_index("helix.index")
```

---

## Step 4: Retrieval and Citation

At query time:

```python
async def search_docs(query: str, k: int = 5, product_area: str | None = None) -> list[DocChunk]:
    query_embedding = embed_query(query)

    # Build metadata filter
    where = {"product_area": product_area} if product_area else None

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        where=where,
    )

    chunks = []
    for chunk_id, distance, doc, meta in zip(
        results["ids"][0],
        results["distances"][0],
        results["documents"][0],
        results["metadatas"][0],
    ):
        chunks.append(DocChunk(
            chunk_id=chunk_id,
            score=round(1 - distance, 4),
            content=doc,
            metadata=meta,
        ))

    return sorted(chunks, key=lambda c: c.score, reverse=True)
```

### Injecting into the agent prompt

The KnowledgeAgent's system instruction should tell it how to use retrieved context:

```
You are a Helix product knowledge agent.
Answer questions using ONLY the provided context chunks.
Always cite the chunk_id (e.g. "According to [chunk_abc123]...").
If the context does not contain the answer, say so — do not guess.
```

The tool call result should format the chunks clearly:

```python
def format_chunks_for_agent(chunks: list[DocChunk]) -> str:
    parts = []
    for chunk in chunks:
        parts.append(
            f"[{chunk.chunk_id}] (score: {chunk.score:.2f}, source: {chunk.metadata.get('source')})\n"
            f"{chunk.content}"
        )
    return "\n\n---\n\n".join(parts)
```

---

## Step 5: Quality Considerations

### Score threshold
Filter out low-quality results:
```python
SCORE_THRESHOLD = 0.6  # discard chunks below this
chunks = [c for c in chunks if c.score >= SCORE_THRESHOLD]
```

### What to do when no chunks pass threshold
The agent should say "I don't have documentation on that" rather than hallucinating. Design your prompt to enforce this.

### Reranking (Extension E3)
Two-stage retrieval:
1. Retrieve top-20 candidates cheaply (vector search)
2. Rerank with a cross-encoder or LLM-as-judge, return top-5

```python
# LLM-as-judge reranker example
async def rerank(query: str, chunks: list[DocChunk], top_k: int = 5) -> list[DocChunk]:
    prompt = f"""
    Query: {query}
    
    Rank these chunks by relevance (most relevant first). Return only chunk IDs, comma-separated.
    
    Chunks:
    {format_chunks_for_agent(chunks)}
    """
    # call LLM, parse ordered IDs, return reordered chunks
    ...
```

---

## What You Must Build

For this assignment, implement:

1. **`app/rag/ingest.py`** — CLI that reads `docs/*.md`, chunks, embeds, writes to vector store
2. **`app/agents/tools/search_docs.py`** — async function callable by KnowledgeAgent
3. Embed using Google's `text-embedding-004` (or any embedding model — justify choice)
4. Vector store: Chroma recommended (simplest), but any works
5. Chunk IDs must be stable and included in retrieval results
6. Scores must be in [0, 1] and included in results

**Test it:**
```bash
python -m app.rag.ingest --path docs/
# Should print: "Found N markdown files, ingested X chunks"

# Then in Python:
from app.agents.tools.search_docs import search_docs
import asyncio
results = asyncio.run(search_docs("how to rotate a deploy key", k=3))
for r in results:
    print(r.chunk_id, r.score, r.content[:80])
```
