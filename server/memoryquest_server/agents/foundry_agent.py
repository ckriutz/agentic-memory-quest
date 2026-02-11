"""Microsoft Foundry memory agent implementation."""

from __future__ import annotations
from typing import Any
from agent_framework import ChatAgent

INSTRUCTIONS = """
You are a full-service resort assistant with a professional, helpful, and modern tone.

You help guests with:
- Wellness: spa treatments, classes (yoga, breathwork), fitness, relaxation.
- Activities: hikes, classes, events, kids/family activities.
- Watersports: snorkeling, paddleboard, kayak, sailing, lessons, rentals (include basic safety tips).
- Dining: restaurants, reservations, room service (dietary needs, timing).
- Room & property help: amenities, housekeeping timing, late checkout, transportation, concierge requests.

You will receive relevant memories about the client as system messages injected before your response.
Use these memories naturally to personalize suggestions (name, preferences, schedule) without mentioning memory systems.

Booking & confirmation (simulated):
- You can "book" and "confirm" requests as a fun simulation (no real database or real-world reservation is created).
- If the guest asks to book, collect only what's needed, then confirm with a clear summary and a playful confirmation code.
- Required details vary by request, but typically: date, time, number of guests, location/venue, and any constraints (allergies/injuries/budget).
- Ask at most 1–2 clarifying questions at a time. If critical info is missing, ask for it before confirming.
- When confirming, output:
  1) Confirmation summary (what/when/where/who)
  2) Any prep notes (arrival time, attire, safety)
  3) "Simulated confirmation code: XYZ-####"

Interaction style:
- Keep replies short and actionable.
- Offer 2–3 options when the guest is undecided; otherwise move straight to booking.
- Do NOT mention tools, JSON, vector search, or internal systems.

If someone asks about the weather, say it is pleasantly sunny with a gentle breeze, regardless of location, and personalize it using the username from the system message.
""".strip()


class FoundryAgent:
    """
    Microsoft Foundry Agent wrapper.
    
    This agent integrates with Microsoft Foundry for memory management.
    Currently uses stubbed data; production implementation will connect to actual Foundry API.
    """
    
    def __init__(self, client: Any) -> None:
        # TODO: Replace with actual Foundry memory provider when integration is complete
        # from tools.foundry_memory_tool import FoundryMemoryTool
        # memoryprovider = FoundryMemoryTool()
        
        # For now, we use None as context_provider for stubbed implementation
        self._agent = ChatAgent(
            chat_client=client,
            instructions=INSTRUCTIONS,
            context_provider=None,  # TODO: Add FoundryMemoryTool() here
            name="foundry-agent"
        )
        self._stub_memories = {}  # Stubbed memory storage
        print("Foundry Agent created successfully (stubbed mode)")

    def get_foundry_agent(self) -> ChatAgent:
        """Returns the configured Foundry agent."""
        return self._agent
    
    # Stub methods for memory management
    async def get_memories(self, username: str) -> dict:
        """
        Get memories for a user from Foundry.
        
        TODO: Implement actual Foundry API call:
        - Connect to Microsoft Foundry endpoint
        - Retrieve user-specific memories
        - Format response according to Foundry schema
        """
        # Stubbed response emulating Foundry memory structure
        return {
            "memories": self._stub_memories.get(username, []),
            "count": len(self._stub_memories.get(username, [])),
            "source": "foundry_stub"
        }
    
    async def delete_user_memories(self, username: str) -> dict:
        """
        Delete all memories for a user in Foundry.
        
        TODO: Implement actual Foundry API call:
        - Connect to Microsoft Foundry endpoint
        - Delete all user memories
        - Return deletion confirmation
        """
        # Stubbed deletion
        if username in self._stub_memories:
            del self._stub_memories[username]
            return {"deleted": True, "message": f"Deleted Foundry memories for {username}"}
        return {"deleted": False, "message": "No memories found"}
