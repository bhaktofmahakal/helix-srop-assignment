"""
SROP Root Orchestrator — Google ADK agent.

Routes every user turn to KnowledgeAgent or AccountAgent via ADK's AgentTool.
This means the LLM decides which tool to call — you do not parse its output.

Intent → sub-agent:
  knowledge:  "how do I X", "what is X", docs questions
  account:    "show my builds", "my account status", usage questions
  smalltalk:  greetings, thanks — root agent handles inline (no tool call)

See docs/google-adk-guide.md for AgentTool pattern and event extraction.
"""
from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool

from app.agents.account import account_agent
from app.agents.escalation import escalation_agent
from app.agents.knowledge import knowledge_agent
from app.settings import settings
from app.srop.state import SessionState

ROOT_INSTRUCTION = """
You are the Helix Support Concierge — a routing agent.
Call the correct specialist tool based on the user's intent.

Intent → tool:
- HOW to do something, WHAT something is, docs/feature questions → knowledge_agent
- Their account, builds, status, usage → account_agent
- Open a ticket, escalate, report an issue → escalation_agent
- Greetings or off-topic → respond directly, no tool call

Always call a tool when intent matches. Never answer knowledge or account questions yourself.
User context will be in the system message — use it.
"""

def build_root_agent(state: SessionState) -> LlmAgent:
  recent_history = "\n".join(
    f"- {turn.role}: {turn.content}" for turn in state.conversation_history[-6:]
  )
  if not recent_history:
    recent_history = "- (none)"

  instruction = (
    f"{ROOT_INSTRUCTION}\n\n"
    "Current user context:\n"
    f"- user_id: {state.user_id}\n"
    f"- plan_tier: {state.plan_tier}\n"
    f"- last_routed_to: {state.last_routed_to or 'none'}\n"
    f"- turn_count: {state.turn_count}\n"
    f"- last_retrieved_chunk_ids: {state.last_retrieved_chunk_ids}\n"
    "Recent conversation:\n"
    f"{recent_history}\n"
  )

  knowledge_tool = AgentTool(agent=knowledge_agent)
  account_tool = AgentTool(agent=account_agent)
  escalation_tool = AgentTool(agent=escalation_agent)

  return LlmAgent(
    name="srop_root",
    model=settings.adk_model,
    instruction=instruction,
    tools=[knowledge_tool, account_tool, escalation_tool],
  )
