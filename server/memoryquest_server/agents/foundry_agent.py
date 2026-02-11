"""Microsoft Foundry memory agent implementation."""

from __future__ import annotations
import os
from typing import Any
from agent_framework import Agent

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
    
    This agent integrates with Microsoft Azure AI Foundry for memory management and agent orchestration.
    
    Authentication:
    - Uses Azure AD token authentication via DefaultAzureCredential
    - Requires AZURE_FOUNDRY_ENDPOINT environment variable
    - Does not support API key authentication (not available for Azure AI Foundry)
    
    Endpoint format: https://<resource>.services.ai.azure.com/api/projects/<project-name>
    """
    
    def __init__(self, foundry_client: Any = None) -> None:
        """
        Initialize the Foundry agent.
        
        Args:
            foundry_client: Optional pre-configured AzureAIClient for Foundry.
                          If not provided, will create one using environment variables.
        """
        # Store the foundry client if provided, otherwise we'll use a fallback
        self._foundry_client = foundry_client
        self._stub_memories = {}  # Fallback memory storage
        
        # If a Foundry client is provided, use it directly as the agent
        if foundry_client:
            self._agent = Agent(
                client=foundry_client,
                instructions=INSTRUCTIONS,
                # TODO: Integrate Foundry-specific memory management
                # When ready, implement FoundryMemoryTool as a ContextProvider that:
                # - Stores conversation history in Azure AI Foundry's memory store
                # - Retrieves relevant context based on conversation_id or user identity
                # - Integrates with Foundry's agent memory capabilities
                context_provider=None,
                name="foundry-agent"
            )
            print("Foundry Agent created with Azure AI Foundry client")
        else:
            # Fallback: this shouldn't happen in production, but provides graceful degradation
            print("Warning: No Foundry client provided, using stub mode")
            from agent_framework.azure import AzureOpenAIChatClient
            # Use a basic client as fallback (requires AZURE_OPENAI_* env vars)
            api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
            deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")
            
            if api_key and endpoint:
                fallback_client = AzureOpenAIChatClient(
                    api_key=api_key,
                    endpoint=endpoint,
                    deployment_name=deployment,
                )
                self._agent = Agent(
                    client=fallback_client,
                    instructions=INSTRUCTIONS,
                    context_provider=None,
                    name="foundry-agent-fallback"
                )
                print("Foundry Agent created in fallback mode with OpenAI client")
            else:
                raise RuntimeError(
                    "Foundry client not provided and fallback Azure OpenAI credentials not found. "
                    "Please set AZURE_FOUNDRY_ENDPOINT or AZURE_OPENAI_* environment variables."
                )

    def get_foundry_agent(self) -> Agent:
        """Returns the configured Foundry agent."""
        return self._agent
    
    # Memory management methods (stubbed for now)
    async def get_memories(self, username: str) -> dict:
        """
        Get memories for a user from Foundry.
        
        TODO: Implement actual Foundry memory retrieval:
        - Query Azure AI Foundry memory store for user-specific memories
        - Use the conversation_id or user context to filter memories
        - Return structured memory data
        
        Args:
            username: The username to retrieve memories for
            
        Returns:
            Dictionary with memories, count, and source
        """
        # Stubbed response for now
        return {
            "memories": self._stub_memories.get(username, []),
            "count": len(self._stub_memories.get(username, [])),
            "source": "foundry_stub",
            "note": "Foundry memory retrieval not yet implemented - using stub data"
        }
    
    async def delete_user_memories(self, username: str) -> dict:
        """
        Delete all memories for a user in Foundry.
        
        TODO: Implement actual Foundry memory deletion:
        - Connect to Azure AI Foundry memory store
        - Delete all user-specific memories using conversation_id or user context
        - Return deletion confirmation
        
        Args:
            username: The username to delete memories for
            
        Returns:
            Dictionary with deletion status and message
        """
        # Stubbed deletion for now
        if username in self._stub_memories:
            del self._stub_memories[username]
            return {
                "deleted": True, 
                "message": f"Deleted stub memories for {username}",
                "note": "Foundry memory deletion not yet implemented - deleted stub data only"
            }
        return {
            "deleted": False, 
            "message": "No memories found",
            "note": "Foundry memory deletion not yet implemented"
        }
