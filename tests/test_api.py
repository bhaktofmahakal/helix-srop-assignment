"""
Integration tests — exercise the full SROP pipeline.
LLM mocked at the ADK boundary (not at the HTTP layer).
"""
import pytest


@pytest.mark.asyncio
async def test_create_session(client) -> None:
    resp = await client.post("/v1/sessions", json={"user_id": "u_test_001"})
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert data["user_id"] == "u_test_001"


@pytest.mark.asyncio
async def test_knowledge_query_routes_correctly(client, mock_adk) -> None:
    """
    Core integration test.

    Sends a knowledge question, asserts:
    1. Response contains a reply
    2. routed_to == "knowledge"
    3. trace exists with retrieved chunk IDs
    4. Turn 2 in the same session has access to context from turn 1
       (state persistence — at minimum, plan_tier available without re-asking)

    The mock_adk fixture patches at the ADK boundary, not at the HTTP layer.
    """
    # Create session
    sess = await client.post(
        "/v1/sessions", json={"user_id": "u_test_002", "plan_tier": "pro"}
    )
    session_id = sess.json()["session_id"]

    # Turn 1 — knowledge query
    r1 = await client.post(
        f"/v1/chat/{session_id}",
        json={"message": "How do I rotate a deploy key?"},
    )
    assert r1.status_code == 200
    assert r1.json()["routed_to"] == "knowledge"
    assert r1.json()["reply"]  # non-empty
    trace_id = r1.json()["trace_id"]

    # Trace must have chunk IDs
    trace = await client.get(f"/v1/traces/{trace_id}")
    assert trace.status_code == 200
    assert len(trace.json()["retrieved_chunk_ids"]) > 0

    # Turn 2 — follow-up in same session (state persists)
    r2 = await client.post(
        f"/v1/chat/{session_id}",
        json={"message": "What is my plan tier?"},
    )
    assert r2.status_code == 200
    # Agent should know plan_tier from state — not re-ask
    assert "pro" in r2.json()["reply"].lower()


@pytest.mark.asyncio
async def test_session_not_found_returns_404(client) -> None:
    resp = await client.post(
        "/v1/chat/nonexistent-id", json={"message": "hello"}
    )
    assert resp.status_code == 404
    assert resp.json()["title"] == "SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_guardrails_refuse_out_of_scope(client, mock_adk) -> None:
    """E5: Out-of-scope queries get refused before hitting ADK."""
    sess = await client.post("/v1/sessions", json={"user_id": "u_test_003"})
    session_id = sess.json()["session_id"]

    resp = await client.post(
        f"/v1/chat/{session_id}",
        json={"message": "Write me a poem about the ocean."},
    )
    assert resp.status_code == 200
    assert resp.json()["routed_to"] == "guardrails"
    assert "helix" in resp.json()["reply"].lower()


@pytest.mark.asyncio
async def test_healthz(client) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_idempotency_returns_cached(client, mock_adk) -> None:
    """E1: Same Idempotency-Key returns identical response."""
    sess = await client.post("/v1/sessions", json={"user_id": "u_test_idem"})
    session_id = sess.json()["session_id"]

    headers = {"Idempotency-Key": "test-key-001"}

    r1 = await client.post(
        f"/v1/chat/{session_id}",
        json={"message": "How do I rotate a deploy key?"},
        headers=headers,
    )
    assert r1.status_code == 200
    trace_id_1 = r1.json()["trace_id"]

    # Same key → same response
    r2 = await client.post(
        f"/v1/chat/{session_id}",
        json={"message": "How do I rotate a deploy key?"},
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["trace_id"] == trace_id_1
    assert r2.json()["reply"] == r1.json()["reply"]


@pytest.mark.asyncio
async def test_trace_not_found_returns_404(client) -> None:
    resp = await client.get("/v1/traces/nonexistent-trace")
    assert resp.status_code == 404
