using ProcAI.Core.Models;

namespace ProcAI.Core.Detection;

/// <summary>Welford running statistics for a single metric (O(1) memory).</summary>
public sealed class RunningStat
{
    public long Count { get; set; }
    public double Mean { get; set; }
    public double M2 { get; set; }
    public double MinValue { get; set; } = double.PositiveInfinity;
    public double MaxValue { get; set; } = double.NegativeInfinity;

    public void Update(double x)
    {
        Count++;
        double delta = x - Mean;
        Mean += delta / Count;
        M2 += delta * (x - Mean);
        if (x < MinValue) MinValue = x;
        if (x > MaxValue) MaxValue = x;
    }

    public double Variance => Count > 1 ? M2 / (Count - 1) : 0.0;
    public double Std => Math.Sqrt(Variance);

    /// <summary>
    /// Z-score of x, robust and bounded. A near-constant metric (std ~ 0) would
    /// otherwise make any change look infinitely anomalous, so the std is floored
    /// to a fraction of the mean (or 1.0) and the result is clamped to +/-cap.
    /// </summary>
    public double ZScore(double x, double relFloor = 0.05, double cap = 12.0)
    {
        if (Count < 2) return 0.0;
        double std = Math.Max(Math.Max(Std, Math.Abs(Mean) * relFloor), 1.0);
        double z = (x - Mean) / std;
        return Math.Clamp(z, -cap, cap);
    }
}

/// <summary>Persistence abstraction for baselines (implemented by the SQLite layer).</summary>
public interface IBaselineStore
{
    RunningStat? Get(string identityKey, string metric);
    void Upsert(string identityKey, string metric, RunningStat stat);
    int IdentityCount();
}

/// <summary>In-memory store, used by tests and as a fallback before the DB exists.</summary>
public sealed class InMemoryBaselineStore : IBaselineStore
{
    private readonly Dictionary<string, RunningStat> _data = new();
    private static string Key(string id, string m) => $"{id}\u0001{m}";

    public RunningStat? Get(string identityKey, string metric) =>
        _data.TryGetValue(Key(identityKey, metric), out var s)
            ? new RunningStat { Count = s.Count, Mean = s.Mean, M2 = s.M2, MinValue = s.MinValue, MaxValue = s.MaxValue }
            : null;

    public void Upsert(string identityKey, string metric, RunningStat stat) =>
        _data[Key(identityKey, metric)] = new RunningStat
        { Count = stat.Count, Mean = stat.Mean, M2 = stat.M2, MinValue = stat.MinValue, MaxValue = stat.MaxValue };

    public int IdentityCount() =>
        _data.Keys.Select(k => k.Split('\u0001')[0]).Distinct().Count();
}

/// <summary>
/// Learns normal per-executable behaviour and computes Z-score deviations.
/// Maintains running statistics per (executable identity, metric).
/// </summary>
public sealed class BaselineManager
{
    public static readonly string[] BaselineMetrics =
    {
        "cpu_percent", "memory_percent", "memory_mb", "num_threads", "num_connections",
    };

    private readonly IBaselineStore _store;
    private readonly Dictionary<string, Dictionary<string, RunningStat>> _cache = new();

    public int MinSamples { get; set; }

    public BaselineManager(IBaselineStore store, int minSamples = 8)
    {
        _store = store;
        MinSamples = minSamples;
    }

    private Dictionary<string, RunningStat> LoadStats(string identity)
    {
        if (_cache.TryGetValue(identity, out var cached)) return cached;
        var stats = new Dictionary<string, RunningStat>();
        foreach (var metric in BaselineMetrics)
            stats[metric] = _store.Get(identity, metric) ?? new RunningStat();
        _cache[identity] = stats;
        return stats;
    }

    private void Persist(string identity, Dictionary<string, RunningStat> stats)
    {
        foreach (var (metric, stat) in stats)
            _store.Upsert(identity, metric, stat);
    }

    /// <summary>Fold one snapshot into the baseline for its executable.</summary>
    public void Update(ProcessSnapshot snap, bool persist = true)
    {
        var identity = snap.IdentityKey();
        if (string.IsNullOrEmpty(identity)) return;
        var feats = FeatureExtractor.Extract(snap);
        var stats = LoadStats(identity);
        foreach (var metric in BaselineMetrics)
            stats[metric].Update(feats.TryGetValue(metric, out var v) ? v : 0.0);
        if (persist) Persist(identity, stats);
    }

    public void UpdateMany(IEnumerable<ProcessSnapshot> snaps)
    {
        var touched = new HashSet<string>();
        foreach (var s in snaps)
        {
            Update(s, persist: false);
            var id = s.IdentityKey();
            if (!string.IsNullOrEmpty(id)) touched.Add(id);
        }
        foreach (var id in touched)
            Persist(id, _cache[id]);
    }

    /// <summary>Compute the Z-score deviation of a snapshot from its baseline.</summary>
    public BaselineDeviation Deviation(ProcessSnapshot snap)
    {
        var identity = snap.IdentityKey();
        var stats = LoadStats(identity);
        long samples = BaselineMetrics.Min(m => stats[m].Count);
        if (samples < MinSamples)
            return BaselineDeviation.NotReady((int)samples);

        var feats = FeatureExtractor.Extract(snap);
        var z = new Dictionary<string, double>();
        foreach (var metric in BaselineMetrics)
            z[metric] = Math.Round(stats[metric].ZScore(feats.TryGetValue(metric, out var v) ? v : 0.0), 3);

        var deviating = z.Where(kv => Math.Abs(kv.Value) >= 3.0).Select(kv => kv.Key).ToList();
        double maxAbs = z.Values.Select(Math.Abs).DefaultIfEmpty(0.0).Max();

        return new BaselineDeviation
        {
            Available = true,
            Samples = (int)samples,
            ZScores = z,
            MaxAbsZ = Math.Round(maxAbs, 3),
            DeviatingMetrics = deviating,
        };
    }

    public int IdentityMaturity(string identity)
    {
        var stats = LoadStats(identity);
        return (int)BaselineMetrics.Min(m => stats[m].Count);
    }

    public void ResetCache() => _cache.Clear();
}
