---
title: FastAPI + Async Python — Patterns for This Assignment
product_area: reference
tags: [fastapi, async, sqlalchemy, pydantic, patterns]
---

# FastAPI + Async Python: Patterns for This Assignment

This guide covers the specific async patterns required. Assumes you know basic Python — focuses on the parts that trip people up.

---

## Why Async Matters Here

The SROP pipeline makes multiple I/O calls per request:
- LLM API call (300ms–3s)
- Vector store query (10–50ms)
- DB read/write (1–10ms)

If you use synchronous (blocking) code in an async handler, FastAPI's event loop is blocked — no other requests can be served while you wait. Under load, this causes request queuing and timeouts.

**Rule:** Everything that does I/O must be `async def` or run in a thread pool.

---

## FastAPI Basics

### App and router

```python
from fastapi import FastAPI, APIRouter

app = FastAPI()
router = APIRouter(prefix="/v1", tags=["sessions"])

@router.post("/sessions")
async def create_session(): ...

app.include_router(router)
```

### Request/response models with Pydantic v2

```python
from pydantic import BaseModel, Field
from typing import Literal

class CreateSessionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    plan_tier: Literal["free", "pro", "enterprise"] = "free"

class CreateSessionResponse(BaseModel):
    session_id: str
    user_id: str
```

Pydantic v2 validates on instantiation. If `user_id` is empty, FastAPI returns a 422 automatically — you don't write that check.

### Dependency injection

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db

@router.post("/sessions")
async def create_session(
    body: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),  # injected per-request
) -> CreateSessionResponse:
    ...
```

`get_db` is a generator that yields a session and closes it after the handler returns:

```python
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
        # session closes here, even on exception
```

### Headers as dependencies

```python
from fastapi import Header

@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    ...
```

---

## SQLAlchemy Async

### The async engine and session

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine("sqlite+aiosqlite:///./app.db")
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

`expire_on_commit=False` is important — without it, accessing model attributes after a commit raises `DetachedInstanceError`.

### Querying

```python
from sqlalchemy import select
from app.db.models import Session as SessionModel

async def get_session(session_id: str, db: AsyncSession) -> SessionModel | None:
    result = await db.execute(
        select(SessionModel).where(SessionModel.session_id == session_id)
    )
    return result.scalar_one_or_none()
```

### Creating

```python
import uuid
from app.db.models import Session as SessionModel

async def create_session(user_id: str, db: AsyncSession) -> SessionModel:
    session = SessionModel(
        session_id=str(uuid.uuid4()),
        user_id=user_id,
        state={},
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)  # reload from DB to get DB-generated fields
    return session
```

### Updating

```python
from sqlalchemy import update

await db.execute(
    update(SessionModel)
    .where(SessionModel.session_id == session_id)
    .values(state=new_state_dict, updated_at=datetime.utcnow())
)
await db.commit()
```

### Common mistake: using sync operations in async handlers

```python
# WRONG — blocks the event loop
@router.get("/sessions/{id}")
async def get_session(id: str, db: AsyncSession = Depends(get_db)):
    session = db.execute(select(Session).where(...))  # missing await
    return session.scalar_one()

# CORRECT
@router.get("/sessions/{id}")
async def get_session(id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(...))
    return result.scalar_one()
```

---

## Exception Handling and RFC 7807

RFC 7807 defines a standard format for HTTP error responses:

```json
{
  "type": "https://docs.helix.example/errors/session_not_found",
  "title": "SESSION_NOT_FOUND",
  "status": 404,
  "detail": "Session abc123 does not exist"
}
```

Define typed exceptions:

```python
class HelixError(Exception):
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    def __init__(self, detail: str = ""):
        self.detail = detail

class SessionNotFoundError(HelixError):
    status_code = 404
    error_code = "SESSION_NOT_FOUND"
```

Register a global handler in `main.py`:

```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(HelixError)
async def helix_error_handler(request: Request, exc: HelixError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": f"https://docs.helix.example/errors/{exc.error_code.lower()}",
            "title": exc.error_code,
            "status": exc.status_code,
            "detail": exc.detail,
        },
    )
```

Raise from handlers:
```python
session = await get_session(session_id, db)
if session is None:
    raise SessionNotFoundError(f"Session {session_id} does not exist")
```

---

## Idempotency Pattern

Idempotency prevents duplicate processing if a client retries a request (network glitch, timeout).

Pattern: store the `Idempotency-Key` in the `messages` table. On receipt of a request with a known key, return the stored response without re-running the pipeline.

```python
async def handle_idempotency(
    session_id: str,
    idempotency_key: str | None,
    db: AsyncSession,
) -> SendMessageResponse | None:
    """Return cached response if key already seen, else None."""
    if not idempotency_key:
        return None

    result = await db.execute(
        select(Message).where(
            Message.session_id == session_id,
            Message.idempotency_key == idempotency_key,
            Message.role == "assistant",
        )
    )
    cached = result.scalar_one_or_none()
    if cached:
        return SendMessageResponse(
            message_id=cached.message_id,
            content=cached.content,
            routed_to=cached.routed_to,  # you need to store this
            trace_id=cached.trace_id,
        )
    return None
```

**Race condition:** two simultaneous requests with the same key could both pass the check and both run the pipeline. For the assignment, a `UNIQUE` constraint on `idempotency_key` + catching the `IntegrityError` is sufficient:

```python
from sqlalchemy.exc import IntegrityError

try:
    await db.commit()
except IntegrityError:
    await db.rollback()
    # Key conflict — look up and return the existing response
    return await handle_idempotency(session_id, idempotency_key, db)
```

---

## Timeouts with asyncio

```python
import asyncio

async def call_with_timeout(coro, timeout_seconds: int):
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise UpstreamTimeoutError(f"Operation timed out after {timeout_seconds}s")
```

---

## Lifespan Events

Use `lifespan` for startup/shutdown logic (DB init, vector store loading):

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await load_vector_store()
    yield
    # Shutdown (cleanup if needed)
    await engine.dispose()

app = FastAPI(lifespan=lifespan)
```

---

## Testing Async FastAPI

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_healthz():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

Override dependencies in tests:
```python
app.dependency_overrides[get_db] = lambda: test_db_session
```

Restore after:
```python
app.dependency_overrides.clear()
```
