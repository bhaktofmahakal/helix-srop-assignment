---
title: Google ADK (Agent Development Kit) — Concepts and Implementation Guide
product_area: reference
tags: [adk, agents, tools, orchestration, google]
---

# Google Agent Development Kit (ADK)

This guide explains the ADK concepts you need for this assignment. You do not need any other reference — everything required is here.

Install: `pip install google-adk` (already in `pyproject.toml`).

---

## Core Concepts

### LlmAgent

The fundamental building block. An `LlmAgent` is an LLM + a system instruction + a set of tools it can call.

```python
from google.adk.agents import LlmAgent

agent = LlmAgent(
    name="my_agent",
    model="gemini-2.0-flash",          # or gemini-1.5-pro, etc.
    instruction="You are a helpful assistant that answers questions about Python.",
    tools=[my_tool_function],           # list of callable tools
)
```

### Tools

A tool is any Python function (sync or async) decorated or passed directly. ADK inspects the function signature and docstring to generate the tool schema for the LLM.

```python
def get_weather(city: str) -> str:
    """Get the current weather for a city. Returns a description string."""
    return f"Sunny, 22°C in {city}"

agent = LlmAgent(name="weather", model="gemini-2.0-flash", tools=[get_weather])
```

**Important:** the function's docstring becomes the tool description. Write clear docstrings — the LLM uses them to decide when to call the tool.

**Async tools work too:**
```python
async def search_database(query: str, limit: int = 10) -> list[dict]:
    """Search the database and return matching records."""
    ...
```

### AgentTool — sub-agents as tools

This is the key pattern for SROP. You wrap one `LlmAgent` as a tool callable by another:

```python
from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool

# Sub-agent
knowledge_agent = LlmAgent(
    name="knowledge",
    model="gemini-2.0-flash",
    instruction="Answer product questions using the search_docs tool. Always cite chunk IDs.",
    tools=[search_docs],
)

# Root orchestrator calls the sub-agent as a tool
root_agent = LlmAgent(
    name="root",
    model="gemini-2.0-flash",
    instruction="Route user queries to the correct specialist.",
    tools=[
        AgentTool(agent=knowledge_agent),
        AgentTool(agent=account_agent),
        AgentTool(agent=escalation_agent),
    ],
)
```

When the root agent calls `AgentTool(knowledge_agent)`, ADK runs the sub-agent with its own instruction and tools, then returns the result to the root agent. The LLM sees this as calling a "function" named `knowledge`.

**Why AgentTool instead of raw if/else?**
- Routing is handled by the LLM's tool-selection, not brittle string parsing
- Sub-agents have their own instruction scope (KnowledgeAgent doesn't see AccountAgent's tools)
- ADK handles the agent-to-agent call lifecycle

---

## Running an Agent

### InMemoryRunner (for single-turn or testing)

```python
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService
import asyncio

runner = InMemoryRunner(agent=root_agent)
session_service = InMemorySessionService()

async def run_once(user_message: str):
    session = await session_service.create_session(
        app_name="helix_srop",
        user_id="u_123",
    )
    response = await runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message={"role": "user", "parts": [{"text": user_message}]},
    )
    async for event in response:
        if event.is_final_response():
            return event.content.parts[0].text
```

### Persisting sessions across turns

For multi-turn conversations that survive process restarts, you need a persistent session store. ADK's built-in `InMemorySessionService` is lost on restart — you must implement your own or use the DB.

**Pattern 1: Store full message history in DB, reload on each turn**

```python
from google.adk.sessions import BaseSessionService, Session

class DatabaseSessionService(BaseSessionService):
    """Persists ADK sessions to your relational DB."""

    async def create_session(self, app_name: str, user_id: str, state: dict = None) -> Session:
        # Write session to DB, return ADK Session object
        ...

    async def get_session(self, app_name: str, user_id: str, session_id: str) -> Session | None:
        # Load from DB, reconstruct message history
        ...

    async def update_session(self, session: Session) -> None:
        # Persist updated session (new messages, updated state) to DB
        ...
```

**Pattern 2: Re-hydrate from message history stored in your DB**

On each turn:
1. Load all past `Message` rows for this session from your DB
2. Build a fresh ADK session with that history as prior turns
3. Run the agent
4. Persist the new messages back to DB

```python
async def run_with_history(session_id: str, user_message: str, db: AsyncSession):
    # Load history from DB
    messages = await load_messages(session_id, db)

    # Build ADK session with history
    adk_session = Session(
        id=session_id,
        user_id=...,
        turns=[
            {"role": m.role, "parts": [{"text": m.content}]}
            for m in messages
        ],
    )

    # Run agent
    runner = InMemoryRunner(agent=root_agent)
    response = await runner.run_async(
        session=adk_session,
        new_message={"role": "user", "parts": [{"text": user_message}]},
    )
    ...
```

**Pattern 3: Store only SessionState in DB, pass as system context**

