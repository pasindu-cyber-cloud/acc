using ProcAI.Core.Models;

namespace ProcAI.Core.Engine;

/// <summary>
/// Drives periodic scans on a background task. Fully controllable
/// (Start/Stop/Pause/Resume) and exposes the latest results so the GUI can
/// render without re-scanning. This is ordinary, visible, user-controlled work —
/// not a hidden process; it only reads data the OS already exposes.
/// </summary>
public sealed class ProcessMonitor : IDisposable
{
    private readonly ProcAIEngine _engine;
    private CancellationTokenSource? _cts;
    private Task? _loop;
    private volatile bool _paused;
    private readonly object _lock = new();

    private IReadOnlyList<DetectionResult> _lastResults = Array.Empty<DetectionResult>();
    private double _lastScanAt;
    private long _scanCount;
    private double _lastRetention;
    private const double RetentionIntervalSeconds = 3600.0;

    public event Action<IReadOnlyList<DetectionResult>>? Scanned;

    public ProcessMonitor(ProcAIEngine engine) => _engine = engine;

    public bool Running => _loop is { IsCompleted: false } && _cts is { IsCancellationRequested: false };
    public bool Paused => _paused;
    public long ScanCount => Interlocked.Read(ref _scanCount);
    public double LastScanAt => _lastScanAt;

    public IReadOnlyList<DetectionResult> LastResults
    {
        get { lock (_lock) return _lastResults; }
    }

    public void Start()
    {
        if (Running) return;
        _cts = new CancellationTokenSource();
        _paused = false;
        _engine.Collector.Prime(); // warm CPU counters
        _loop = Task.Run(() => LoopAsync(_cts.Token));
        _engine.Audit.Record("monitoring.start",
            new { interval_s = _engine.Settings.ScanIntervalSeconds }, actor: "service");
    }

    public void Stop()
    {
        if (_cts is null) return;
        _cts.Cancel();
        try { _loop?.Wait(TimeSpan.FromSeconds(5)); } catch { /* ignore */ }
        _cts.Dispose();
        _cts = null;
        _loop = null;
        _engine.Audit.Record("monitoring.stop", actor: "service");
    }

    public void Pause() { _paused = true; _engine.Audit.Record("monitoring.pause"); }
    public void Resume() { _paused = false; _engine.Audit.Record("monitoring.resume"); }

    private async Task LoopAsync(CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            double interval = Math.Max(0.5, _engine.Settings.ScanIntervalSeconds);
            if (!_paused)
            {
                try { DoScan(); }
                catch { /* a scan error must never kill the loop */ }
            }
            try { await Task.Delay(TimeSpan.FromSeconds(interval), token); }
            catch (TaskCanceledException) { break; }
        }
    }

    private void DoScan()
    {
        var results = _engine.ScanOnce();
        lock (_lock) _lastResults = results;
        _lastScanAt = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
        Interlocked.Increment(ref _scanCount);
        Scanned?.Invoke(results);

        if (_lastScanAt - _lastRetention > RetentionIntervalSeconds)
        {
            _lastRetention = _lastScanAt;
            try { _engine.RunRetention(); } catch { /* non-fatal */ }
        }
    }

    public void Dispose() => Stop();
}
