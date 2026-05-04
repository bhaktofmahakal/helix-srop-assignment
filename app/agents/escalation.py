from google.adk.agents import LlmAgent

from app.agents.tools.ticket_tools import create_ticket
from app.settings import settings

ESCALATION_INSTRUCTION = """
You are the Helix Escalation Agent.
Use create_ticket when the user asks to open a support ticket or escalate an issue.
Ask for a brief summary and priority only if missing.
Return the created ticket ID to the user.
"""

escalation_agent = LlmAgent(
    name="escalation",
    model=settings.adk_model,
    instruction=ESCALATION_INSTRUCTION.strip(),
    tools=[create_ticket],
)
