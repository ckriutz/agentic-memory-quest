
using System.Xml.Schema;
using System.Collections.Concurrent;
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

var userThreads = new ConcurrentDictionary<string, AgentThread>();

// Create the client, connecting to Microsoft Foundry.
//ChatClient client = new AzureOpenAIClient(new Uri(endpoint),new DefaultAzureCredential()).GetChatClient(deploymentName);

// Same, but with Key authentication (for local testing)
string apiKey = Environment.GetEnvironmentVariable("AZURE_OPENAI_API_KEY") 
    ?? throw new InvalidOperationException("AZURE_OPENAI_API_KEY environment variable is not set.");
ChatClient client = new AzureOpenAIClient(new Uri(endpoint), new Azure.AzureKeyCredential(apiKey)).GetChatClient(deploymentName);

// Create the sample Weather Agent
WeatherAgent weatherAgent = new WeatherAgent(client);

// Here is the generic agent that does not use memory.
GenericAgent genericAgent = new GenericAgent(client);

// Here is the agent that uses Mem0 for memory.
Mem0Agent mem0Agent = new Mem0Agent(client);

// Create a test agent for Agent Framework Memory integration (not used in the orchestrator agent)
AgentFrameworkMemoryAgent afMemoryAgent = new AgentFrameworkMemoryAgent(client);

HindsightAgent hindsightAgent = new HindsightAgent(client);

CogneeAgent cogneeAgent = new CogneeAgent(client);

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
app.MapPost("/", async (HttpContext context, ChatRequest request) =>
{
    // This method will prepare the data for the agent and call it.
    var message = request.Messages.LastOrDefault(m => m.Role == "user")?.Content ?? "";
    Console.WriteLine($"Received request for Generic Agent from user: {request.Username}");

    // Prepend username as a system message
    var messagesWithUser = new List<Microsoft.Extensions.AI.ChatMessage>
    {
        new Microsoft.Extensions.AI.ChatMessage(ChatRole.System, $"You are assisting user: {request.Username}")
    };

    // Add conversation History
    messagesWithUser.AddRange(request.Messages.Select(m => new Microsoft.Extensions.AI.ChatMessage(m.Role == "user" ? ChatRole.User : ChatRole.Assistant, m.Content)));

    var response = await genericAgent.GetGenericAgent().RunAsync(messagesWithUser.ToArray(), thread: null);

    Console.WriteLine("Generic Agent Response: " + response.Messages.LastOrDefault()?.Text);
    return Results.Ok(new 
    { 
        message = response.Messages.LastOrDefault()?.Text,
        usage = new 
        {
            inputTokenCount = response.Usage.InputTokenCount,
            outputTokenCount = response.Usage.OutputTokenCount,
            totalTokenCount = response.Usage.TotalTokenCount
        }
    });
});


app.MapPost("/agent-framework", async (HttpContext context, ChatRequest request) =>
{
    // This method, like the others, will prepare the data for the agent and call it.
    var message = request.Messages.LastOrDefault(m => m.Role == "user")?.Content ?? "";
    Console.WriteLine($"Received request for Agent Framework Memory Agent from user: {request.Username}");

    // Create or reuse a thread per user
    var thread = userThreads.GetOrAdd(request.Username, _ =>
    {
        var t = afMemoryAgent.GetAgentFrameworkMemoryAgent().GetNewThread();
        Console.WriteLine($"Created new AgentThread for user: {request.Username}");
        return t;
    });

    // Prepend username as a system message
    var messagesWithUser = new List<Microsoft.Extensions.AI.ChatMessage>
    {
        new Microsoft.Extensions.AI.ChatMessage(ChatRole.System, $"You are assisting user: {request.Username}")
    };

    // Add conversation History
    messagesWithUser.AddRange(request.Messages.Select(m => new Microsoft.Extensions.AI.ChatMessage(m.Role == "user" ? ChatRole.User : ChatRole.Assistant, m.Content)));

    var response = await afMemoryAgent.GetAgentFrameworkMemoryAgent().RunAsync(messagesWithUser.ToArray(), thread: thread);

    Console.WriteLine("Agent Framework Memory Agent Response: " + response.Messages.LastOrDefault()?.Text);
    return Results.Ok(new 
    { 
        message = response.Messages.LastOrDefault()?.Text,
        usage = new 
        {
            inputTokenCount = response.Usage.InputTokenCount,
            outputTokenCount = response.Usage.OutputTokenCount,
            totalTokenCount = response.Usage.TotalTokenCount
        }
    });
    
});

