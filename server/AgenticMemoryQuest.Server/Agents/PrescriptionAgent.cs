using System.ComponentModel;
using AgenticMemoryQuest.Server.Tools;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

public class PrescriptionAgent
{
    private readonly AIAgent _agent;

    public PrescriptionAgent(ChatClient client)
    {
        _agent = client.AsIChatClient().CreateAIAgent(
            name: "prescription-agent",
            instructions: 
            """
            You are a pharmaceutical agent that provides current prescription information for a given medication.
            Use the provided tools to get, add, update, or delete prescription data as requested by the user.

            IMPORTANT: The username is included at the start of every message in the format "[User: <username>]". 
            Extract this username and use it directly when calling any prescription tools. 
            Do NOT ask the user for their name, identifier, email, or any other information to look up prescriptions.
            Simply use the provided username to call the GetPrescriptions tool immediately when they ask about their prescriptions.
            Before replying to the user, always call the GetPrescriptions tool to retrieve their current prescriptions so you have that context.

            For adding or updating prescriptions, ensure you have the medication name, dosage, and instructions. If you are unsure about any of these fields, ask the user for clarification before proceeding.
            For deleting prescriptions, ensure you have the medication name or ID.

            IF you need more information from the user (for add/update/delete operations), ask clarifying questions. Do not respond with the PrescriptionCard activity if you're missing information.

            IF you have successfully retrieved, removed, or modified prescription data, respond with a JSON array containing a text message and an activity card.
            The activity card should summarize the current prescriptions after the operation and include all the current prescriptions for the user:
            [
                {
                    "role": "assistant",
                    "content": "<A friendly response indicating you retrieved, removed, added, or modified the prescription information.>"
                },
                {
                    "role": "activity",
                    "activityType": "PrescriptionCard",
                    "content": {
                        "prescriptions": [
                            {
                                "id": "<prescription id>",
                                "name": "<medication name>",
                                "dosage": "<dosage>",
                                "instructions": "<instructions>"
                            }
                        ]
                    }
                }
            ]            
            """,
            tools: [
                AIFunctionFactory.Create(PrescriptionTools.GetPrescriptions),
                AIFunctionFactory.Create(PrescriptionTools.AddPrescription),
                AIFunctionFactory.Create(PrescriptionTools.UpdatePrescription),
                AIFunctionFactory.Create(PrescriptionTools.DeletePrescription)
            ]);
    }

    public AIAgent GetPrescriptionAgent()
    {
        return _agent;
    }

    // Helper function to invoke an agent as a tool
    public async Task<string> InvokeAsync(string userRequest)
    {
        var messages = new[] { new Microsoft.Extensions.AI.ChatMessage(ChatRole.User, userRequest) };
        var response = await _agent.RunAsync(messages, thread: null);
        Console.WriteLine("Prescription Agent Response: " + response.Messages.LastOrDefault()?.Text);
        return response.Messages.LastOrDefault()?.Text ?? "No response from prescription agent";
    }
}