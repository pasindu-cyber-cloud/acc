using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using ProcAI.Core.Engine;

namespace ProcAI.Service;

/// <summary>
/// Hosted background worker that runs ProcAI monitoring as a transparent,
/// stoppable Windows Service. Alerts are logged; desktop toast notifications can
/// be wired in here. The service never hides and is fully controllable.
/// </summary>
public sealed class MonitorWorker : BackgroundService
{
    private readonly ILogger<MonitorWorker> _log;
    private ProcAIEngine? _engine;
    private ProcessMonitor? _monitor;

    public MonitorWorker(ILogger<MonitorWorker> log) => _log = log;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _engine = new ProcAIEngine();
        _monitor = new ProcessMonitor(_engine);
        _engine.AlertRaised += (alert, _) =>
            _log.LogWarning("ProcAI alert: {Severity} {Name} (PID {Pid}) risk {Risk}",
                alert.Severity, alert.ProcessName, alert.Pid, alert.RiskScore);

        _monitor.Start();
        _log.LogInformation("ProcAI monitoring service started (interval {Interval}s).",
            _engine.Settings.ScanIntervalSeconds);

        try
        {
            await Task.Delay(Timeout.Infinite, stoppingToken);
        }
        catch (TaskCanceledException)
        {
            // Normal shutdown.
        }
        finally
        {
            _monitor.Stop();
            _engine.Dispose();
            _log.LogInformation("ProcAI monitoring service stopped.");
        }
    }
}
