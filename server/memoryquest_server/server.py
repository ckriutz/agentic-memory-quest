from agent_framework.azure import AzureOpenAIChatClient
from agent_framework import ChatMessage
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Any
import os
from dotenv import load_dotenv

load_dotenv()

# QdrantClient defaults to port 6333 which causes timeouts with HTTPS endpoints if not explicitly handled.
if os.getenv("QDRANT_HOST", "").startswith("https://") and os.getenv("QDRANT_PORT") == "6333":
    print("Adjusting QDRANT_PORT to 443 for HTTPS connection in server startup")
    os.environ["QDRANT_PORT"] = "443"

from agent_framework.azure import AzureOpenAIChatClient
from agent_framework import ChatMessage

from agents.agent_framework_memory_agent import AgentFrameworkMemoryAgent
from agents.cognee_agent import CogneeAgent
from agents.hindsight_agent import HindsightAgent
from agents.mem0_agent import Mem0Agent
from tools.mem0_tool import Mem0Tool
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is not set.")
    return value


async def check_qdrant_health():
    """Check if Qdrant is running and accessible"""
    qdrant_host = os.getenv("QDRANT_HOST")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{qdrant_host}")
            if response.status_code == 200:
                print(f"✓ Qdrant is running and accessible at {qdrant_host}")
                return True
            else:
                print(f"✗ Qdrant returned status code {response.status_code}")
                return False
    except Exception as e:
        print(f"✗ Qdrant is not accessible at {qdrant_host}")
        return False

async def check_hindsight_health():
    """Check if Hindsight is running and accessible"""
    hindsight_url = os.getenv("HINDSIGHT_URL", "http://localhost:8888")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{hindsight_url}/health")
            if response.status_code == 200:
                print(f"✓ Hindsight is running and accessible at {hindsight_url}")
                return True
            else:
                print(f"✗ Hindsight returned status code {response.status_code}")
                return False
    except Exception as e:
        print(f"✗ Hindsight is not accessible at {hindsight_url}: {str(e)}")
        return False

@app.get("/")
async def read_root():
    qdrant_healthy = await check_qdrant_health()
    hindsight_healthy = await check_hindsight_health()
    return {"Hello": "Agentic World", "Qdrant Healthy": qdrant_healthy, "Hindsight Healthy": hindsight_healthy}


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    username: str
    messages: List[Message] = Field(default_factory=list)
    query: Optional[str] = None


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is not set.")
    return value


def _normalize_usage(usage: Any) -> Optional[dict[str, int]]:
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


client = AzureOpenAIChatClient(
    api_key=_require_env("AZURE_OPENAI_API_KEY"),
    endpoint=_require_env("AZURE_OPENAI_ENDPOINT"),
    deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT") or "gpt-5-mini",
)

gpt_4_client = AzureOpenAIChatClient(
    api_key=_require_env("AZURE_OPENAI_API_KEY"),
    endpoint=_require_env("AZURE_OPENAI_ENDPOINT"),
    deployment_name=os.getenv("GPT4_DEPLOYMENT_NAME") or "gpt-5-mini",
)


grok_client = AzureOpenAIChatClient(
    api_key=_require_env("AZURE_OPENAI_API_KEY"),
    endpoint=_require_env("AZURE_OPENAI_ENDPOINT"),
    deployment_name=os.getenv("GROK_DEPLOYMENT_NAME") or "gpt-5-mini",
)

deepseek_client = AzureOpenAIChatClient(
    api_key=_require_env("AZURE_OPENAI_API_KEY"),
    endpoint=_require_env("AZURE_OPENAI_ENDPOINT"),
    deployment_name=os.getenv("DEEPSEEK_DEPLOYMENT_NAME") or "gpt-5-mini",
)

# Create a single, persistent agent instance with memory
# This ensures memory persists across requests for all users
print("Initializing Agent Framework Memory Agent...")
agent_framework_memory_agent = AgentFrameworkMemoryAgent(client).get_agent_framework_memory_agent()
mem0_agent = Mem0Agent(grok_client).get_mem0_agent()
mem0_memory_reader = Mem0Tool()
hindsight_agent = HindsightAgent(client).get_hindsight_agent()
cognee_agent = CogneeAgent(grok_client).get_cognee_agent()
print("Agent initialized and ready")

# Store agent instances per user - each user gets their own agent with isolated memory.
# We can store this data in a database (like Cosoms DB) for persistence across server restarts.
# But for simplicity, we'll keep it in memory for now.
print("Agent Framework Memory system initialized")
user_agents = {}
user_threads = {}


@app.post("/")
async def generic_agent(request: ChatRequest):
    print(f"Received request for Generic Agent from user: {request.username}")
    
    messages = [
        ChatMessage(role="system", text=f"You are assisting user {request.username}"),
        *(
            ChatMessage(role=m.role, text=m.content)
            for m in request.messages
        ),
    ]

    response = await gpt_4_client.get_response(messages)
    usage = _normalize_usage(response.usage_details)

    if usage is None:
        return {"message": response.messages[0].text}
    return {"message": response.messages[0].text, "usage": usage}

