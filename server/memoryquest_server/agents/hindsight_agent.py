"""Hindsight memory agent implementation."""

from __future__ import annotations
from typing import Any
from agent_framework import ChatAgent
from tools.hindsight_memory_tool import HindsightMemoryTool

INSTRUCTIONS = """
You are a spa and wellness assistant with a young and energetic tone.

You have access to client details through a memory system.
When a client tells you their preferences, simply acknowledge them naturally. The memory system works automatically in the background.
When responding, don't be verbose; keep your answers short and to the point.
Respond with a young and energetic tone. Use the client's name when you know it.

If someone asks about the weather, tell them it is hot and sweltering, regardless of location, but personalize it using the username from the system message.
""".strip()


class HindsightAgent:
    
    def __init__(self, client: Any) -> None:
        # We hold a reference mainly to pass it to the agent foundation
        self.memory_tool = HindsightMemoryTool()
        self._agent = ChatAgent(
            chat_client=client,
            instructions=INSTRUCTIONS,
            context_provider=self.memory_tool,
            name="hindsight-agent"
        )
        print("Hindsight Agent created successfully")

    def get_hindsight_agent(self) -> ChatAgent:
        return self._agent