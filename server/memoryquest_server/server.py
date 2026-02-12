import os
import warnings
import httpx
from contextlib import asynccontextmanager
from typing import List, Literal, Optional, Any
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework import ChatMessage

# Suppress harmless aiohttp deprecation warning about enable_cleanup_closed
warnings.filterwarnings("ignore", message="enable_cleanup_closed", category=DeprecationWarning)

# Tools & Agents
from agents.agent_framework_memory_agent import AgentFrameworkMemoryAgent
from agents.cognee_agent import CogneeAgent
from agents.hindsight_agent import HindsightAgent
from agents.mem0_agent import Mem0Agent
from agents.foundry_agent import FoundryAgent

# --- Configuration & Initialization ---
load_dotenv()

# Fix for Qdrant connection issues with HTTPS
if os.getenv("QDRANT_HOST", "").startswith("https://") and os.getenv("QDRANT_PORT") == "6333":
    print("Adjusting QDRANT_PORT to 443 for HTTPS connection in server startup")
    os.environ["QDRANT_PORT"] = "443"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup/shutdown lifecycle."""
    yield
    # Shutdown: drain Cognee background tasks to avoid unclosed sessions
    try:
        cognee_ctx = cognee_agent.context_provider
        if hasattr(cognee_ctx, "shutdown"):
            await cognee_ctx.shutdown()
    except Exception:
        pass

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Data Models ---

class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    username: str
    messages: List[Message] = Field(default_factory=list)
    query: Optional[str] = None

# --- Helper Functions ---

def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is not set.")
    return value

def _normalize_usage(usage: Any) -> Optional[dict[str, int]]:
    """Normalizes token usage data from different client versions/formats."""
    if usage is None:
        return None
    
    if isinstance(usage, dict):
        input_count = usage.get("input_token_count") or usage.get("inputTokenCount")
        output_count = usage.get("output_token_count") or usage.get("outputTokenCount")
        total_count = usage.get("total_token_count") or usage.get("totalTokenCount")
    else:
        input_count = getattr(usage, "input_token_count", None)
        output_count = getattr(usage, "output_token_count", None)
        total_count = getattr(usage, "total_token_count", None)

    if input_count is None and output_count is None and total_count is None:
        return None

    return {
        "inputTokenCount": input_count or 0,
        "outputTokenCount": output_count or 0,
        "totalTokenCount": total_count or 0,
    }

def _create_system_context(username: str, messages: List[Message]) -> List[ChatMessage]:
    """Helper to convert API models to Agent Framework models."""
    return [
        ChatMessage(role="system", text=f"You are assisting user {username}"),
        *(ChatMessage(role=m.role, text=m.content) for m in messages),
    ]


def _create_openai_input(username: str, messages: List[Message]) -> list[dict[str, str]]:
    """Helper to convert API models to OpenAI Responses API input format.

    NOTE: The Foundry Responses API with agent references does NOT support
    'system' role messages — the agent's instructions are configured in the
    Foundry portal. Only 'user' and 'assistant' messages are forwarded.
    """
    return [
        {"role": m.role, "content": m.content}
        for m in messages
        if m.role in ("user", "assistant")
    ]

# --- Health Checks ---

async def check_qdrant_health():
    qdrant_host = os.getenv("QDRANT_HOST")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{qdrant_host}")
            return response.status_code == 200
    except Exception:
        return False

async def check_hindsight_health():
    hindsight_url = os.getenv("HINDSIGHT_URL", "http://localhost:8888")
    print(f"Checking Hindsight health at: {hindsight_url}")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{hindsight_url}/health")
            return response.status_code == 200
    except Exception:
        return False

@app.get("/")
async def read_root():
    qdrant_healthy = await check_qdrant_health()
    hindsight_healthy = await check_hindsight_health()
    return {
        "Hello": "Agentic World", 
        "Qdrant Healthy": qdrant_healthy, 
        "Hindsight Healthy": hindsight_healthy
    }

# --- Service Composition ---

# 1. Base Client
client = AzureOpenAIChatClient(
    api_key=_require_env("AZURE_OPENAI_API_KEY"),
    endpoint=_require_env("AZURE_OPENAI_ENDPOINT"),
    deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT") or "gpt-5-mini",
)

grok_client = AzureOpenAIChatClient(
    api_key=_require_env("AZURE_OPENAI_API_KEY"),
    endpoint=_require_env("AZURE_OPENAI_ENDPOINT"),
    deployment_name=os.getenv("GROK_DEPLOYMENT_NAME") or "gpt-5-mini",
)

gpt_4_client = AzureOpenAIChatClient(
    api_key=_require_env("AZURE_OPENAI_API_KEY"),
    endpoint=_require_env("AZURE_OPENAI_ENDPOINT"),
    deployment_name=os.getenv("GPT4_DEPLOYMENT_NAME") or "gpt-5-mini",
)

deepseek_client = AzureOpenAIChatClient(
    api_key=_require_env("AZURE_OPENAI_API_KEY"),
    endpoint=_require_env("AZURE_OPENAI_ENDPOINT"),
    deployment_name=os.getenv("DEEPSEEK_DEPLOYMENT_NAME") or "gpt-5-mini",
)

# 2. Singleton Agents (Stateless wrappers around DB-backed memory)
# These agents don't hold conversational state in Python memory, so we can reuse them.
print("Initializing Persistent Agents...")
mem0_agent = Mem0Agent(client).get_mem0_agent()
cognee_agent = CogneeAgent(deepseek_client).get_cognee_agent()
hindsight_agent = HindsightAgent(grok_client).get_hindsight_agent()
foundry_agent_wrapper = FoundryAgent()

# 3. Stateful Agents (Held in memory)
# The AgentFrameworkMemoryAgent holds extracted details in python class variables, 
# so we must maintain a dictionary of instances per user.
print("Initializing Stateful Agent Registry...")
agent_framework_instances = {} 
agent_framework_threads = {}

print("Server initialized and ready")

# --- Endpoints: Generic ---

@app.post("/")
async def generic_agent(request: ChatRequest):
    print(f"Generic Agent request: {request.username}")
    messages = _create_system_context(request.username, request.messages)

    response = await gpt_4_client.get_response(messages)
    usage = _normalize_usage(response.usage_details)

    return {"message": response.messages[0].text, "usage": usage}

# --- Endpoints: Agent Framework (In-Memory State) ---

@app.post("/agent-framework")
async def agent_framework(request: ChatRequest):
    print(f"Agent Framework request: {request.username}")
    
    # Lifecycle: Load or Create Agent
    if request.username not in agent_framework_instances:
        print(f"Creating new stateful agent for: {request.username}")
        # Note: In a production app, we would load this state from a database here
        agent_framework_instances[request.username] = AgentFrameworkMemoryAgent(client).get_agent_framework_memory_agent()
    
    agent = agent_framework_instances[request.username]
    
    # Lifecycle: Load or Create Thread
    if request.username not in agent_framework_threads:
        agent_framework_threads[request.username] = agent.get_new_thread()
    
    thread = agent_framework_threads[request.username]
    messages = _create_system_context(request.username, request.messages)

    response = await agent.run(messages, thread=thread)
    usage = _normalize_usage(response.usage_details)
    
    return {"message": response.messages[0].text, "usage": usage}

@app.post("/agent-framework/memories")
async def get_af_memories(request: ChatRequest):
    if request.username not in agent_framework_instances:
        return {"message": "No memories found (Agent not active in memory)"}
    
    agent = agent_framework_instances[request.username]
    context_provider = agent.context_provider
    
    # Access internal state of the specific tool implementation
    memories = "No memories stored"
    if context_provider and hasattr(context_provider, '_user_info'):
        user_info = context_provider._user_info
        memories = {
            "username": user_info.username,
            "spa_preferences": user_info.spa_preferences,
            "preferred_hours": user_info.preferred_hours,
        }
    
    return {"message": memories}

@app.delete("/agent-framework/delete/{username}")
async def delete_af_memory(username: str):
    print(f"Deleting Agent Framework state for: {username}")
    agent_framework_instances.pop(username, None)
    agent_framework_threads.pop(username, None)
    return {"message": f"Deleted in-memory state for: {username}"}

# --- Endpoints: Mem0 (Qdrant Backed) ---

@app.post("/mem0")
async def mem0(request: ChatRequest):
    print(f"Mem0 request: {request.username}")
    messages = _create_system_context(request.username, request.messages)
    
    # Mem0 handles state via Qdrant, we just pass the username
    response = await mem0_agent.run(messages, username=request.username)
    usage = _normalize_usage(response.usage_details)
    
    return {"message": response.messages[0].text, "usage": usage}

@app.post("/mem0/memories")
async def mem0_get_memories(request: ChatRequest):
    context_provider = mem0_agent.context_provider
    memories = await context_provider.get_memories(
        request.username,
        query=request.query,
        limit=10,
    )
    return {"message": memories}

@app.delete("/mem0/delete/{username}")
async def delete_mem0_memory(username: str):
    context_provider = mem0_agent.context_provider
    result = await context_provider.delete_user_memories(username)
    if not result.get("deleted"):
        return {"message": "Failed to delete Mem0 memories", **result}
    return {"message": f"Deleted Mem0 memories for: {username}", **result}

# --- Endpoints: Cognee (Graph/Vector Backed) ---

@app.post("/cognee")
async def cognee(request: ChatRequest):
    print(f"Cognee request: {request.username}")
    messages = _create_system_context(request.username, request.messages)

    response = await cognee_agent.run(messages, username=request.username)
    usage = _normalize_usage(response.usage_details)
    return {"message": response.messages[0].text, "usage": usage}

@app.post("/cognee/memories")
async def cognee_get_memories(request: ChatRequest):
    context_provider = cognee_agent.context_provider
    memories = await context_provider.get_memories(request.username)
    return {"message": memories}

@app.delete("/cognee/delete/{username}")
async def delete_cognee_memory(username: str):
    context_provider = cognee_agent.context_provider
    if not hasattr(context_provider, "delete_user_memories"):
         raise HTTPException(status_code=500, detail="Cognee provider missing delete function")

    result = await context_provider.delete_user_memories(username)
    if not result.get("deleted"):
        return {"message": "No Cognee dataset found", **result}
    return {"message": f"Deleted Cognee memories for: {username}", **result}

# --- Endpoints: Hindsight (Service Backed) ---

@app.post("/hindsight")
async def hindsight(request: ChatRequest):
    print(f"Hindsight request: {request.username}")
    messages = _create_system_context(request.username, request.messages)
    
    response = await hindsight_agent.run(messages, username=request.username)
    usage = _normalize_usage(response.usage_details)
    
    return {"message": response.messages[0].text, "usage": usage}

@app.post("/hindsight/memories")
async def hindsight_get_memories(request: ChatRequest):
    context_provider = hindsight_agent.context_provider
    # Hindsight tool areflect returns Any (usually string or structured summary)
    memories = await context_provider.get_memories(request.username)
    # Handle the fact that areflect returns a wrapper or simple string
    if hasattr(memories, 'text'):
        return {"message": memories.text}
    return {"message": memories}

@app.delete("/hindsight/delete/{username}")
async def delete_hindsight_memory(username: str):
    print(f"Deleting Hindsight memories for: {username}")
    context_provider = hindsight_agent.context_provider
    docs = await context_provider.delete_user_memories(username)
    print(docs)
    
    if hasattr(context_provider, "delete_user_memories"):
         await context_provider.delete_user_memories(username)
         return {"message": f"Deleted Hindsight memories for: {username}"}
    else:
         # Fallback if the specific implementation hasn't been added to the Agent yet
        return {"message": "Delete operation not supported by Hindsight provider yet."}

# --- Endpoints: Foundry (Memory Store backed) ---

@app.post("/foundry")
async def foundry(request: ChatRequest):
    """
    Microsoft Foundry agent endpoint.
    
    If Azure AI Foundry is configured, this *references an existing agent* created
    in the Foundry portal (Azure AD auth via DefaultAzureCredential).
    The agent's Memory Store is scoped per-user via the ``user`` parameter.
    
    If not configured, falls back to GPT-4 client.
    """
    print(f"Foundry request: {request.username}")

    # If Foundry is configured, reference the existing Foundry portal agent.
    if foundry_agent_wrapper.is_configured:
        try:
            openai_input = _create_openai_input(request.username, request.messages)
            result = await foundry_agent_wrapper.chat(input_messages=openai_input, username=request.username)
            usage = _normalize_usage(result.usage)
            return {"message": result.text, "usage": usage}
        except Exception as e:
            # If Foundry is misconfigured or the SDK surface differs, do not hard-fail the API.
            # Fall back to GPT-4 client but include a diagnostic note.
            print(f"Warning: Foundry chat failed, falling back to GPT-4 client: {type(e).__name__}: {e}")

    # Otherwise, fall back to the local Azure OpenAI client (useful for dev/test).
    messages = _create_system_context(request.username, request.messages)
    response = await gpt_4_client.get_response(messages)
    usage = _normalize_usage(response.usage_details)
    return {
        "message": response.messages[0].text,
        "usage": usage,
        "note": (
            "Foundry not configured or Foundry call failed; returned response from GPT-4 client instead. "
            "Check AZURE_FOUNDRY_ENDPOINT/AZURE_FOUNDRY_AGENT_NAME, Azure AD auth, and azure-ai-projects version."
        ),
    }

@app.post("/foundry/memories")
async def foundry_get_memories(request: ChatRequest):
    """Retrieve Foundry memories for a user.

    Asks the Foundry agent to recall everything it remembers about the
    user.  The agent's Memory Store automatically injects stored facts
    into the context, so the response reflects what the store contains.
    """
    memories = await foundry_agent_wrapper.get_memories(request.username)
    return {"message": memories}


@app.delete("/foundry/delete/{username}")
async def delete_foundry_memory(username: str):
    """Clear the Foundry conversation chain for a user."""
    print(f"Deleting Foundry conversation chain for: {username}")
    result = await foundry_agent_wrapper.delete_user_memories(username)
    return {"message": result.get("message", "Done"), **result}