@app.post("/agent-framework")
async def agent_framework(request: ChatRequest):
    print(f"Received request for Agent Framework Memory Agent from user: {request.username}")
    
    # Get or create an agent for this specific user
    if request.username not in user_agents:
        print(f"Creating new agent instance for user: {request.username}")
        user_agents[request.username] = AgentFrameworkMemoryAgent(client).get_agent_framework_memory_agent()
    
    agent = user_agents[request.username]
    
    # Get or create a thread for this user
    if request.username not in user_threads:
        print(f"Creating new thread for user: {request.username}")
        user_threads[request.username] = agent.get_new_thread()
    
    thread = user_threads[request.username]
    
    messages = [
        ChatMessage(role="system", text=f"You are assisting user {request.username}"),
        *(
            ChatMessage(role=m.role, text=m.content)
            for m in request.messages
        ),
    ]

    response = await agent.run(messages, thread=thread)
    usage = _normalize_usage(response.usage_details)
    print(response.usage_details)
    if usage is None:
        return {"message": response.messages[0].text}
    return {"message": response.messages[0].text, "usage": usage}

@app.post("/agent-framework/memories")
async def get_memories(request: ChatRequest):
    print(f"Received request to get memories for user: {request.username}")
    
    # Get the user's agent if it exists
    if request.username not in user_agents:
        return {"message": "No memories found for this user"}
    
    agent = user_agents[request.username]
    
    # Access the memory from the agent's context provider (ClientDetailsMemoryTool)
    context_provider = agent.context_provider
    if context_provider and hasattr(context_provider, '_user_info'):
        user_info = context_provider._user_info
        memories = {
            "username": user_info.username,
            "spa_preferences": user_info.spa_preferences,
            "preferred_hours": user_info.preferred_hours,
        }
    else:
        memories = "No memories stored"
    
    return {
        "message": memories,
    }
    
@app.delete("/agent-framework/delete/{username}")
async def delete_agent_framework_memory(username: str):
    print(f"Received request to delete Agent Framework Memory Agent for user: {username}")
    if username in user_agents:
        del user_agents[username]
    if username in user_threads:
        del user_threads[username]
    return {"message": f"Deleted Agent Framework Memory Agent for user: {username}"}


@app.post("/mem0")
async def mem0(request: ChatRequest):
    print(f"Received request for Mem0 Agent from user: {request.username}")
    messages = [
        ChatMessage(role="system", text=f"You are assisting user {request.username}"),
        *(
            ChatMessage(role=m.role, text=m.content)
            for m in request.messages
        ),
    ]

    response = await mem0_agent.run(messages, username=request.username)
    usage = _normalize_usage(response.usage_details)
    print(response.usage_details)
    if usage is None:
        return {"message": response.messages[0].text}
    return {"message": response.messages[0].text, "usage": usage}

@app.post("/mem0/memories")
async def mem0_get_memories(request: ChatRequest):
    print(f"Received request to get Mem0 memories for user: {request.username}")
    memories = await mem0_memory_reader.get_memories(
        request.username,
        query=request.query,
        limit=10,
    )
    return {
        "message": memories,
    }


@app.post("/cognee")
async def cognee(request: ChatRequest):
    print(f"Received request for Cognee Agent from user: {request.username}")
    messages = [
        ChatMessage(role="system", text=f"You are assisting user {request.username}"),
        *(
            ChatMessage(role=m.role, text=m.content)
            for m in request.messages
        ),
    ]

    response = await cognee_agent.run(messages, username=request.username)
    usage = _normalize_usage(response.usage_details)
    return {
        "message": response.messages[0].text,
        "usage": usage,
    }

@app.post("/cognee/memories")
async def cognee_get_memories(request: ChatRequest):
    print(f"Received request to get Cognee memories for user: {request.username}")
    context_provider = cognee_agent.context_provider

    memories = await context_provider.get_memories(request.username)
    print("Retrieved memories:", memories)

    return {"message": memories}

@app.delete("/cognee/delete/{username}")
async def delete_cognee_memory(username: str):
    print(f"Received request to delete Cognee memory for user: {username}")

    context_provider = cognee_agent.context_provider
    if not context_provider or not hasattr(context_provider, "delete_user_memories"):
        raise HTTPException(status_code=500, detail="Cognee context provider does not support deletion")

    try:
        result = await context_provider.delete_user_memories(username)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete Cognee memories: {exc}")

    if not result.get("deleted"):
        return {"message": f"No Cognee dataset found for user: {username}", **result}
    return {"message": f"Deleted all Cognee memories for user: {username}", **result}


@app.post("/hindsight")
async def hindsight(request: ChatRequest):
    print(f"Received request for Hindsight Agent from user: {request.username}")
    messages = [
        ChatMessage(role="system", text=f"You are assisting user {request.username}"),
        *(
            ChatMessage(role=m.role, text=m.content)
            for m in request.messages
        ),
    ]
    response = await hindsight_agent.run(messages, username=request.username)
    usage = _normalize_usage(response.usage_details)
    if usage is None:
        return {"message": response.messages[0].text}
    return {"message": response.messages[0].text, "usage": usage}

@app.post("/hindsight/memories")
async def hindsight_get_memories(request: ChatRequest):
    print(f"Received request to get Hindsight memories for user: {request.username}")
    context_provider = hindsight_agent.context_provider

    memories = await context_provider.get_memories(request.username)
    print("Retrieved memories:", memories)

    return {"message": memories.text}

