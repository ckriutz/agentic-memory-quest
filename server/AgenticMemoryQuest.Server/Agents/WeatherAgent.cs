using System.ComponentModel;
using AgenticMemoryQuest.Server.Tools;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

public class WeatherAgent
{
    private readonly AIAgent _agent;

    public WeatherAgent(ChatClient client)
    {
        _agent = client.AsIChatClient().CreateAIAgent(
            name: "weather-agent",
            instructions: 
                """
                You are a weather agent that provides current weather information for a given location.
                Use the provided tool to get the weather data, and return the values in the specified format.
                Return the weather in this format, as valid JSON:
                {
                    "id": "<some unique id>",
                    "role": "activity",
                    "activityType": "WeatherCard",
                    "content": {
                        "location": "<users location>",
                        "temperatureC": number,
                        "humidityPct": number,
                        "windKph": number,
                        "conditions": "string",
                        "source": "string"
                    }
                }
                """,
            tools: [AIFunctionFactory.Create(WeatherTools.GetWeather)]);
    }

    public AIAgent GetWeatherAgent()
    {
        return _agent;
    }

    // Helper function to invoke an agent as a tool
    public async Task<string> InvokeAsync(string userRequest)
    {
        var messages = new[] { new Microsoft.Extensions.AI.ChatMessage(ChatRole.User, userRequest) };
        var response = await _agent.RunAsync(messages, thread: null);
        Console.WriteLine("Weather Agent Response: " + response.Messages.LastOrDefault()?.Text);
        return response.Messages.LastOrDefault()?.Text ?? "No response from weather agent";
    }
}