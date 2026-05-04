"""
Account tools — used by AccountAgent.

These tools query the DB for user-specific data.
Mock data is acceptable for the take-home; the integration matters.

TODO for candidate: implement these tools.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from app.db.models import User
from app.db.session import AsyncSessionLocal


@dataclass
class BuildSummary:
    build_id: str
    pipeline: str
    status: str  # passed | failed | cancelled
    branch: str
    started_at: datetime
    duration_seconds: int


@dataclass
class AccountStatus:
    user_id: str
    plan_tier: str
    concurrent_builds_used: int
    concurrent_builds_limit: int
    storage_used_gb: float
    storage_limit_gb: float


async def get_recent_builds(user_id: str, limit: int = 5) -> list[BuildSummary]:
    """
    Return the most recent builds for a user, newest first.

    For the take-home: returning mock/seeded data is fine.
    The key evaluation point is that this is wired as an ADK tool
    and the agent correctly invokes it when the user asks about builds.
    """
    now = datetime.utcnow()
    seed = sum(ord(ch) for ch in user_id)
    statuses = ["passed", "failed", "cancelled", "running", "queued"]
    builds: list[BuildSummary] = []
    for i in range(max(limit, 5)):
        status = statuses[(seed + i) % len(statuses)]
        builds.append(
            BuildSummary(
                build_id=f"bld_{seed:04d}_{i:02d}",
                pipeline="deploy" if i % 2 == 0 else "test",
                status=status,
                branch="main" if i % 3 == 0 else "feature/api",
                started_at=now,
                duration_seconds=180 + (i * 12),
            )
        )
    return builds[:limit]


async def get_account_status(user_id: str) -> AccountStatus:
    """
    Return current account status (plan, usage limits).

    For the take-home: mock data is fine.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()

    plan_tier = user.plan_tier if user else "free"
    limits = {
        "free": (1, 1.0),
        "pro": (5, 10.0),
        "enterprise": (999, 100.0),
    }
    concurrent_limit, storage_limit = limits.get(plan_tier, limits["free"])
    usage_seed = sum(ord(ch) for ch in user_id) % max(concurrent_limit, 1)
    return AccountStatus(
        user_id=user_id,
        plan_tier=plan_tier,
        concurrent_builds_used=usage_seed,
        concurrent_builds_limit=concurrent_limit,
        storage_used_gb=round(storage_limit * 0.3, 2),
        storage_limit_gb=storage_limit,
    )