The lightest approach: don't try to persist full ADK session. Instead, load `SessionState` from DB and inject it into the agent's instruction at runtime:

```python
async def run_turn(session_id: str, user_message: str, db: AsyncSession):
    state = await load_session_state(session_id, db)

    # Dynamic instruction with user context
    instruction_with_context = f"""
    {ROOT_INSTRUCTION}

    Current user context:
    - user_id: {state.user_id}
    - plan_tier: {state.plan_tier}
    - open_tickets: {state.open_ticket_ids}
    - last_agent: {state.last_agent}
    """

    agent = LlmAgent(
        name="srop_root",
        model=settings.adk_model,
        instruction=instruction_with_context,
        tools=[...],
    )

    runner = InMemoryRunner(agent=agent)
    # run single-turn ...
    # update state and persist to DB
```

**Choose a pattern and document your choice in the README.** Each has tradeoffs around context window usage, consistency, and simplicity.

---

## Extracting Agent Decisions

For tracing, you need to know which sub-agent ran and what tools were called. ADK events give you this:

```python
async def run_and_trace(user_message: str):
    routed_to = None
    tool_calls = []

    response = await runner.run_async(
        user_id=..., session_id=...,
        new_message={"role": "user", "parts": [{"text": user_message}]},
    )

    async for event in response:
        # Tool call started
        if event.type == "tool_call":
            tool_calls.append({
                "tool_name": event.tool_name,
                "args": event.tool_args,
            })

        # Tool call result
        if event.type == "tool_result":
            # find the matching call and add result
            ...

        # Which agent produced the final response
        if event.is_final_response():
            # event.author is the agent name that produced this
            routed_to = event.author  # e.g. "knowledge", "account", "escalation"
            final_text = event.content.parts[0].text

    return final_text, routed_to, tool_calls
```

**Note:** ADK's event API may differ slightly by version. Check `google.adk.events` for available event types in your installed version. The pattern above is representative.

---

## Timeouts

Wrap ADK runs with `asyncio.wait_for`:

```python
import asyncio
from app.settings import settings
from app.api.errors import UpstreamTimeoutError

try:
    result = await asyncio.wait_for(
        runner.run_async(...),
        timeout=settings.llm_timeout_seconds,
    )
except asyncio.TimeoutError:
    raise UpstreamTimeoutError(f"LLM did not respond within {settings.llm_timeout_seconds}s")
```

---

## Retries

Use `tenacity` for retries on transient LLM errors (rate limits, 503s):

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import google.api_core.exceptions

@retry(
    retry=retry_if_exception_type((
        google.api_core.exceptions.ResourceExhausted,  # rate limit
        google.api_core.exceptions.ServiceUnavailable,
    )),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
)
async def run_with_retry(runner, **kwargs):
    return await runner.run_async(**kwargs)
```

---

## Model Selection

For the assignment, `gemini-2.0-flash` is recommended for all agents — it's fast and cheap during development. Use `gemini-1.5-pro` for better accuracy if you need it.

If you prefer OpenAI or Anthropic, ADK supports them via LiteLLM:

```python
# pip install litellm
from google.adk.models.lite_llm import LiteLlm

agent = LlmAgent(
    name="root",
    model=LiteLlm(model="openai/gpt-4o"),
    ...
)
```

Or for Anthropic:
```python
agent = LlmAgent(
    name="root",
    model=LiteLlm(model="anthropic/claude-3-5-sonnet-20241022"),
    ...
)
```

---

## Common Mistakes

| Mistake | Consequence | Fix |
|---------|-------------|-----|
| Same `name` for two agents | ADK collision, unpredictable routing | Use unique names: `srop_root`, `knowledge_agent`, etc. |
| Tool function with no docstring | LLM doesn't know when to call it | Always write a clear docstring |
| Tool returns None | Agent gets confused | Always return a meaningful value or raise an exception |
| Creating new LlmAgent per turn | High latency (object init overhead) | Create agents once at module load |
| Blocking I/O inside async tool | Freezes event loop | Use `asyncio.to_thread()` or async DB calls |
| Mixing sync and async tools | Some may not fire | Stick to one style (async recommended) |

---

## Minimal Working Example

```python
import asyncio
from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService

def add(a: int, b: int) -> int:
    """Add two numbers and return the result."""
    return a + b

agent = LlmAgent(name="math", model="gemini-2.0-flash", tools=[add])
runner = InMemoryRunner(agent=agent)
session_svc = InMemorySessionService()

async def main():
    session = await session_svc.create_session(app_name="test", user_id="u1")
    response = runner.run_async(
        user_id="u1",
        session_id=session.id,
        new_message={"role": "user", "parts": [{"text": "What is 17 + 25?"}]},
    )
    async for event in response:
        if event.is_final_response():
            print(event.content.parts[0].text)  # "42"

asyncio.run(main())
```

Run this to verify your ADK setup before building the full pipeline.
