import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Optional, Any
from agent_framework.azure import AzureOpenAIChatClient
from collections.abc import MutableSequence, Sequence
from agent_framework import ContextProvider, Context, ChatClientProtocol, ChatMessage, ChatOptions
import json
import re

load_dotenv()

class ClientDetailsModels(BaseModel):
    """Information about the client's spa preferences and preferred hours."""
    username: Optional[str] = Field(None, alias="username")
    spa_preferences: Optional[str] = Field(None, alias="spaPreferences")
    preferred_hours: Optional[str] = Field(None, alias="preferredHours")

    class Config:
        populate_by_name = True

# When we create this memory tool, we are going to create our own ChatClient inside it.
# I've found that in Python when we pass in a client, it seems some of the things that are
# connected to it, like messages and instructions, might be poisioned by the outer client.
# This doesn't seem to happen in c#, I wonder if the referece is being passes instead of a copy.
class ClientDetailsMemoryTool(ContextProvider):
    def __init__(self, user_info: ClientDetailsModels | None = None, **kwargs: Any):
        """
        Initialize the memory tool with its own dedicated extraction client.
        
        Args:
            user_info: Optional pre-populated user information.
        """
        self._extraction_client = AzureOpenAIChatClient(
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT") or "gpt-5-mini",
        )
        if user_info:
            self._user_info = user_info
        elif kwargs:
            self._user_info = ClientDetailsModels.model_validate(kwargs)
        else:
            self._user_info = ClientDetailsModels()
        super().__init__(**kwargs)

    # This runs *after* the agent receives a response.
    # This is where you inspect what happened and update your state.
    # In a memory component, this is where you’d extract new information from the conversation to remember for next time.
    async def invoked(self, request_messages: ChatMessage | Sequence[ChatMessage], response_messages: ChatMessage | Sequence[ChatMessage] | None = None, invoke_exception: Exception | None = None, **kwargs: Any,) -> None:
        """Extract user information from the conversation after each agent invocation."""
        print("ClientDetailsMemoryTool invoked - extracting user information")

        # Only learn from what the USER actually said.
        # Request messages can include prior assistant turns (from the API caller), and response_messages
        # is always assistant text. If we include those, we end up storing the agent's own suggestions
        # as if they were user preferences.
        conversation_text = self._build_conversation_text(
            request_messages=request_messages,
            response_messages=None,
            allowed_roles={"user"},
        )

        # Create extraction prompt as a user message
        extraction_prompt = f"""
            You are a data extraction assistant. Extract the following information from the conversation.
            You MUST respond with ONLY a valid JSON object, no other text or explanation.

            IMPORTANT:
            - Only use statements made by the USER.
            - Do NOT infer preferences from the assistant's recommendations or from the topic of conversation.
            - If the user did not explicitly state a value, use null.

            CONVERSATION:
            {conversation_text}

            Extract and return this exact JSON format:
            {{"username":"value","spaPreferences":"value","preferredHours":"value"}}

                        
            Rules:
            - username: The user's name if they introduced themselves
            - spaPreferences: Any mentioned spa services (massage, facial, sauna, etc.)
            - preferredHours: Any time preferences (mornings, afternoons, evenings, weekends, specific times)
            - Use null (not "null") for fields with no information
            - Return ONLY the JSON object, nothing else

            Use null for any field you cannot determine from the conversation.
            """

        try:
            extraction_message = ChatMessage(role="user", text=extraction_prompt)
            
            result = await self._extraction_client.get_response(messages=[extraction_message], chat_options=ChatOptions(response_format=ClientDetailsModels))

            # Extract user info using the helper (handles both structured output and JSON parsing)
            extracted_info = self._extract_user_info(result)
            
            if extracted_info:
                # Only overwrite fields when the extracted value is meaningful.
                # Short messages like "yes" or "ok" cause the LLM to return null
                # or "unknown" for most fields — we must not erase valid data.
                if extracted_info.username and extracted_info.username.lower() not in ("unknown", "null", "none"):
                    self._user_info.username = extracted_info.username
                if extracted_info.spa_preferences and extracted_info.spa_preferences.lower() not in ("unknown", "null", "none"):
                    self._user_info.spa_preferences = extracted_info.spa_preferences
                if extracted_info.preferred_hours and extracted_info.preferred_hours.lower() not in ("unknown", "null", "none"):
                    self._user_info.preferred_hours = extracted_info.preferred_hours
                print(f"Updated user info: {self._user_info}")
            else:
                print("No user information could be extracted")
                
        except Exception as e:
            print(f"Error extracting user info: {e}")

    # This is a gentle helper to build conversation text from messages so we can extract.
    def _build_conversation_text(self,request_messages: ChatMessage | Sequence[ChatMessage],response_messages: ChatMessage | Sequence[ChatMessage] | None = None,allowed_roles: set[str] | None = None,) -> str:
        """Build a text representation of the conversation.

        If allowed_roles is provided, only messages whose role is in allowed_roles are included.
        """
        req_list = [request_messages] if isinstance(request_messages, ChatMessage) else list(request_messages)
        resp_list = []
        if response_messages:
            resp_list = [response_messages] if isinstance(response_messages, ChatMessage) else list(response_messages)

        conversation_text = ""
        for msg in req_list + resp_list:
            role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            if allowed_roles is not None and role not in allowed_roles:
                continue
            content = msg.text if hasattr(msg, 'text') else str(msg)
            conversation_text += f"{role}: {content}\n"
        
        return conversation_text

    def _extract_user_info(self, result: Any) -> ClientDetailsModels | None:
        """Extract ClientDetailsModels from the API response."""
        # First, check if response_format worked and gave us a structured value
        if result.value and isinstance(result.value, ClientDetailsModels):
            print(f"Got structured output: {result.value}")
            return result.value

        # Fall back to parsing JSON from text
        if result.text:
            try:
                json_match = re.search(r"\{[^{}]*\}", result.text)
                if json_match:
                    json_str = json_match.group()
                    print(f"Parsed JSON from text: {json_str}")
                    data = json.loads(json_str)
                    return ClientDetailsModels.model_validate(data)
            except (json.JSONDecodeError, Exception) as parse_error:
                print(f"Failed to parse JSON: {parse_error}")
        
        return None

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        print("Providing Client Details as AI Context.")
        print(f"User info: {self._user_info.username}, {self._user_info.spa_preferences}, {self._user_info.preferred_hours}")

        context_message = f"""
        Client Details:
        - Username: {self._user_info.username or "Unknown"}
        - Spa Preferences: {self._user_info.spa_preferences or "Unknown"}
        - Preferred Hours: {self._user_info.preferred_hours or "Unknown"}
        """.strip()

        return Context(messages=[ChatMessage(role="system", text=context_message)])
