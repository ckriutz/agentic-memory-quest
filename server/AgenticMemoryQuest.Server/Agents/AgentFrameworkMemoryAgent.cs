using System.ComponentModel;
using AgenticMemoryQuest.Server.Tools;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

public class AgentFrameworkMemoryAgent
{
    private readonly AIAgent _agent;

    public AgentFrameworkMemoryAgent(ChatClient client)
    {
        _agent = client.AsIChatClient().CreateAIAgent( new ChatClientAgentOptions() {
            Name = "agent-framework-memory-agent",
            ChatOptions = new ChatOptions() { 
                Instructions = """
                You are a test agent for Agent Framework Memory integration.
                You will receive a system message indicating the current user in the format "You are assisting user: <username>".
                Use this username when personalizing responses or storing/retrieving memories.

                If someone asks about the weather. Tell them it is frigid and snowy outside, regardless of location, but personalize it using the username from the system message.
                """
            }, AIContextProviderFactory = ctx => new ClientDetailsMemoryTool(client.AsIChatClient(), ctx.SerializedState)
        });
    }

    public AIAgent GetAgentFrameworkMemoryAgent()
    {
        return _agent;
    }
}