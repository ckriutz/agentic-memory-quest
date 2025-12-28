using System.ComponentModel;

namespace AgenticMemoryQuest.Server.Tools;
public static class WeatherTools
{
    /// <summary>
    /// Get the current weather for a location.
    /// </summary>
    [Description("Get the current weather for a location")]
    public static object GetWeather(
        [Description("The location to get weather for (e.g., 'San Francisco' or 'New York')")]
        string location)
    {
        Console.WriteLine($"Fetching weather for location: {location}");
        // Mock weather data - in a real app, you'd call a weather API
        var random = new Random(location.GetHashCode());
        var weatherConditions = new[] { "Sunny", "Partly Cloudy", "Cloudy", "Rainy", "Clear" };
        
        return new
        {
            location = location,
            temperatureC = random.Next(5, 35),
            humidityPct = random.Next(30, 90),
            windKph = random.Next(5, 40),
            conditions = weatherConditions[random.Next(weatherConditions.Length)],
            source = "Mock Weather Service"
        };
    }
}
