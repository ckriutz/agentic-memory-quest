using System.ComponentModel;
using System.Text.Json;

namespace AgenticMemoryQuest.Server.Tools;

public static class PrescriptionTools
{
    private static readonly string PrescriptionFilePath = 
        Path.Combine(AppContext.BaseDirectory, "Tools", "prescriptions.json");

    /// <summary>
    /// Get all prescriptions for a specific user.
    /// </summary>
    [Description("Get all prescriptions for a user")]
    public static object GetPrescriptions(
        [Description("The username to retrieve prescriptions for")]
        string user)
    {
        Console.WriteLine($"Fetching prescriptions for user: {user}");
        
        try
        {
            if (!File.Exists(PrescriptionFilePath))
            {
                return new { success = false, message = "No prescriptions file found", prescriptions = new List<object>() };
            }

            var json = File.ReadAllText(PrescriptionFilePath);
            if (string.IsNullOrWhiteSpace(json))
            {
                return new { success = true, message = "No prescriptions found for user", prescriptions = new List<object>() };
            }

            var allPrescriptions = JsonSerializer.Deserialize<List<Dictionary<string, object>>>(json) ?? new List<Dictionary<string, object>>();
            var userPrescriptions = allPrescriptions
                .Where(p => p.ContainsKey("user") && p["user"].ToString()!.Equals(user, StringComparison.OrdinalIgnoreCase))
                .ToList();

            return new { success = true, message = $"Found {userPrescriptions.Count} prescriptions", prescriptions = userPrescriptions };
        }
        catch (Exception ex)
        {
            return new { success = false, message = $"Error retrieving prescriptions: {ex.Message}", prescriptions = new List<object>() };
        }
    }

    /// <summary>
    /// Add a new prescription for a user.
    /// </summary>
    [Description("Add a new prescription for a user")]
    public static object AddPrescription(
        [Description("The username")]
        string user,
        [Description("The medication name")]
        string name,
        [Description("The dosage (e.g., '300MG')")]
        string dosage,
        [Description("Instructions for taking the medication")]
        string instructions)
    {
        Console.WriteLine($"Adding prescription for user: {user}, medication: {name}");
        
        try
        {
            var prescriptions = LoadPrescriptions();
            var newId = (prescriptions.Count > 0 
                ? int.Parse(prescriptions.Max(p => p["id"].ToString() ?? "0")) + 1 
                : 1).ToString();

            var newPrescription = new Dictionary<string, object>
            {
                { "user", user },
                { "id", newId },
                { "name", name },
                { "dosage", dosage },
                { "instructions", instructions }
            };

            prescriptions.Add(newPrescription);
            SavePrescriptions(prescriptions);

            return new { success = true, message = "Prescription added successfully", prescription = newPrescription };
        }
        catch (Exception ex)
        {
            return new { success = false, message = $"Error adding prescription: {ex.Message}" };
        }
    }

    /// <summary>
    /// Update an existing prescription.
    /// </summary>
    [Description("Update an existing prescription")]
    public static object UpdatePrescription(
        [Description("The prescription ID to update")]
        string id,
        [Description("The medication name")]
        string name,
        [Description("The dosage (e.g., '300MG')")]
        string dosage,
        [Description("Instructions for taking the medication")]
        string instructions)
    {
        Console.WriteLine($"Updating prescription with ID: {id}");
        
        try
        {
            var prescriptions = LoadPrescriptions();
            var prescription = prescriptions.FirstOrDefault(p => p["id"].ToString() == id);

            if (prescription == null)
            {
                return new { success = false, message = $"Prescription with ID {id} not found" };
            }

            prescription["name"] = name;
            prescription["dosage"] = dosage;
            prescription["instructions"] = instructions;

            SavePrescriptions(prescriptions);

            return new { success = true, message = "Prescription updated successfully", prescription = prescription };
        }
        catch (Exception ex)
        {
            return new { success = false, message = $"Error updating prescription: {ex.Message}" };
        }
    }

    /// <summary>
    /// Delete a prescription.
    /// </summary>
    [Description("Delete a prescription")]
    public static object DeletePrescription(
        [Description("The prescription ID to delete")]
        string id)
    {
        Console.WriteLine($"Deleting prescription with ID: {id}");
        
        try
        {
            var prescriptions = LoadPrescriptions();
            var prescription = prescriptions.FirstOrDefault(p => p["id"].ToString() == id);

            if (prescription == null)
            {
                return new { success = false, message = $"Prescription with ID {id} not found" };
            }

            prescriptions.Remove(prescription);
            SavePrescriptions(prescriptions);

            return new { success = true, message = "Prescription deleted successfully" };
        }
        catch (Exception ex)
        {
            return new { success = false, message = $"Error deleting prescription: {ex.Message}" };
        }
    }

    // Helper methods
    private static List<Dictionary<string, object>> LoadPrescriptions()
    {
        if (!File.Exists(PrescriptionFilePath))
        {
            return new List<Dictionary<string, object>>();
        }

        var json = File.ReadAllText(PrescriptionFilePath);
        if (string.IsNullOrWhiteSpace(json))
        {
            return new List<Dictionary<string, object>>();
        }

        return JsonSerializer.Deserialize<List<Dictionary<string, object>>>(json) ?? new List<Dictionary<string, object>>();
    }

    private static void SavePrescriptions(List<Dictionary<string, object>> prescriptions)
    {
        var options = new JsonSerializerOptions { WriteIndented = true };
        var json = JsonSerializer.Serialize(prescriptions, options);
        File.WriteAllText(PrescriptionFilePath, json);
    }
}
