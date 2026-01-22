using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

public class ClientDetailsMemoryTool : AIContextProvider
{  
    public readonly IChatClient _chatClient;
    public ClientDetailsModels UserInfo { get; set; }

    public ClientDetailsMemoryTool(IChatClient chatClient, JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        _chatClient = chatClient;
        UserInfo = serializedState.ValueKind == JsonValueKind.Object ? serializedState.Deserialize<ClientDetailsModels>(jsonSerializerOptions)! : new ClientDetailsModels();
    }
    public ClientDetailsMemoryTool(IChatClient chatClient, ClientDetailsModels? userInfo = null)
    {
        _chatClient = chatClient;
        UserInfo = userInfo ?? new ClientDetailsModels();
    }

    // This runs *after* the agent receives a response.
    // This is where you inspect what happened and update your state.
    // In a memory component, this is where you’d extract new information from the conversation to remember for next time.
    public override async ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        Console.WriteLine("Invoked ClientDetailsMemoryTool to extract client details from conversation.");
        //Console.WriteLine($"Context has {context.RequestMessages.Count()} request messages and {context.ResponseMessages.Count()} response messages");

        var schema = AIJsonUtilities.CreateJsonSchema(typeof(ClientDetailsModels));

        ChatOptions chatOptions = new ChatOptions()
        {
            Instructions = """
                You are a data extraction assistant. Extract the following information from the conversation:
                - username: The user's name or username
                - spaPreferences: Any spa or wellness preferences mentioned such as massage types, treatments, facials, etc.
                - preferredHours: Any time preferences mentioned, like they don't like mornings, prefer afternoons, evenings, weekends, etc.
                
                Respond with ONLY a valid JSON object in this exact format, no other text:
                {"username":"value","spaPreferences":"value","preferredHours":"value"}
                
                Use "Unknown" for any field you cannot determine.
                """,
                ResponseFormat = ChatResponseFormat.ForJsonSchema(
                    schema: schema,
                    schemaName: "ClientDetails",
                    schemaDescription: "Client details including username, spa preferences, and preferred hours.")
        };

        try
        {
            var result = await _chatClient.GetResponseAsync<ClientDetailsModels>(context.RequestMessages, chatOptions, cancellationToken: cancellationToken);
            UserInfo.Username = result.Result.Username;
            UserInfo.PreferredHours = result.Result.PreferredHours;
            UserInfo.SpaPreferences = result.Result.SpaPreferences;
        }
        catch (JsonException ex)
        {
            Console.WriteLine("Error serializing extracted client details: " + ex.Message);
        }
        catch (Exception ex)
        {
            Console.WriteLine("Error extracting client details: " + ex.Message);
        }
    }

    // This runs before each agent invocation.
    // This is where you inject context into the request.
    // You can provide additional instructions, tools, or messages that will be merged with the agent’s existing context.
    // If your memory component knows the user’s preferences or history, this is where you’d add that to the conversation.
    public override ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        Console.WriteLine("Providing Client Details as AI Context.");
        var contextMessage = $"""
            Client Details:
            - Username: {UserInfo.Username ?? "Unknown"}
            - Spa Preferences: {UserInfo.SpaPreferences ?? "Unknown"}
            - Preferred Hours: {UserInfo.PreferredHours ?? "Unknown"}
            """;
        
        return ValueTask.FromResult(new AIContext()
        {
            Messages = [new Microsoft.Extensions.AI.ChatMessage(Microsoft.Extensions.AI.ChatRole.System, contextMessage)]
        });
    }
}

public class ClientDetailsModels
{
    [JsonPropertyName("username")]
    public string? Username { get; set; }
    
    [JsonPropertyName("spaPreferences")]
    public string? SpaPreferences { get; set; }
    
    [JsonPropertyName("preferredHours")]
    public string? PreferredHours { get; set; }
}