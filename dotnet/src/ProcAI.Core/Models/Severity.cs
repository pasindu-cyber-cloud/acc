namespace ProcAI.Core.Models;

/// <summary>Ordered severity levels. Higher value == more severe.</summary>
public enum Severity
{
    Info = 0,
    Low = 1,
    Medium = 2,
    High = 3,
    Critical = 4,
}

/// <summary>Helpers for mapping scores/names to <see cref="Severity"/>.</summary>
public static class SeverityExtensions
{
    public static string Label(this Severity severity) => severity switch
    {
        Severity.Info => "Info",
        Severity.Low => "Low",
        Severity.Medium => "Medium",
        Severity.High => "High",
        Severity.Critical => "Critical",
        _ => "Info",
    };

    /// <summary>Map a 0-100 risk score to a severity band.</summary>
    public static Severity FromScore(double score) => score switch
    {
        >= 85 => Severity.Critical,
        >= 65 => Severity.High,
        >= 45 => Severity.Medium,
        >= 25 => Severity.Low,
        _ => Severity.Info,
    };

    public static Severity FromName(string? name) => (name?.Trim().ToLowerInvariant()) switch
    {
        "critical" => Severity.Critical,
        "high" => Severity.High,
        "medium" => Severity.Medium,
        "low" => Severity.Low,
        _ => Severity.Info,
    };
}
