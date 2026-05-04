"""
Session state schema — persisted in sessions.state (JSON column).

Only store what the agent cannot re-derive from message history.
Keep it small — every turn loads and saves this.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SessionState(BaseModel):
    user_id: str
    plan_tier: Literal["free", "pro", "enterprise"] = "free"
    turn_count: int = 0
    last_routed_to: str | None = None
    last_retrieved_chunk_ids: list[str] = Field(default_factory=list)
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    last_ticket_id: str | None = None

    def to_db_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_db_dict(cls, data: dict) -> "SessionState":
        return cls.model_validate(data)
