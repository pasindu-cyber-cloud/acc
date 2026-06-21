using System.Text.Json;
using System.Text.Json.Serialization;

namespace ProcAI.Core.Configuration;

/// <summary>
/// User-tunable settings. Serialises to JSON (settings.json) and is mirrored into
/// the database so the GUI and the background service share one source of truth.
/// Privacy-first: AI assistant network access defaults OFF.
/// </summary>
public sealed class Settings
{
    // Monitoring
    public SensitivityProfile Sensitivity { get; set; } = SensitivityProfile.Balanced;
    public double ScanIntervalSeconds { get; set; } = 3.0;
    public bool LearningMode { get; set; } = true;
    public int LearningDurationMinutes { get; set; } = 30;
    public bool StartWithWindows { get; set; }
    public bool StartMinimizedToTray { get; set; } = true;

    // Detection
    public bool EnableMl { get; set; } = true;
    public string PreferredModel { get; set; } = "random_forest"; // or "decision_tree"
    public int BaselineMinSamples { get; set; } = 8;
    public bool SuppressTrusted { get; set; } = true;

    // Notifications
    public bool DesktopNotifications { get; set; } = true;
    public string NotifyMinSeverity { get; set; } = "high";

    // Privacy / AI assistant (OFF by default)
    public bool PrivacyFirstMode { get; set; } = true;
    public bool AiAssistantEnabled { get; set; }
    public string AiBackend { get; set; } = "offline"; // offline | gemini | ollama
    public string AiGeminiApiKey { get; set; } = string.Empty;
    public string AiOllamaHost { get; set; } = "http://localhost:11434";
    public string AiOllamaModel { get; set; } = "llama3";

    // Retention / logging
    public int LogRetentionDays { get; set; } = 30;
    public int ProcessHistoryRetentionDays { get; set; } = 14;
    public bool AuditEnabled { get; set; } = true;

    // Lists
    public List<string> Allowlist { get; set; } = new();
    public List<string> Blocklist { get; set; } = new();

    // Consent / state
    public bool ConsentAccepted { get; set; }
    public string ConsentVersion { get; set; } = "1.0";

    [JsonIgnore]
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.CamelCase) },
    };

    public string ToJson() => JsonSerializer.Serialize(this, JsonOptions);

    public static Settings Load(string? path = null)
    {
        path ??= AppPaths.Default.SettingsPath;
        if (!File.Exists(path)) return new Settings();
        try
        {
            var json = File.ReadAllText(path);
            return JsonSerializer.Deserialize<Settings>(json, JsonOptions) ?? new Settings();
        }
        catch (Exception ex) when (ex is JsonException or IOException)
        {
            // Corrupt settings must never crash the app; fall back to defaults.
            return new Settings();
        }
    }

    public void Save(string? path = null)
    {
        path ??= AppPaths.Default.SettingsPath;
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, ToJson());
    }

    public Settings Clone() =>
        JsonSerializer.Deserialize<Settings>(ToJson(), JsonOptions)!;
}

/// <summary>Directories commonly abused for dropping executables on Windows (advisory).</summary>
public static class SuspiciousLocations
{
    public static readonly string[] Hints =
    {
        @"\appdata\local\temp",
        @"\windows\temp",
        @"\users\public",
        @"\programdata\temp",
        @"\downloads",
        @"\$recycle.bin",
        @"\appdata\roaming\temp",
    };
}
