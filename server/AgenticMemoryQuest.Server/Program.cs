
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.AddAGUI();

string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") 
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT environment variable is not set.");
string deploymentName = "gpt-5-mini"; // Update this to match your actual deployment name

// Create the client, connecting to Microsoft Foundry.
ChatClient client = new AzureOpenAIClient(new Uri(endpoint),new DefaultAzureCredential()).GetChatClient(deploymentName);

// Create the sample Weather Agent
WeatherAgent weatherAgent = new WeatherAgent(client);

// Create the simple agent
AIAgent genericAgent = client.AsIChatClient().CreateAIAgent(
    name: "orchestrator-agent",
    instructions:
        """
        You are an intelligent routing assistant. You coordinate with specialized agents to help users.

        When a user asks for weather information, you should use the Weather Agent to get the data.
        The Weather Agent returns weather information in a JSON format, so be sure to pass that JSON back to the user directly.
        """,
    tools: 
    [
        AIFunctionFactory.Create(weatherAgent.InvokeAsync, description: "Get weather information for a location. Pass the user's weather request as the parameter.")
    ]
);

// Add CORS
builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        policy.AllowAnyOrigin()
              .AllowAnyHeader()
              .AllowAnyMethod();
    });
});

// Add services to the container.
// Learn more about configuring OpenAPI at https://aka.ms/aspnet/openapi
builder.Services.AddOpenApi();

var app = builder.Build();

// Configure the HTTP request pipeline.
if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
}

app.UseHttpsRedirection();

app.UseCors();

// Map the AG-UI agent endpoint
app.MapAGUI("/", genericAgent);


app.Run();



