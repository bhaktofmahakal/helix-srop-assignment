# Helix SROP — AI Support Concierge

## Setup (< 5 min)

```bash
git clone <your-repo>
cd helix-srop
pip install -e ".[dev]"
cp .env.example .env
# Set GROQ_API_KEY and DATABASE_URL in .env
python -m app.rag.ingest --path docs/
uvicorn app.main:app --reload
```

### LLM Provider

| Provider | Key | Model |
|----------|-----|-------|
| **Groq** (primary) | `GROQ_API_KEY` | llama-3.3-70b-versatile |
| Gemini (optional) | `GOOGLE_API_KEY` | gemini-2.0-flash |

Set `LLM_PROVIDER=auto` (default) — uses whichever key is configured.

## Architecture

```
POST /v1/chat/{session_id}
         │
         ▼
┌─────────────────────────┐
│  SROP Pipeline          │
│  1. Load session state  │ ← SQLAlchemy async (Supabase PostgreSQL)
│  2. Guardrails pre-check│ ← E5: out-of-scope refusal
│  3. Route via AgentTool │ ← LLM function calling (not string parsing)
│  4. Execute sub-agent   │
│  5. Save state + trace  │ ← Survives process restart
└────────────┬────────────┘
             │ routes via tool selection
       ┌─────┼──────────┐
       ▼     ▼          ▼
 Knowledge  Account  Escalation
 Agent      Agent    Agent
   │          │         │
Vector DB   Mock DB   Tickets DB
(pgvector)  (seeded)  (Supabase)
```

### State Persistence Design Decision

**Pattern chosen:** Session state serialized as JSON in `sessions.state` column.

**Why:** This is the simplest pattern that satisfies the hard requirement of surviving process restarts. State is loaded from DB at the start of each turn and saved back after the turn completes. No in-memory caching — every turn hits the DB. This trades latency for correctness and simplicity.

**Alternatives considered:**
- ADK's built-in session service → requires Gemini, tied to Google infrastructure
- Redis-backed state → adds operational complexity for a single-instance app
- Hybrid (DB + in-memory cache) → risk of stale state on restart

### Why Supabase pgvector instead of ChromaDB

**Decision:** We use Supabase PostgreSQL with pgvector for the vector store instead of the recommended ChromaDB.

**Rationale:**
1. **Deployment-ready** — Supabase provides a managed, always-on PostgreSQL instance. No local file persistence to manage.
2. **Single DB** — Both application data (sessions, messages, traces) and vector embeddings live in the same database. Simpler operations.
3. **pgvector is production-grade** — Used by companies like Supabase, Neon, and Vercel for production RAG systems.
4. **No cold-start** — ChromaDB's persistent mode requires local disk and re-loads indices on startup. pgvector is always warm.

**Tradeoff:** Requires a Supabase project (free tier works). For local-only dev, you could swap `DATABASE_URL` to SQLite and use ChromaDB.

### Chunking Strategy

**Strategy:** Heading-aware + sentence-boundary splitting with overlap.

**Why:** Markdown docs have natural section boundaries at `##` and `###` headings. Splitting at these boundaries keeps related content together (e.g., all steps for "rotating a deploy key" stay in one chunk). For sections exceeding `chunk_size`, we fall back to sentence-boundary splitting with overlap to preserve context at chunk edges.

