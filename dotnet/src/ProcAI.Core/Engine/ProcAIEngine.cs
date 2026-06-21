using ProcAI.Core.Configuration;
using ProcAI.Core.Data;
using ProcAI.Core.Detection;
using ProcAI.Core.Ml;
using ProcAI.Core.Models;
using ProcAI.Core.Reputation;
using ProcAI.Core.Telemetry;
using ProcAI.Core.Utils;

namespace ProcAI.Core.Engine;

/// <summary>Protection-health snapshot for the GUI's health page.</summary>
public sealed record HealthStatus(
    bool MlAvailable, bool ModelLoaded, string ModelName, int BaselineIdentities,
    bool LearningActive, double LearningRemainingMinutes, string Sensitivity,
    bool PrivacyFirst, bool AiAssistantEnabled, bool AuditOk);

/// <summary>
/// The single orchestration facade tying telemetry -> detection -> persistence
/// together. Both the GUI and the background service talk to this object.
/// </summary>
public sealed class ProcAIEngine : IDisposable
{
    public Settings Settings { get; private set; }
    public Database Db { get; }
    public ITelemetryCollector Collector { get; }
    public BaselineManager Baseline { get; }
    public LearningMode Learning { get; }
    public AuditLog Audit { get; }

    private readonly RuleEngine _rules = new();
    private readonly ReputationService _reputation = new();
    private MlClassifier? _classifier;
    private HybridEngine _hybrid;

    private readonly Dictionary<string, double> _lastAlertAt = new();
    private const double AlertCooldownSeconds = 120.0;
    private readonly object _alertLock = new();

    public event Action<Alert, DetectionResult>? AlertRaised;

    public ProcAIEngine(Settings? settings = null, Database? db = null)
    {
        AppPaths.Default.Ensure();
        Settings = settings ?? Settings.Load();
        Db = db ?? new Database();
        Audit = new AuditLog();
        Collector = new TelemetryCollector();
        Baseline = new BaselineManager(Db, Settings.BaselineMinSamples);
        Learning = new LearningMode(Db);

        LoadClassifier();
        _hybrid = new HybridEngine(_rules, Baseline, _classifier);

        if (Settings.LearningMode && !Learning.HasStarted())
            Learning.Start(Settings.LearningDurationMinutes);
    }

    private void LoadClassifier()
    {
        _classifier = null;
        if (Settings.EnableMl)
        {
            var clf = new MlClassifier(Settings.PreferredModel);
            if (clf.Load()) _classifier = clf;
        }
    }

    public void UpdateSettings(Settings updated)
    {
        var old = Settings;
        Settings = updated;
        updated.Save();
        Baseline.MinSamples = updated.BaselineMinSamples;
        if (updated.EnableMl && (_classifier is null || _classifier.Name != updated.PreferredModel))
            LoadClassifier();
        else if (!updated.EnableMl)
            _classifier = null;
        _hybrid = new HybridEngine(_rules, Baseline, _classifier);
        Audit.Record("settings.update", new
        {
            sensitivity = updated.Sensitivity.ToString(),
            enable_ml = updated.EnableMl,
            ai_assistant_enabled = updated.AiAssistantEnabled,
            from_sensitivity = old.Sensitivity.ToString(),
        });
    }

    private HybridConfig BuildConfig() => HybridConfig.FromSettings(
        Settings,
        learningMode: Settings.LearningMode && Learning.IsActive(),
        extraAllow: Db.GetReputation("allow"),
        extraBlock: Db.GetReputation("block"));

    /// <summary>Run the full pipeline once over the given (or live) snapshots.</summary>
    public IReadOnlyList<DetectionResult> ScanOnce(
        IReadOnlyList<ProcessSnapshot>? snapshots = null, bool enrichReputation = true, bool persist = true)
    {
        snapshots ??= Collector.Collect();
        var config = BuildConfig();
        var results = new List<DetectionResult>(snapshots.Count);
        var historyRows = new List<(ProcessSnapshot, double, int)>(snapshots.Count);

        foreach (var snap in snapshots)
        {
            if (enrichReputation && !string.IsNullOrEmpty(snap.ExePath) && snap.Pid > 0)
            {
                try { _reputation.Enrich(snap); } catch { /* never let enrichment crash a scan */ }
            }
            var result = _hybrid.Evaluate(snap, config);
            results.Add(result);
            historyRows.Add((snap, result.RiskScore, (int)result.Severity));
            if (result.ShouldAlert) RaiseAlert(result);
        }

        // Fold this scan's observations into the per-executable baselines (persisted once per identity).
        Baseline.UpdateMany(snapshots);

        if (persist)
        {
            try { Db.InsertSnapshots(historyRows); } catch { /* non-fatal */ }
        }
        return results;
    }

    private void RaiseAlert(DetectionResult result)
    {
        string identity = result.Snapshot.IdentityKey();
        double now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
        lock (_alertLock)
        {
            if (_lastAlertAt.TryGetValue(identity, out var last) && now - last < AlertCooldownSeconds)
                return; // de-duplicate alert storms for the same executable
            _lastAlertAt[identity] = now;
        }

        var alert = Alert.FromDetection(result);
        try { alert.Id = Db.InsertAlert(alert); } catch { /* non-fatal */ }
        Audit.Record("alert.raise", new
        {
            pid = alert.Pid, name = alert.ProcessName, severity = alert.Severity.Label(), risk = alert.RiskScore,
        }, actor: "service");
        AlertRaised?.Invoke(alert, result);
    }

    public DetectionResult? Inspect(int pid)
    {
        var snap = Collector.CollectOne(pid);
        if (snap is null) return null;
        try { _reputation.Enrich(snap); } catch { /* ignore */ }
        return _hybrid.Evaluate(snap, BuildConfig());
    }

    public Dictionary<string, int> RunRetention() =>
        Db.PruneRetention(Settings.ProcessHistoryRetentionDays, Settings.LogRetentionDays);

    public HealthStatus Health() => new(
        MlAvailable: true,
        ModelLoaded: _classifier is { IsLoaded: true },
        ModelName: _classifier?.Name ?? string.Empty,
        BaselineIdentities: Db.IdentityCount(),
        LearningActive: Learning.IsActive(),
        LearningRemainingMinutes: Math.Round(Learning.RemainingSeconds() / 60.0, 1),
        Sensitivity: Settings.Sensitivity.ToString(),
        PrivacyFirst: Settings.PrivacyFirstMode,
        AiAssistantEnabled: Settings.AiAssistantEnabled,
        AuditOk: Audit.Verify().Ok);

    public void Dispose()
    {
        _classifier?.Dispose();
        Db.Dispose();
    }
}