app.MapPost("/mem0", async (HttpContext context, ChatRequest request) =>
{
    // This method, like the others, will prepare the data for the agent and call it.
    var message = request.Messages.LastOrDefault(m => m.Role == "user")?.Content ?? "";
    Console.WriteLine($"Received request for Mem0 Agent from user: {request.Username}");
    // Prepend username as a system message
    var messagesWithUser = new List<Microsoft.Extensions.AI.ChatMessage>
    {
        new Microsoft.Extensions.AI.ChatMessage(ChatRole.System, $"You are assisting user: {request.Username}")
    };

    // Add conversation History
    messagesWithUser.AddRange(request.Messages.Select(m => new Microsoft.Extensions.AI.ChatMessage(m.Role == "user" ? ChatRole.User : ChatRole.Assistant, m.Content)));

    var response = await mem0Agent.GetMem0Agent().RunAsync(messagesWithUser.ToArray(), thread: null);

    Console.WriteLine("Mem0 Agent Response: " + response.Messages.LastOrDefault()?.Text);
    return Results.Ok(new 
    { 
        message = response.Messages.LastOrDefault()?.Text,
        usage = new 
        {
            inputTokenCount = response.Usage.InputTokenCount,
            outputTokenCount = response.Usage.OutputTokenCount,
            totalTokenCount = response.Usage.TotalTokenCount
        }
    });
    
});

app.MapPost("/cognee", async (HttpContext context, ChatRequest request) =>
{
    // This method will prepare the data for the agent and call it.
    var message = request.Messages.LastOrDefault(m => m.Role == "user")?.Content ?? "";
    Console.WriteLine($"Received request for Cognee Agent from user: {request.Username}");
    // Prepend username as a system message
    var messagesWithUser = new List<Microsoft.Extensions.AI.ChatMessage>
    {
        new Microsoft.Extensions.AI.ChatMessage(ChatRole.System, $"You are assisting user: {request.Username}")
    };

    // Add conversation History
    messagesWithUser.AddRange(request.Messages.Select(m => new Microsoft.Extensions.AI.ChatMessage(m.Role == "user" ? ChatRole.User : ChatRole.Assistant, m.Content)));

    var response = await cogneeAgent.GetCogneeAgent().RunAsync(messagesWithUser.ToArray(), thread: null);

    Console.WriteLine("Cognee Agent Response: " + response.Messages.LastOrDefault()?.Text);
    return Results.Ok(new 
    { 
        message = response.Messages.LastOrDefault()?.Text,
        usage = new 
        {
            inputTokenCount = response.Usage.InputTokenCount,
            outputTokenCount = response.Usage.OutputTokenCount,
            totalTokenCount = response.Usage.TotalTokenCount
        }
    });
});

app.MapPost("/hindsight", async (HttpContext context, ChatRequest request) =>
{
    // This method will prepare the data for the agent and call it.
    var message = request.Messages.LastOrDefault(m => m.Role == "user")?.Content ?? "";
    Console.WriteLine($"Received request for Hindsight Agent from user: {request.Username}");
    // Prepend username as a system message
    var messagesWithUser = new List<Microsoft.Extensions.AI.ChatMessage>
    {
        new Microsoft.Extensions.AI.ChatMessage(ChatRole.System, $"You are assisting user: {request.Username}")
    };

    // Add conversation History
    messagesWithUser.AddRange(request.Messages.Select(m => new Microsoft.Extensions.AI.ChatMessage(m.Role == "user" ? ChatRole.User : ChatRole.Assistant, m.Content)));

    var response = await hindsightAgent.GetHindsightAgent().RunAsync(messagesWithUser.ToArray(), thread: null);

    Console.WriteLine("Hindsight Agent Response: " + response.Messages.LastOrDefault()?.Text);
    return Results.Ok(new 
    { 
        message = response.Messages.LastOrDefault()?.Text,
        usage = new 
        {
            inputTokenCount = response.Usage.InputTokenCount,
            outputTokenCount = response.Usage.OutputTokenCount,
            totalTokenCount = response.Usage.TotalTokenCount
        }
    });
});


app.Run();

record ChatRequest(string Username, List<Message> Messages);
record Message(string Role, string Content);