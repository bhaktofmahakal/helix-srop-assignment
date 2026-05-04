"""
LLM provider abstraction — supports Gemini (via google-adk) or Groq (llama-3.3-70b).

If LLM_PROVIDER=gemini or GOOGLE_API_KEY is set → use google-adk with Gemini
If LLM_PROVIDER=groq or only GROQ_API_KEY is set → use Groq SDK
If LLM_PROVIDER=auto → prefer Gemini if key present, else Groq

Raises ConfigurationError at startup if neither key is set.
"""

from enum import Enum
from typing import Any, AsyncIterator

import structlog
from app.api.errors import HelixError
from app.settings import settings

log = structlog.get_logger()


class ConfigurationError(HelixError):
    status_code = 500
    error_code = "CONFIGURATION_ERROR"


class LLMProvider(Enum):
    GEMINI = "gemini"
    GROQ = "groq"
    AUTO = "auto"


def get_provider() -> LLMProvider:
    provider_str = settings.llm_provider.lower().strip()

    if provider_str == "gemini":
        return LLMProvider.GEMINI
    if provider_str == "groq":
        return LLMProvider.GROQ

    has_google = bool(settings.google_api_key)
    has_groq = bool(settings.groq_api_key)

    if has_google or (provider_str == "auto" and has_google):
        return LLMProvider.GEMINI
    if has_groq or (provider_str == "auto" and not has_google and has_groq):
        return LLMProvider.GROQ

    raise ConfigurationError(
        "No LLM API key configured. Set GOOGLE_API_KEY (Gemini) or GROQ_API_KEY in .env"
    )


def is_gemini() -> bool:
    return get_provider() == LLMProvider.GEMINI


def is_groq() -> bool:
    return get_provider() == LLMProvider.GROQ


async def get_chat_response(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> tuple[str, str | None]:
    """
    Get chat completion with function calling support.

    Args:
        messages: [{"role": "user" | "assistant", "content": str}]
        tools: JSON schema for tools (OpenAI-compatible format)

    Returns:
        (response_text, tool_call_json or None)
    """
    if is_gemini():
        return _gemini_chat(messages, tools)
    return _groq_chat(messages, tools)


async def _gemini_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> tuple[str, str | None]:
    import google.adk.runners
    from google.adk.agents import LlmAgent
    from google.adk.tools.function_tool import FunctionTool
    from app.agents.orchestrator import build_root_agent
    from app.srop.state import SessionState

    agent = build_root_agent(SessionState(user_id="", plan_tier=""))
    runner = google.adk.runners.InMemoryRunner(agent=agent)

    response = runner.run_async(
        user_id="",
        session_id="",
        new_message={"role": "user", "parts": [{"text": messages[-1]["content"]}]},
    )

    text = ""
    tool_call = None
    async for event in response:
        if event.is_final_response():
            content = getattr(event, "content", None)
            if content and getattr(content, "parts", None):
                text = content.parts[0].text or ""
    return text, tool_call


async def _groq_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> tuple[str, str | None]:
    from groq import AsyncGroq

    client = AsyncGroq(api_key=settings.groq_api_key)

    response = await client.chat.completions.create(
        model=settings.groq_model,
        messages=messages,
        tools=tools,
        tool_choice="auto" if tools else None,
        temperature=0.7,
    )

    message = response.choices[0].message
    text = message.content or ""

    tool_calls = getattr(message, "tool_calls", None)
    tool_call_json = None
    if tool_calls:
        tool_call_json = str(tool_calls)

    return text, tool_call_json


async def stream_chat_response(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    """Stream tokens from the LLM."""
    if is_gemini():
        async for token in _stream_gemini(messages, tools):
            yield token
    else:
        async for token in _stream_groq(messages, tools):
            yield token


async def _stream_gemini(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    yield ""


async def _stream_groq(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    from groq import AsyncGroq

    client = AsyncGroq(api_key=settings.groq_api_key)

    stream = await client.chat.completions.create(
        model=settings.groq_model,
        messages=messages,
        tools=tools,
        stream=True,
    )

    async for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            yield content
