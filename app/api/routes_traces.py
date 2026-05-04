"""
GET /v1/traces/{trace_id} — return the structured trace for one pipeline turn.
"""

import json
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import TraceNotFoundError
from app.db.models import AgentTrace
from app.db.session import get_db

router = APIRouter(tags=["traces"])


class ToolCallRecord(BaseModel):
    tool_name: str
    args: dict
    result: Any


class TraceResponse(BaseModel):
    trace_id: str
    session_id: str
    routed_to: str
    tool_calls: list[ToolCallRecord]
    retrieved_chunk_ids: list[str]
    latency_ms: int
    idempotency_key: str | None = None


@router.get("/traces/{trace_id}", response_model=TraceResponse)
async def get_trace(
    trace_id: str,
    db: AsyncSession = Depends(get_db),
) -> TraceResponse:
    """Return trace for one turn. 404 if not found."""
    result = await db.execute(select(AgentTrace).where(AgentTrace.trace_id == trace_id))
    trace = result.scalar_one_or_none()
    if trace is None:
        raise TraceNotFoundError(f"Trace {trace_id} does not exist")

    tool_calls = _parse_tool_calls(trace.tool_calls)
    return TraceResponse(
        trace_id=trace.trace_id,
        session_id=trace.session_id,
        routed_to=trace.routed_to,
        tool_calls=tool_calls,
        retrieved_chunk_ids=trace.retrieved_chunk_ids,
        latency_ms=trace.latency_ms,
        idempotency_key=trace.idempotency_key,
    )


def _parse_tool_calls(tool_calls_data: str | list) -> list[ToolCallRecord]:
    """Parse tool_calls from DB - supports both JSON string and list."""
    if isinstance(tool_calls_data, str):
        if not tool_calls_data:
            return []
        calls = json.loads(tool_calls_data)
    else:
        calls = tool_calls_data or []
    return [
        ToolCallRecord(
            tool_name=call.get("tool_name", call.get("name", "")),
            args=call.get("args", {}),
            result=call.get("result"),
        )
        for call in calls
    ]
