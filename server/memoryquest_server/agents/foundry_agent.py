"""Azure AI Foundry agent wrapper.

This integration is different from the other agents in this repo:
- We do NOT create an agent definition at runtime.
- We authenticate with Azure AD (DefaultAzureCredential).
- We *reference* an existing agent created in the Foundry portal.

Docs/sample in Foundry portal typically look like:

    project_client = AIProjectClient(endpoint=..., credential=DefaultAzureCredential())
    agent = project_client.agents.get(agent_name=...)
    openai_client = project_client.get_openai_client()
    response = openai_client.responses.create(... extra_body={"agent": {"name": agent.name, "type": "agent_reference"}})

This module adapts that pattern for the FastAPI server.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional, Sequence

import anyio


@dataclass(frozen=True)
class FoundryChatResult:
    text: str
    usage: Optional[dict[str, int]] = None
    raw_response: Any | None = None


def _first_env(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _build_foundry_endpoint() -> Optional[str]:
    """Return the full Foundry *project* endpoint.

    Preferred env var:
      - AZURE_FOUNDRY_ENDPOINT

    Or build it from:
      - AZURE_FOUNDRY_RESOURCE_NAME and AZURE_FOUNDRY_PROJECT
      - AZURE_FOUNDRY_RESOURCE_ENDPOINT and AZURE_FOUNDRY_PROJECT

    Result format:
      https://<resource>.services.ai.azure.com/api/projects/<project>
    """

    explicit = _first_env("AZURE_FOUNDRY_ENDPOINT")
    if explicit:
        return explicit.rstrip("/")

    project = _first_env("AZURE_FOUNDRY_PROJECT", "AZURE_FOUNDRY_PROJECT_NAME")
    if not project:
        return None

    resource_endpoint = _first_env("AZURE_FOUNDRY_RESOURCE_ENDPOINT")
    if resource_endpoint:
        return f"{resource_endpoint.rstrip('/')}" + f"/api/projects/{project}"

    resource_name = _first_env("AZURE_FOUNDRY_RESOURCE_NAME")
    if resource_name:
        return f"https://{resource_name}.services.ai.azure.com/api/projects/{project}"

    return None


def _normalize_foundry_usage(usage: Any) -> Optional[dict[str, int]]:
    """Normalize token usage to the server's expected shape.

    The server normalizer expects: input_token_count, output_token_count, total_token_count.
    We attempt to extract those from common responses API formats.
    """

    if usage is None:
        return None

    # Dict-like usage
    if isinstance(usage, dict):
        # OpenAI-style names
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")

        # agent-framework style names
        input_token_count = usage.get("input_token_count")
        output_token_count = usage.get("output_token_count")
        total_token_count = usage.get("total_token_count")

        it = input_token_count if input_token_count is not None else input_tokens
        ot = output_token_count if output_token_count is not None else output_tokens
        tt = total_token_count if total_token_count is not None else total_tokens

        if it is None and ot is None and tt is None:
            return None

        return {
            "input_token_count": int(it or 0),
            "output_token_count": int(ot or 0),
            "total_token_count": int(tt or 0),
        }

    # Object-like usage
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)

    input_token_count = getattr(usage, "input_token_count", None)
    output_token_count = getattr(usage, "output_token_count", None)
    total_token_count = getattr(usage, "total_token_count", None)

    it = input_token_count if input_token_count is not None else input_tokens
    ot = output_token_count if output_token_count is not None else output_tokens
    tt = total_token_count if total_token_count is not None else total_tokens

    if it is None and ot is None and tt is None:
        return None

    return {
        "input_token_count": int(it or 0),
        "output_token_count": int(ot or 0),
        "total_token_count": int(tt or 0),
    }


class FoundryAgent:
    """Connects to an existing Azure AI Foundry agent and runs chat requests.

    Memory behaviour
    ----------------
    When the Foundry portal agent has Memory **enabled**, the service
    automatically extracts facts from conversations and retrieves them
    on subsequent calls.  The ``user`` parameter passed to
    ``responses.create`` scopes the memory store *per user* so each
    person gets their own personalised experience.

    We also maintain a per-user ``conversation`` mapping so
    multi-turn conversations within the same session are tracked
    server-side and the Memory Store can persist/retrieve memories.
    """

    def __init__(
        self,
        *,
        endpoint: Optional[str] = None,
        agent_name: Optional[str] = None,
        credential: Any = None,
        project_client: Any = None,
    ) -> None:
        # Track per-user conversation IDs for memory continuity.
        self._user_conversations: dict[str, str] = {}

        self.endpoint = (endpoint or _build_foundry_endpoint() or "").rstrip("/")
        self.agent_name = agent_name or _first_env("AZURE_FOUNDRY_AGENT_NAME")

        self._project_client: Any | None = None
        self._openai_client: Any | None = None
        self._agent: Any | None = None
        self._init_error: str | None = None

        try:
            if project_client is not None:
                self._project_client = project_client
            elif self.endpoint and self.agent_name:
                # Lazy-import so a missing prerelease dependency doesn't break non-Foundry usage.
                from azure.ai.projects import AIProjectClient
                from azure.identity import DefaultAzureCredential, ManagedIdentityCredential, ChainedTokenCredential

                if credential is None:
                    # In Azure Container Apps, ManagedIdentityCredential is the
                    # fastest path. DefaultAzureCredential's chain tries many
                    # providers and can time out before reaching it.
                    credential = ChainedTokenCredential(
                        ManagedIdentityCredential(),
                        DefaultAzureCredential(),
                    )

                self._project_client = AIProjectClient(endpoint=self.endpoint, credential=credential)

            if self._project_client is not None and self.agent_name:
                # Resolve the agent reference (matches the Foundry portal sample).
                # azure-ai-projects v2 (preview/beta) exposes agents.get(agent_name=...)
                # but the GA v1 exposes a different AgentsClient without that method.
                agents_client = self._project_client.agents
                get_fn = getattr(agents_client, "get", None)
                if get_fn is None:
                    # Wrong SDK version installed. Provide a clear diagnostic.
                    installed_ver = "unknown"
                    try:
                        import importlib.metadata
                        installed_ver = importlib.metadata.version("azure-ai-projects")
                    except Exception:
                        pass
                    raise RuntimeError(
                        f"azure-ai-projects {installed_ver} is installed, but the Foundry "
                        f"agent-reference feature requires >=2.0.0b1 (preview). "
                        f"Run: pip install --pre 'azure-ai-projects>=2.0.0b1' to upgrade. "
                        f"Available methods on agents client: "
                        f"{[m for m in dir(agents_client) if not m.startswith('_')]}"
                    )

                self._agent = agents_client.get(agent_name=self.agent_name)
                print(f"Retrieved Foundry agent: {self._agent.name}")

                # Get an OpenAI client from the project — do NOT pass api_version or set
                # OPENAI_API_VERSION, as the SDK picks the correct version for the
                # Responses API internally.  Passing the old Azure OpenAI API version
                # (e.g. 2024-10-01-preview) would route to the Assistants API and break
                # agent-reference calls.
                self._openai_client = self._project_client.get_openai_client()
                print(f"✓ Foundry project client ready (endpoint={self.endpoint}, agent={self._agent.name})")
            else:
                # Not configured; server can fall back to other clients.
                print(
                    "Foundry agent not configured. Set AZURE_FOUNDRY_ENDPOINT (or RESOURCE_NAME/RESOURCE_ENDPOINT + PROJECT) "
                    "and AZURE_FOUNDRY_AGENT_NAME to enable Foundry chat."
                )
        except Exception as e:
            # Never crash app import-time; let the API endpoint fall back.
            self._init_error = f"{type(e).__name__}: {e}"
            self._project_client = None
            self._openai_client = None
            self._agent = None
            print(f"Warning: Foundry client initialization failed: {self._init_error}")

    @property
    def is_configured(self) -> bool:
        return self._openai_client is not None and self._agent is not None

    async def chat(
        self,
        *,
        input_messages: Sequence[dict[str, str]],
        username: str | None = None,
    ) -> FoundryChatResult:
        """Send messages to the referenced Foundry agent.

        Args:
            input_messages: OpenAI Responses-style input messages, e.g.
                [{"role": "user", "content": "hi"}]
            username: Optional user identifier.  When supplied the Foundry
                Memory Store is scoped to this user (instead of the portal
                default ``defaultUser``) and responses are chained so the
                agent remembers prior turns.

        Returns:
            FoundryChatResult(text=..., usage=...)
        """

        if not self.is_configured:
            raise RuntimeError(
                "Foundry agent is not configured. Provide AZURE_FOUNDRY_ENDPOINT and AZURE_FOUNDRY_AGENT_NAME."
            )

        openai_client = self._openai_client
        agent = self._agent
        assert openai_client is not None
        assert agent is not None

        # Get or create a conversation for this user so the Memory Store
        # can persist and retrieve memories across turns.
        # Note: conversation and previous_response_id are mutually exclusive
        # in the Foundry API, so we use conversation (which tracks history
        # and enables the memory lifecycle).
        conversation_id = self._user_conversations.get(username) if username else None
        if username and conversation_id is None:
            def _create_conv() -> str:
                conv = openai_client.conversations.create()
                return conv.id
            conversation_id = await anyio.to_thread.run_sync(_create_conv)
            self._user_conversations[username] = conversation_id

        def _do_call() -> Any:
            kwargs: dict[str, Any] = {
                "input": list(input_messages),
                "extra_body": {"agent": {"name": agent.name, "type": "agent_reference"}},
            }

            # Attach to a conversation so the Memory Store can read/write memories.
            if conversation_id:
                kwargs["conversation"] = conversation_id

            # Scope the Memory Store to this specific user.
            if username:
                kwargs["user"] = username

            return openai_client.responses.create(**kwargs)

        response = await anyio.to_thread.run_sync(_do_call)

        # Common helper field on the response object
        text = getattr(response, "output_text", None)
        if text is None:
            # Fallback: attempt to stringify output
            text = str(getattr(response, "output", ""))

        usage_any = getattr(response, "usage", None) or getattr(response, "usage_details", None)
        usage = _normalize_foundry_usage(usage_any)

        return FoundryChatResult(text=text or "", usage=usage, raw_response=response)

    # ------------------------------------------------------------------
    # Memory management
    # ------------------------------------------------------------------

    async def get_memories(self, username: str) -> dict:
        """Retrieve memories the Foundry agent has stored for *username*.

        Because the Foundry Memory Store does not (yet) expose a direct
        "list memories" SDK method, we ask the agent itself to recall
        what it remembers.  We make this call **stateless** — it does not
        chain onto the user's real conversation and does not update the
        conversation chain mapping.
        """

        if not self.is_configured:
            return {
                "memories": [],
                "count": 0,
                "source": "foundry",
                "note": "Foundry agent is not configured.",
            }

        try:
            openai_client = self._openai_client
            agent = self._agent
            assert openai_client is not None
            assert agent is not None

            recall_input = [
                {
                    "role": "user",
                    "content": (
                        f"What do you remember about the user '{username}'? "
                        "List every fact or preference you have stored about them as a bulleted list. "
                        "If you have no memories, respond with exactly: No memories stored."
                    ),
                }
            ]

            # Use the user's existing conversation so the Memory Store can
            # look up memories scoped to that user, or create a temporary one.
            conversation_id = self._user_conversations.get(username)
            if conversation_id is None:
                def _create_conv() -> str:
                    conv = openai_client.conversations.create()
                    return conv.id
                conversation_id = await anyio.to_thread.run_sync(_create_conv)

            def _do_recall() -> Any:
                return openai_client.responses.create(
                    input=recall_input,
                    conversation=conversation_id,
                    user=username,
                    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
                    # No previous_response_id — intentionally stateless so we
                    # don't pollute the user's real conversation chain.
                )

            response = await anyio.to_thread.run_sync(_do_recall)

            memory_text = getattr(response, "output_text", None)
            if memory_text is None:
                memory_text = str(getattr(response, "output", ""))
            memory_text = memory_text.strip()

            # Determine if the agent actually has memories.
            no_memory_phrases = [
                "no memories stored",
                "i don't have any",
                "i do not have any",
                "i don't remember",
                "no information",
                "no stored",
                "don't have any memories",
                "do not have any memories",
            ]
            has_memories = not any(p in memory_text.lower() for p in no_memory_phrases)

            if has_memories:
                # Split on bullet points or newlines to get individual memories.
                lines = [
                    line.strip().lstrip("-•*").strip()
                    for line in memory_text.split("\n")
                    if line.strip() and line.strip().lstrip("-•*").strip()
                ]
                memories = lines if lines else [memory_text]
            else:
                memories = []

            return {
                "memories": memories,
                "count": len(memories),
                "source": "foundry",
                "message": memory_text,
            }
        except Exception as e:
            print(f"Warning: Foundry memory retrieval failed: {e}")
            return {
                "memories": [],
                "count": 0,
                "source": "foundry",
                "note": f"Memory retrieval failed: {type(e).__name__}: {e}",
            }

    async def delete_user_memories(self, username: str) -> dict:
        """Clear conversation chain for *username*.

        The Foundry Memory Store itself does not currently expose a
        per-user delete API from the SDK.  What we *can* do is reset the
        conversation chain so the agent starts fresh for this user.  Any
        facts already persisted in the Memory Store will still be retained
        server-side until cleared via the Foundry portal.
        """

        had_conversation = username in self._user_conversations
        self._user_conversations.pop(username, None)

        return {
            "deleted": had_conversation,
            "message": (
                f"Cleared conversation chain for {username}. "
                "Server-side Memory Store entries can be managed in the Foundry portal."
            ),
        }
