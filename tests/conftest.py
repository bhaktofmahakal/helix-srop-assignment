"""
Test fixtures.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base
from app.db.session import get_db
from app.main import app
from app import settings as settings_module


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_module.settings, "google_api_key", "")
    monkeypatch.setattr(settings_module.settings, "groq_api_key", "test-groq-key")
    monkeypatch.setattr(settings_module.settings, "llm_provider", "groq")


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db: AsyncSession):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def mock_adk(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.srop import pipeline as pipeline_module

    async def mock_route_with_adk_pattern(
        user_message: str, state
    ) -> tuple[str, dict, list[dict], list[str]]:
        if "rotate" in user_message.lower() or "deploy key" in user_message.lower():
            return (
                "knowledge",
                {"response": "To rotate a deploy key, go to Settings > Deploy Keys > Rotate. [chunk_001]"},
                [{"tool_name": "knowledge_agent", "args": {"query": user_message}, "result": "routed"}],
                ["chunk_001"],
            )
        elif "build" in user_message.lower():
            return (
                "account",
                {"response": "Here are your recent builds: bld_001 passed, bld_002 failed."},
                [{"tool_name": "account_agent", "args": {"user_id": "test"}, "result": "routed"}],
                [],
            )
        elif "plan tier" in user_message.lower() or "plan" in user_message.lower():
            return (
                "account",
                {"response": f"Your plan tier is {state.plan_tier}."},
                [{"tool_name": "account_agent", "args": {"user_id": state.user_id}, "result": "routed"}],
                [],
            )
        elif "ticket" in user_message.lower():
            return (
                "escalation",
                {"response": "Created ticket TKT-001 for your issue."},
                [{"tool_name": "escalation_agent", "args": {"summary": user_message}, "result": "routed"}],
                [],
            )
        return (
            "smalltalk",
            {"response": "Hello! I'm here to help with Helix questions."},
            [],
            [],
        )

    async def mock_run_groq_agent(
        user_message: str, state
    ) -> tuple[str, str, list[str]]:
        routed_to, resp, _, chunks = await mock_route_with_adk_pattern(user_message, state)
        return resp.get("response", ""), routed_to, chunks

    monkeypatch.setattr(pipeline_module, "_route_with_adk_pattern", mock_route_with_adk_pattern)
    monkeypatch.setattr(pipeline_module, "_run_groq_agent", mock_run_groq_agent)
