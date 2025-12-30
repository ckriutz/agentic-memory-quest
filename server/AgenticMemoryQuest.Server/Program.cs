
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

// Create the Prescription Agent
PrescriptionAgent prescriptionAgent = new PrescriptionAgent(client);

// Create the simple agent
AIAgent genericAgent = client.AsIChatClient().CreateAIAgent(
    name: "orchestrator-agent",
    instructions:
        """
        You are an intelligent routing assistant. You coordinate with specialized agents to help users.
        Any general questions should be answered directly by you in a friendly, helpful manner.

        IMPORTANT: You will receive a system message indicating the current user in the format "You are assisting user: <username>".
        Extract this username for use when routing to specialized agents.

        When a user asks for weather information (e.g., "what's the weather in X", "how's the weather"), use the Weather Agent to get the data.
        You don't need any additional information from the user to get weather data other than their location.
        The Weather Agent returns weather information in a JSON format, so be sure to pass that JSON back to the user directly.

        When a user explicitly asks about prescriptions or medications (e.g., "what prescriptions do I have", "show my medications", "add a prescription"), use the Prescription Agent.
        IMPORTANT: When calling the Prescription Agent, you MUST prepend "[User: <username>]" (using the username from the system message) to the user's request.
        For example, if the user is "kurt" and they ask "what prescriptions do I have", pass "[User: kurt] what prescriptions do I have" to the Prescription Agent.
        When the Prescription Agent has all the information it needs, it returns information in a JSON format, so be sure to pass that JSON back to the user directly.
        When the Prescription Agent needs more information, it will ask clarifying questions - simply relay those questions to the user.
        
        Do NOT route to the Prescription Agent for general questions, greetings, or weather queries - only for explicit prescription/medication requests.
        """,
    tools: 
    [
        AIFunctionFactory.Create(weatherAgent.InvokeAsync, description: "Get weather information for a location. Pass the user's weather request as the parameter."),
        AIFunctionFactory.Create(prescriptionAgent.InvokeAsync, description: "Get, add, update, or delete prescription information for a user. Pass the user's prescription request as the parameter.")
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



