from dataclasses import dataclass
import uuid

from app.db.models import Ticket
from app.db.session import AsyncSessionLocal


@dataclass
class TicketResult:
    ticket_id: str
    status: str
    priority: str


async def create_ticket(user_id: str, summary: str, priority: str = "normal") -> TicketResult:
    """
    Create a support ticket for the user and return the new ticket ID.

    Args:
        user_id: Helix user ID
        summary: short description of the issue
        priority: low | normal | high | critical
    """
    allowed = {"low", "normal", "high", "critical"}
    normalized = priority.lower().strip()
    if normalized not in allowed:
        normalized = "normal"

    ticket_id = f"tkt_{uuid.uuid4().hex[:12]}"
    async with AsyncSessionLocal() as session:
        session.add(
            Ticket(
                ticket_id=ticket_id,
                user_id=user_id,
                summary=summary,
                priority=normalized,
                status="open",
            )
        )
        await session.commit()

    return TicketResult(ticket_id=ticket_id, status="open", priority=normalized)
