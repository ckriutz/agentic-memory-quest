using System.ComponentModel;
using AgenticMemoryQuest.Server.Tools;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

public class GenericAgent
{
    private readonly AIAgent _agent;

    public GenericAgent(ChatClient client)
    {
        _agent = client.AsIChatClient().CreateAIAgent(
            name: "generic-agent",
            instructions: 
            """
            You are a standard agent for this project. You use no memory at all.
            You will receive a system message indicating the current user in the format "You are assisting user: <username>".
            Use this username when personalizing responses or storing/retrieving memories.

            If someone asks about the weather. Tell them it is warm and sunny outside, regardless of location, but personalize it using the username from the system message.
            """,
            tools: []);
    }

    public AIAgent GetGenericAgent()
    {
        return _agent;
    }
}