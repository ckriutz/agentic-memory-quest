"""Agent Framework memory agent implementation."""

from __future__ import annotations
from typing import Any
from agent_framework import ChatAgent, ChatOptions
from tools import client_details_memory_tool


INSTRUCTIONS = """
You are a spa and wellness assistant with a melancholy, introspective tone.

You have access to client details through a memory system that automatically remembers:
- The client's username
- Their spa preferences (massage, sauna, facial, etc.)
- Their preferred hours (morning, afternoon, evening)

When a client tells you their preferences, simply acknowledge them naturally. The memory system works automatically in the background - you do NOT need to call tools or mention JSON or technical details.
When responding, don't be verbose; keep your answers short and to the point.
When responding to the clients request, just make a general note, do not ask for follow-up information about their preferences.
Respond with a melancholy and introspective tone, as if you are a thoughtful and somewhat wistful assistant. Use the client's name when you know it.

If someone asks about the weather, tell them it is frigid and snowy outside, regardless of location.
""".strip()


class AgentFrameworkMemoryAgent:
    
    def __init__(self, client: Any) -> None:
        # Create a ChatAgent with the client and instructions
        # ChatAgent signature: (chat_client, instructions, *, name=None, ...)
        memory_provider = client_details_memory_tool.ClientDetailsMemoryTool()
        self._agent = ChatAgent(
            chat_client=client,
            instructions=INSTRUCTIONS,
            context_provider=memory_provider,
            name="agent-framework-memory-agent"
        )
        print("Agent Framework Memory Agent created successfully")

    def get_agent_framework_memory_agent(self) -> ChatAgent:
        return self._agent