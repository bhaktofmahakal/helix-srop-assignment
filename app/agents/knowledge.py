from google.adk.agents import LlmAgent

from app.agents.tools.search_docs import search_docs
from app.settings import settings

KNOWLEDGE_INSTRUCTION = """
You are the Helix Product Knowledge Agent.
Always use search_docs to answer product and documentation questions.
Use ONLY the returned chunks as your source of truth.
Cite sources by chunk_id in brackets, e.g. "According to [chunk_abc123] ...".
If the answer is not in the provided chunks, say you do not have documentation for it.
"""

knowledge_agent = LlmAgent(
    name="knowledge",
    model=settings.adk_model,
    instruction=KNOWLEDGE_INSTRUCTION.strip(),
    tools=[search_docs],
)