**Parameters:** `chunk_size=800` chars, `overlap=120` chars. These values balance retrieval precision (smaller chunks) with context completeness (larger chunks).

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/sessions` | Create session. Body: `{user_id, plan_tier}` → `{session_id}` |
| `POST` | `/v1/chat/{session_id}` | Send message. Body: `{message}` → `{reply, routed_to, trace_id}` |
| `GET` | `/v1/traces/{trace_id}` | Get structured trace for debugging |
| `GET` | `/healthz` | Health check |

## Quick Test (Local)

```bash
SESSION=$(curl -s -X POST localhost:8000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_id": "u_demo", "plan_tier": "pro"}' | jq -r .session_id)

curl -s -X POST localhost:8000/v1/chat/$SESSION \
  -H "Content-Type: application/json" \
  -d '{"message": "How do I rotate a deploy key?"}' | jq .
```

For live API testing, see the [Live Demo & Testing](#live-demo--testing) section.

## Extensions Implemented

### E1: Idempotency (6 pts)
- `Idempotency-Key` header on `POST /v1/chat/{session_id}`
- Replay returns cached response from DB — pipeline runs once
- Stored in `agent_traces.idempotency_key` column

### E2: Escalation Agent (5 pts)
- Third sub-agent: `create_ticket(user_id, summary, priority)`
- Writes to `tickets` table, returns ticket_id
- Ticket ID available in session state for follow-ups

### E3: Streaming SSE (5 pts)
- `Accept: text/event-stream` on POST /v1/chat returns SSE
- Streams tokens as `data: {"token": "..."}`
- Final event: `data: {"done": true, "trace_id": "..."}`

### E4: Reranking (4 pts)
- LLM-as-judge reranker using Groq after vector search
- Reorders chunks by relevance, latency tracked in trace
- Enable via `enable_rerank=True` in search_docs

### E5: Guardrails + PII Redaction (4 pts)
- Pre-flight refusal for out-of-scope queries (poems, stories, personal advice)
- PII redaction in structured logs (emails, phones, SSNs, credit cards, API keys)
- Test: `test_guardrails_refuse_out_of_scope`

### E6: Docker (3 pts)
- `Dockerfile` + `docker-compose.yml`
- `docker compose up` → health check passes

## Known Limitations

1. No TTL for idempotency keys — could grow unbounded in high-traffic
2. Reranker adds ~500ms latency (additional LLM call)
3. SSE streams character-by-character (could batch tokens for efficiency)
4. No rate limiting per plan tier
5. Session state JSON is not normalized (trades schema for simplicity)
6. Groq function calling occasionally returns text instead of tool call — handled gracefully as "smalltalk"

## Live Demo & Testing

The project is live at: [https://helix-srop-assignment.onrender.com](https://helix-srop-assignment.onrender.com)

### Testing the Live API

You can test the live deployment using `curl`. Note: The first request might take 30s due to Render's free tier cold start.

**1. Create a session:**
```bash
SESSION=$(curl -s -X POST https://helix-srop-assignment.onrender.com/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_id": "evaluator_live", "plan_tier": "pro"}' | jq -r .session_id)
echo "Session created: $SESSION"
```

**2. Ask a question:**
```bash
curl -s -X POST https://helix-srop-assignment.onrender.com/v1/chat/$SESSION \
  -H "Content-Type: application/json" \
  -d '{"message": "How do I rotate a deploy key?"}' | jq .
```

---

## Deployment (Render)

This project is configured for easy deployment on **Render.com** via Blueprints (`render.yaml`).

### Deployment Steps

1.  **Connect Repo:** Go to [Render.com](https://render.com), click **New → Web Service**, and connect your GitHub repository.
2.  **Render Blueprint:** Render will automatically detect the `render.yaml` file.
3.  **Configure Environment:** Add the following Environment Variables in the Render dashboard:
    - `DATABASE_URL`: Your Supabase connection string (`postgresql+asyncpg://...`)
    - `GROQ_API_KEY`: Your Groq API key.
    - `LLM_PROVIDER`: `auto`
4.  **Deploy:** Click **Create Web Service**.

### 🧊 Cold Start Fix

Render's free tier spins down after 15 minutes of inactivity, which causes a ~30s delay on the next request. For the evaluator to have a smooth experience:

- **Keep-Alive Ping:** Use a service like [Cron-job.org](https://cron-job.org) to ping the `/healthz` endpoint every 10-14 minutes.
- **Fast Startup:** The Dockerfile is optimized with a pre-installed environment to ensure that even if a cold start occurs, the container is ready as fast as possible.


| Phase | Time |
|-------|------|
| Setup + DB + FastAPI boilerplate | 1.5h |
| RAG ingest + search_docs + pgvector | 1.5h |
| ADK agents + pipeline routing | 2h |
| State persistence + restart test | 1h |
| Extensions (E1-E6) | 2.5h |
| Tests + README | 1h |
| **Total** | **~9.5h** |