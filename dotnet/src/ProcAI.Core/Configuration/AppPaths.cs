namespace ProcAI.Core.Configuration;

/// <summary>
/// Centralises every on-disk location ProcAI uses. All data stays under the
/// per-user LocalApplicationData directory (%LOCALAPPDATA%\ProcAI on Windows).
/// An optional PROCAI_DATA_DIR environment variable overrides the base (useful
/// for tests).
/// </summary>
public sealed class AppPaths
{
    public string DataDir { get; }
    public string DbPath { get; }
    public string LogsDir { get; }
    public string ModelsDir { get; }
    public string ReportsDir { get; }
    public string SettingsPath { get; }
    public string AuditPath { get; }

    public AppPaths(string? baseDir = null)
    {
        baseDir ??= Environment.GetEnvironmentVariable("PROCAI_DATA_DIR");
        if (string.IsNullOrWhiteSpace(baseDir))
        {
            var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            baseDir = Path.Combine(local, "ProcAI");
        }

        DataDir = baseDir;
        DbPath = Path.Combine(baseDir, "procai.db");
        LogsDir = Path.Combine(baseDir, "logs");
        ModelsDir = Path.Combine(baseDir, "models");
        ReportsDir = Path.Combine(baseDir, "reports");
        SettingsPath = Path.Combine(baseDir, "settings.json");
        AuditPath = Path.Combine(LogsDir, "audit.log");
    }

    /// <summary>Create all directories. Safe to call repeatedly.</summary>
    public AppPaths Ensure()
    {
        Directory.CreateDirectory(DataDir);
        Directory.CreateDirectory(LogsDir);
        Directory.CreateDirectory(ModelsDir);
        Directory.CreateDirectory(ReportsDir);
        return this;
    }

    public static AppPaths Default { get; } = new();
}
