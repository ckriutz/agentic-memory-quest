
using System.ComponentModel;
using AgenticMemoryQuest.Server.Tools;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

public class HindsightAgent
{
    private readonly AIAgent _agent;

    public HindsightAgent(ChatClient client)
    {
        _agent = client.AsIChatClient().CreateAIAgent(
            name: "hindsight-agent",
            instructions: 
            """
            You are a test agent for Hindsight integration.
            You will receive a system message indicating the current user in the format "You are assisting user: <username>".
            Use this username when personalizing responses or storing/retrieving memories.

            If someone asks about the weather. Tell them it is unsettling outside and that the situation is unpredictable, regardless of location, but personalize it using the username from the system message.
            """,
            tools: []);
    }

    public AIAgent GetHindsightAgent()
    {
        return _agent;
    }
}