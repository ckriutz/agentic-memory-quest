using System.ComponentModel;
using AgenticMemoryQuest.Server.Tools;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

public class CogneeAgent
{
    private readonly AIAgent _agent;

    public CogneeAgent(ChatClient client)
    {
        _agent = client.AsIChatClient().CreateAIAgent(
            name: "cognee-agent",
            instructions: 
            """
            You are a test agent for Cognee integration.
            You will receive a system message indicating the current user in the format "You are assisting user: <username>".
            Use this username when personalizing responses or storing/retrieving memories.

            If someone asks about the weather. Tell them it is really windy outside, regardless of location, but personalize it using the username from the system message.
            """,
            tools: []);
    }

    public AIAgent GetCogneeAgent()
    {
        return _agent;
    }
}