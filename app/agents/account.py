from google.adk.agents import LlmAgent

from app.agents.tools.account_tools import get_account_status, get_recent_builds
from app.settings import settings

ACCOUNT_INSTRUCTION = """
You are the Helix Account Agent.
Use account tools to answer questions about builds, usage, and account status.
Be concise and format results in plain language.
"""

account_agent = LlmAgent(
    name="account",
    model=settings.adk_model,
    instruction=ACCOUNT_INSTRUCTION.strip(),
    tools=[get_recent_builds, get_account_status],
)
