using ProcAI.Core.Configuration;
using ProcAI.Core.Engine;

namespace ProcAI.App.Services;

/// <summary>
/// Process-wide holder for the shared engine, monitor and settings. A lightweight
/// service locator so pages (created by the NavigationView) can reach the backend
/// without constructor injection plumbing.
/// </summary>
public sealed class AppServices
{
    public static AppServices Instance { get; } = new();

    public Settings Settings { get; private set; } = new();
    public ProcAIEngine Engine { get; private set; } = null!;
    public ProcessMonitor Monitor { get; private set; } = null!;

    private bool _initialised;

    private AppServices() { }

    public void Initialize()
    {
        if (_initialised) return;
        Settings = Settings.Load();
        Engine = new ProcAIEngine(Settings);
        Monitor = new ProcessMonitor(Engine);
        _initialised = true;
    }

    public void ApplySettings(Settings updated)
    {
        Settings = updated;
        Engine.UpdateSettings(updated);
    }

    public void Shutdown()
    {
        try { Monitor?.Stop(); } catch { /* ignore */ }
        try { Engine?.Dispose(); } catch { /* ignore */ }
    }
}
