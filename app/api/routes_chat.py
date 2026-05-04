"""
POST /v1/chat/{session_id} — send a user message, get assistant reply.
"""

import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentTrace, Message
from app.db.session import get_db
from app.srop import pipeline

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    routed_to: str  # which sub-agent handled this turn
    trace_id: str


async def _sse_stream(
    content: str,
    trace_id: str,
) -> AsyncIterator[str]:
    """Stream content as SSE events."""
    for char in content:
        yield f"data: {json.dumps({'token': char})}\n\n"
    data = {"done": True, "trace_id": trace_id}
    yield f"data: {json.dumps(data)}\n\n"


@router.post("/chat/{session_id}", response_model=None)
async def chat(
    session_id: str,
    body: ChatRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse | StreamingResponse:
    """
    Run one turn of the SROP pipeline.

    If Accept: text/event-stream, streams response as SSE.
    Otherwise returns JSON response.

    Error cases:
    - Session not found → 404
    - LLM timeout → 504
    """
    accept = request.headers.get("Accept", "")

    if idempotency_key:
        existing = await db.execute(
            select(AgentTrace)
            .where(AgentTrace.idempotency_key == idempotency_key)
            .where(AgentTrace.session_id == session_id)
        )
        existing_trace = existing.scalar_one_or_none()
        if existing_trace:
            msg_result = await db.execute(
                select(Message)
                .where(Message.trace_id == existing_trace.trace_id)
                .where(Message.role == "assistant")
            )
            existing_msg = msg_result.scalar_one_or_none()
            if existing_msg:
                if "event-stream" in accept:
                    return StreamingResponse(
                        _sse_stream(existing_msg.content, existing_trace.trace_id),
                        media_type="text/event-stream",
                    )
                return ChatResponse(
                    reply=existing_msg.content,
                    routed_to=existing_trace.routed_to,
                    trace_id=existing_trace.trace_id,
                )

    result = await pipeline.run(session_id, body.message, idempotency_key, db)

    if "event-stream" in accept:
        return StreamingResponse(
            _sse_stream(result.content, result.trace_id),
            media_type="text/event-stream",
        )

    return ChatResponse(
        reply=result.content,
        routed_to=result.routed_to,
        trace_id=result.trace_id,
    )
