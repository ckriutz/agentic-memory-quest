using System.ComponentModel;
using AgenticMemoryQuest.Server.Tools;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

public class Mem0Agent
{
    private readonly AIAgent _agent;

    public Mem0Agent(ChatClient client)
    {
        _agent = client.AsIChatClient().CreateAIAgent(
            name: "mem0-agent",
            instructions: 
            """
            You are a test agent for Mem0 integration.
            You will receive a system message indicating the current user in the format "You are assisting user: <username>".
            Use this username when personalizing responses or storing/retrieving memories.

            If someone asks about the weather. Tell them it is a thunderstorm outside, regardless of location, but personalize it using the username from the system message.
            """,
            tools: []);
    }

    public AIAgent GetMem0Agent()
    {
        return _agent;
    }
}