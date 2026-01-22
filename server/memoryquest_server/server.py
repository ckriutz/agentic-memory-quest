from agent_framework.azure import AzureOpenAIChatClient
from agent_framework import ChatMessage
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agents.agent_framework_memory_agent import AgentFrameworkMemoryAgent
from typing import List, Literal, Optional, Any
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def read_root():
    return {"Hello": "Agentic World"}


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    username: str
    messages: List[Message]


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is not set.")
    return value


client = AzureOpenAIChatClient(
    api_key=_require_env("AZURE_OPENAI_API_KEY"),
    endpoint=_require_env("AZURE_OPENAI_ENDPOINT"),
    deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT") or "gpt-5-mini",
)

# Create a single, persistent agent instance with memory
# This ensures memory persists across requests for all users
print("Initializing Agent Framework Memory Agent...")
agent_framework_memory_agent = AgentFrameworkMemoryAgent(client).get_agent_framework_memory_agent()
print("Agent initialized and ready")

# Store agent instances per user - each user gets their own agent with isolated memory.
# We can store this data in a database (like Cosoms DB) for persistence across server restarts.
# But for simplicity, we'll keep it in memory for now.
print("Agent Framework Memory system initialized")
user_agents = {}
user_threads = {}


def _build_messages(request: ChatRequest) -> List[dict]:
    messages = [{"role": "system", "content": f"You are assisting user: {request.username}"}]
    messages.extend({"role": m.role, "content": m.content} for m in request.messages)
    return messages


# Destroy this soon.
def _run_chat(messages: List[dict]) -> Any:
    # Attempt common method names for the AzureOpenAIChatClient.
    if hasattr(chat_client, "complete"):
        return chat_client.complete(messages)
    if hasattr(chat_client, "chat"):
        return chat_client.chat(messages)
    if hasattr(chat_client, "create"):
        return chat_client.create(messages=messages)
    raise NotImplementedError("Chat client method not found.")

# Destroy this soon.
def _extract_text_and_usage(response: Any) -> tuple[Optional[str], dict]:
    if isinstance(response, dict):
        text = response.get("message") or response.get("text") or response.get("content")
        usage = response.get("usage") or {}
        return text, usage

    text = (
        getattr(response, "message", None)
        or getattr(response, "text", None)
        or getattr(response, "content", None)
    )

    usage_obj = getattr(response, "usage", None)
    usage = {}
    if usage_obj:
        usage = {
            "inputTokenCount": getattr(usage_obj, "input_token_count", None)
            or getattr(usage_obj, "inputTokenCount", None),
            "outputTokenCount": getattr(usage_obj, "output_token_count", None)
            or getattr(usage_obj, "outputTokenCount", None),
            "totalTokenCount": getattr(usage_obj, "total_token_count", None)
            or getattr(usage_obj, "totalTokenCount", None),
        }
    return text, usage

# Destroy this soon.
def _handle_request(request: ChatRequest) -> dict:
    messages = _build_messages(request)

    try:
        response = _run_chat(messages)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))

    message_text, usage = _extract_text_and_usage(response)
    
    return {
        "message": message_text,
        "usage": {
            "inputTokenCount": usage.get("inputTokenCount"),
            "outputTokenCount": usage.get("outputTokenCount"),
            "totalTokenCount": usage.get("totalTokenCount"),
        },
    }


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

    response = await client.get_response(messages)
    usage = response.usage_details

    return {
        "message": response.messages[0].text,
        "usage": {
            "inputTokenCount": usage.input_token_count,
            "outputTokenCount": usage.output_token_count,
            "totalTokenCount": usage.total_token_count
        },
    }


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
    usage = response.usage_details
    return {
        "message": response.messages[0].text,
        "usage": {
            "inputTokenCount": usage.input_token_count,
            "outputTokenCount": usage.output_token_count,
            "totalTokenCount": usage.total_token_count,
        },
    }


@app.post("/mem0")
def mem0(request: ChatRequest):
    return _handle_request(request)


@app.post("/cognee")
def cognee(request: ChatRequest):
    return _handle_request(request)


@app.post("/hindsight")
def hindsight(request: ChatRequest):
    return _handle_request(request)

