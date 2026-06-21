using ProcAI.Core.Models;

namespace ProcAI.Core.Detection;

/// <summary>
/// Converts a <see cref="ProcessSnapshot"/> into a stable, interpretable numeric
/// feature vector. A single feature definition is shared by the rule engine, the
/// ML model and the simulation generator so training and inference always agree.
/// <see cref="FeatureNames"/> is the canonical order; keep additions append-only
/// so previously trained models stay compatible (or retrain on change).
/// </summary>
public static class FeatureExtractor
{
    public static readonly string[] FeatureNames =
    {
        "cpu_percent",
        "memory_percent",
        "memory_mb",
        "num_threads",
        "num_connections",
        "num_remote_endpoints",
        "lifetime_minutes",
        "is_unsigned",
        "in_suspicious_dir",
        "is_startup_persistent",
        "log_memory_mb",
        "log_threads",
        "conn_per_minute",
        "cmdline_length",
    };

    /// <summary>Return the canonical feature dictionary for one snapshot.</summary>
    public static Dictionary<string, double> Extract(ProcessSnapshot s)
    {
        double lifetimeMin = Math.Max(s.LifetimeSeconds / 60.0, 0.0);
        double memMb = s.MemoryMb;
        double isUnsigned = s.IsSigned == false ? 1.0 : 0.0; // unknown(null) is not a positive signal
        double connPerMin = lifetimeMin > 0.5 ? s.ConnectionCount / lifetimeMin : s.ConnectionCount;

        return new Dictionary<string, double>
        {
            ["cpu_percent"] = s.CpuPercent,
            ["memory_percent"] = s.MemoryPercent,
            ["memory_mb"] = memMb,
            ["num_threads"] = s.ThreadCount,
            ["num_connections"] = s.ConnectionCount,
            ["num_remote_endpoints"] = s.RemoteEndpointCount,
            ["lifetime_minutes"] = lifetimeMin,
            ["is_unsigned"] = isUnsigned,
            ["in_suspicious_dir"] = s.InSuspiciousDir ? 1.0 : 0.0,
            ["is_startup_persistent"] = s.IsStartupPersistent ? 1.0 : 0.0,
            ["log_memory_mb"] = Math.Log(1.0 + Math.Max(memMb, 0.0)),
            ["log_threads"] = Math.Log(1.0 + Math.Max(s.ThreadCount, 0)),
            ["conn_per_minute"] = connPerMin,
            ["cmdline_length"] = (s.CommandLine ?? string.Empty).Length,
        };
    }

    /// <summary>Order a feature dictionary into the canonical float vector for ML.NET.</summary>
    public static float[] ToVector(IReadOnlyDictionary<string, double> features)
    {
        var vec = new float[FeatureNames.Length];
        for (int i = 0; i < FeatureNames.Length; i++)
            vec[i] = features.TryGetValue(FeatureNames[i], out var v) ? (float)v : 0f;
        return vec;
    }

    public static float[] ToVector(ProcessSnapshot s) => ToVector(Extract(s));
}
