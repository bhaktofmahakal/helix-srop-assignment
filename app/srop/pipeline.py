"""
Main SROP Pipeline implementing the AgentTool pattern for routing.
Routes user queries to specialized sub-agents using LLM function calling.
"""

import asyncio
import json
import uuid
from time import monotonic
from typing import Any

import structlog
from sqlalchemy import select

from app.api.errors import SessionNotFoundError, UpstreamTimeoutError
from app.db.models import AgentTrace, Message, Session, User
from app.rag.vector_store import get_vector_store
from app.settings import get_active_llm_provider, settings
from app.srop.state import ConversationTurn, SessionState

log = structlog.get_logger()

# Sub-agent tool definitions for routing
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "knowledge_agent",
            "description": (
                "Route to this agent for Helix product questions about builds, "
                "deploys, webhooks, secrets, billing, documentation, deploy keys, "
                "CI/CD, runners, artifact registry, or any how-to question."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user's question about Helix products.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "account_agent",
            "description": (
                "Route to this agent for account-related queries like "
                "recent builds, plan tier, usage, or account status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The user ID to query.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of results to return.",
                        "default": 5,
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalation_agent",
            "description": "Route to this agent to create a support ticket when user needs help.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Brief description of the issue.",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Priority level.",
                        "default": "medium",
                    },
                },
                "required": ["summary"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are Helix AI Support Concierge. Your job is to route user queries to the correct specialist agent.

AVAILABLE AGENTS:
- knowledge_agent: For questions about Helix products (builds, deploys, webhooks, secrets, billing, docs, how-to, deploy keys, CI/CD, runners, artifact registry)
- account_agent: For account-related queries (my builds, my plan, my usage, my status)
- escalation_agent: To create support tickets when user wants to escalate

RULES:
- Always call exactly one agent tool to handle the query
- Do NOT answer directly — route to the appropriate agent
- For how-to questions or feature questions → knowledge_agent
- For "my builds", "my account", "my plan" questions → account_agent
- For "create ticket", "escalate", "I need help from a person" → escalation_agent

Examples:
- "How do I rotate a deploy key?" → knowledge_agent
- "Show my recent builds" → account_agent
- "I need to escalate this" → escalation_agent
"""


async def run(
    session_id: str, user_message: str, idempotency_key: str | None, db: Any
) -> "PipelineResult":
    """Run one turn of the SROP pipeline with ADK-style routing."""
    trace_id = str(uuid.uuid4())

    result = await db.execute(select(Session).where(Session.session_id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise SessionNotFoundError(f"Session {session_id} does not exist")

    state = SessionState.from_db_dict(session.state) if session.state else None
    if state is None:
        user_result = await db.execute(select(User).where(User.user_id == session.user_id))
        user = user_result.scalar_one_or_none()
        plan_tier = user.plan_tier if user else "free"
        state = SessionState(user_id=session.user_id, plan_tier=plan_tier)

    # Pre-flight guardrail check
    if _is_out_of_scope(user_message):
        return await _handle_guardrails(
            session_id, user_message, trace_id, state, idempotency_key, db
        )

    start_time = monotonic()
    try:
        routed_to, response_data, tool_calls, retrieved_chunk_ids = (
            await _route_with_adk_pattern(user_message, state)
        )
        latency_ms = int((monotonic() - start_time) * 1000)
    except asyncio.TimeoutError:
        raise UpstreamTimeoutError(
            f"LLM did not respond within {settings.llm_timeout_seconds}s"
        )

    if isinstance(response_data, dict):
        final_text = response_data.get("response", str(response_data))
    else:
        final_text = str(response_data)

    # Update session state
    state.turn_count += 1
    state.last_routed_to = routed_to
    state.last_retrieved_chunk_ids = retrieved_chunk_ids
    state.conversation_history.append(
        ConversationTurn(role="user", content=user_message)
    )
    state.conversation_history.append(
        ConversationTurn(role="assistant", content=final_text)
    )
    if len(state.conversation_history) > 20:
        state.conversation_history = state.conversation_history[-20:]

    # Persist state + messages + trace to DB
    session.state = state.to_db_dict()
    db.add(
        Message(
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            role="user",
            content=user_message,
            trace_id=trace_id,
        )
    )
    db.add(
        Message(
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            role="assistant",
            content=final_text,
            trace_id=trace_id,
        )
    )
    db.add(
        AgentTrace(
            trace_id=trace_id,
            session_id=session_id,
            routed_to=routed_to,
            tool_calls=json.dumps(tool_calls),
            retrieved_chunk_ids=retrieved_chunk_ids,
            latency_ms=latency_ms,
            idempotency_key=idempotency_key,
        )
    )
    await db.commit()

    log.info(
        "pipeline_complete",
        session_id=session_id,
        trace_id=trace_id,
        routed_to=routed_to,
        latency_ms=latency_ms,
    )
    return PipelineResult(content=final_text, routed_to=routed_to, trace_id=trace_id)


async def _route_with_adk_pattern(
    user_message: str, state: SessionState
) -> tuple[str, dict[str, str], list[dict[str, Any]], list[str]]:
    """
    Route using ADK-style function calling (AgentTool pattern).

    The LLM selects which sub-agent tool to call — we never parse
    the LLM's text output to decide routing.
    """
    provider = get_active_llm_provider()

    conversation_context = _build_context(state)

    if provider == "groq" and settings.groq_api_key:
        return await _route_with_groq(user_message, state, conversation_context)
    elif settings.google_api_key:
        return await _route_with_google(user_message, state, conversation_context)
    else:
        raise RuntimeError("No LLM API key configured. Set GROQ_API_KEY or GOOGLE_API_KEY.")


def _build_context(state: SessionState) -> str:
    """Build conversation context for the system prompt."""
    lines = [
        f"User: {state.user_id} (plan: {state.plan_tier})",
        f"Turn: {state.turn_count}",
    ]
    if state.last_routed_to:
        lines.append(f"Last agent: {state.last_routed_to}")
    if state.conversation_history:
        lines.append("Recent conversation:")
        for turn in state.conversation_history[-6:]:
            lines.append(f"  {turn.role}: {turn.content[:150]}")
    return "\n".join(lines)


async def _route_with_groq(
    user_message: str, state: SessionState, context: str
) -> tuple[str, dict[str, str], list[dict[str, Any]], list[str]]:
    """Route using Groq function calling (AgentTool pattern)."""
    from groq import AsyncGroq

    client = AsyncGroq(api_key=settings.groq_api_key)

    messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\nContext:\n{context}"},
        {"role": "user", "content": user_message},
    ]

    response = await asyncio.wait_for(
        client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            tools=AGENT_TOOLS,
            tool_choice="auto",
            temperature=0.3,
        ),
        timeout=settings.llm_timeout_seconds,
    )

    tool_calls = response.choices[0].message.tool_calls or []

    if not tool_calls:
        # No tool called — LLM responded directly (smalltalk)
        text = response.choices[0].message.content or "I'm here to help with Helix questions."
        return "smalltalk", {"response": text}, [], []

    tool_call = tool_calls[0]
    agent_name = tool_call.function.name
    args = json.loads(tool_call.function.arguments or "{}")

    return await _dispatch_agent(agent_name, args, user_message, state)


async def _route_with_google(
    user_message: str, state: SessionState, context: str
) -> tuple[str, dict[str, str], list[dict[str, Any]], list[str]]:
    """Route using Google GenerativeAI function calling."""
    import google.generativeai as genai

    genai.configure(api_key=settings.google_api_key)

    model = genai.GenerativeModel(
        model_name=settings.adk_model,
        system_instruction=f"{SYSTEM_PROMPT}\n\nContext:\n{context}",
        tools=AGENT_TOOLS,
    )

    response = await asyncio.wait_for(
        model.generate_content_async(user_message),
        timeout=settings.llm_timeout_seconds,
    )

    tool_calls = (
        response.candidates[0].content.parts[0].function_calls
        if hasattr(response, "candidates") and response.candidates
        else []
    )

    if not tool_calls:
        text = response.text if hasattr(response, "text") else "I'm here to help with Helix questions."
        return "smalltalk", {"response": text}, [], []

    tool_call = tool_calls[0]
    agent_name = tool_call.name
    args = dict(tool_call.args) if hasattr(tool_call, "args") else {}

    return await _dispatch_agent(agent_name, args, user_message, state)


async def _dispatch_agent(
    agent_name: str,
    args: dict[str, Any],
    user_message: str,
    state: SessionState,
) -> tuple[str, dict[str, str], list[dict[str, Any]], list[str]]:
    """Dispatch to the correct sub-agent based on tool call."""
    log.info("agent_dispatched", agent=agent_name, args=args)

    if agent_name == "knowledge_agent":
        result, chunk_ids = await _execute_knowledge_agent(
            args.get("query", user_message)
        )
        return (
            "knowledge",
            {"response": result},
            [{"tool_name": agent_name, "args": args, "result": "routed"}],
            chunk_ids,
        )

    elif agent_name == "account_agent":
        result = await _execute_account_agent(
            args.get("user_id", state.user_id), args.get("limit", 5)
        )
        return (
            "account",
            {"response": result},
            [{"tool_name": agent_name, "args": args, "result": "routed"}],
            [],
        )

    elif agent_name == "escalation_agent":
        result = await _execute_escalation_agent(
            args.get("summary", user_message),
            args.get("priority", "medium"),
            state.user_id
        )
        return (
            "escalation",
            {"response": result},
            [{"tool_name": agent_name, "args": args, "result": "routed"}],
            [],
        )

    log.warning("unknown_agent", agent=agent_name)
    return "smalltalk", {"response": "I'm here to help with Helix questions."}, [], []


async def _execute_knowledge_agent(query: str) -> tuple[str, list[str]]:
    """Execute knowledge agent: search docs via RAG and answer with citations."""
    store = get_vector_store()
    try:
        from app.rag.embeddings import embed_query

        query_embedding = await embed_query(query)
        results = await store.query(query_embedding, k=5)
        retrieved_chunk_ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]

        if not docs:
            return "I don't have documentation about that topic.", []

        # Build context with chunk IDs for citations
        context_parts: list[str] = []
        for chunk_id, doc in zip(retrieved_chunk_ids[:3], docs[:3]):
            context_parts.append(f"[{chunk_id}]: {doc[:500]}")
        context = "\n\n".join(context_parts)

        # Generate answer with citations using Groq
        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.groq_api_key)
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are Helix Support. Answer using ONLY the documentation below. "
                            "Cite sources by chunk_id in brackets, e.g. 'According to [chunk_abc123]...'. "
                            "If the answer is not in the docs, say so.\n\n"
                            f"{context}"
                        ),
                    },
                    {"role": "user", "content": query},
                ],
                temperature=0.3,
            ),
            timeout=settings.llm_timeout_seconds,
        )
        answer = response.choices[0].message.content or "No answer found."
        return answer, retrieved_chunk_ids

    except asyncio.TimeoutError:
        raise  # Let the outer handler catch this
    except Exception as exc:
        log.error("knowledge_agent_failed", error=str(exc), query=query[:100])
        return "I couldn't search documentation at this time. Please try again.", []


async def _execute_account_agent(user_id: str, limit: int) -> str:
    """Execute account agent: return mock build data."""
    from app.agents.tools.account_tools import get_account_status, get_recent_builds

    builds = await get_recent_builds(user_id, limit)
    status = await get_account_status(user_id)

    build_lines = "\n".join(
        f"  - {b.build_id}: {b.status} ({b.branch}, {b.pipeline}, {b.duration_seconds}s)"
        for b in builds
    )
    return (
        f"Account: {status.user_id} ({status.plan_tier} plan)\n"
        f"Builds: {status.concurrent_builds_used}/{status.concurrent_builds_limit} concurrent\n"
        f"Storage: {status.storage_used_gb}/{status.storage_limit_gb} GB\n\n"
        f"Recent {limit} builds:\n{build_lines}"
    )


async def _execute_escalation_agent(summary: str, priority: str, user_id: str) -> str:
    """Execute escalation agent: create a ticket and return its ID."""
    from app.agents.tools.ticket_tools import create_ticket

    result = await create_ticket(user_id=user_id, summary=summary, priority=priority)
    return f"Created ticket {result.ticket_id} (priority: {result.priority}, status: {result.status}). Summary: {summary[:80]}"


def _is_out_of_scope(message: str) -> bool:
    """Pre-flight guardrail: check if message is out of scope."""
    text = message.lower()
    in_scope = [
        "helix", "deploy", "build", "pipeline", "webhook", "secret",
        "billing", "plan", "ticket", "artifact", "oauth", "token",
        "runner", "ci", "cd", "registry", "scan", "key", "api",
        "account", "status", "usage",
    ]
    out_of_scope = [
        "poem", "story", "write me", "joke", "creative",
        "advice", "personal", "recipe", "weather",
    ]
    if any(k in text for k in in_scope):
        return False
    return any(k in text for k in out_of_scope)


async def _handle_guardrails(
    session_id: str,
    user_message: str,
    trace_id: str,
    state: SessionState,
    idempotency_key: str | None,
    db: Any,
) -> "PipelineResult":
    """Handle out-of-scope queries with a refusal message."""
    reply = _get_refusal_message(user_message)
    state.turn_count += 1
    state.last_routed_to = "guardrails"

    result = await db.execute(select(Session).where(Session.session_id == session_id))
    session = result.scalar_one()
    session.state = state.to_db_dict()

    db.add(
        Message(
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            role="user",
            content=user_message,
            trace_id=trace_id,
        )
    )
    db.add(
        Message(
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            role="assistant",
            content=reply,
            trace_id=trace_id,
        )
    )
    db.add(
        AgentTrace(
            trace_id=trace_id,
            session_id=session_id,
            routed_to="guardrails",
            tool_calls="[]",
            retrieved_chunk_ids=[],
            latency_ms=0,
            idempotency_key=idempotency_key,
        )
    )
    await db.commit()
    log.info("guardrails_refused", session_id=session_id, trace_id=trace_id)
    return PipelineResult(content=reply, routed_to="guardrails", trace_id=trace_id)


def _get_refusal_message(message: str) -> str:
    """Generate a refusal message for out-of-scope queries."""
    return (
        "I'm the Helix AI Support Concierge and can only help with "
        "Helix product questions — builds, deploy keys, billing, webhooks, "
        "CI/CD, runners, artifact registry, and support tickets. "
        "Please ask a Helix-related question."
    )


class PipelineResult:
    """Result of one pipeline turn."""

    def __init__(self, content: str, routed_to: str, trace_id: str) -> None:
        self.content = content
        self.routed_to = routed_to
        self.trace_id = trace_id


# Backward compatibility for tests — mock target
async def _run_groq_agent(
    user_message: str, state: SessionState
) -> tuple[str, str, list[str]]:
    """Compatibility wrapper for tests."""
    routed_to, response_data, _, retrieved_chunk_ids = await _route_with_adk_pattern(
        user_message, state
    )
    if isinstance(response_data, dict):
        final_text = response_data.get("response", str(response_data))
    else:
        final_text = str(response_data)
    return final_text, routed_to, retrieved_chunk_ids
