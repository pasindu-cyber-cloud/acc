using ProcAI.Core.Models;

namespace ProcAI.Core.Detection;

/// <summary>Result of running the rule engine over one snapshot.</summary>
public sealed class RuleEvaluation
{
    public double Score { get; init; }       // 0-100
    public double RawPoints { get; init; }
    public IReadOnlyList<RuleHit> Hits { get; init; } = Array.Empty<RuleHit>();
}

/// <summary>
/// Transparent rule-based scoring engine. Every rule is a small, named,
/// fully-explainable heuristic returning a <see cref="RuleHit"/> with the points
/// it contributes, a plain-language explanation and the concrete evidence.
/// Raw points are squashed into 0-100 so no single rule saturates the score
/// while corroborating weak signals still accumulate.
/// </summary>
public sealed class RuleEngine
{
    private static readonly HashSet<string> KnownShellParents = new(StringComparer.OrdinalIgnoreCase)
    {
        "cmd.exe", "powershell.exe", "pwsh.exe", "explorer.exe", "bash", "sh",
        "code.exe", "windowsterminal.exe", "conhost.exe", "python.exe", "py.exe",
    };

    private static readonly HashSet<string> OfficeParents = new(StringComparer.OrdinalIgnoreCase)
    {
        "winword.exe", "excel.exe", "powerpnt.exe", "outlook.exe", "msaccess.exe",
    };

    private static readonly HashSet<string> ShellChildren = new(StringComparer.OrdinalIgnoreCase)
    {
        "cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe", "mshta.exe",
    };

    private readonly List<Func<ProcessSnapshot, BaselineDeviation?, RuleHit?>> _rules;

    public RuleEngine()
    {
        _rules = new()
        {
            HighCpu, HighMemory, ThreadStorm, NetworkBeacon, SuspiciousPath,
            Unsigned, Lineage, ShortLivedBurst, StartupPersistence, BaselineDeviationRule,
        };
    }

    public RuleEvaluation Evaluate(ProcessSnapshot snap, BaselineDeviation? deviation = null)
    {
        var hits = new List<RuleHit>();
        foreach (var rule in _rules)
        {
            try
            {
                var hit = rule(snap, deviation);
                if (hit is not null) hits.Add(hit);
            }
            catch
            {
                // A faulty rule must never crash detection.
            }
        }
        double raw = hits.Sum(h => h.Points);
        return new RuleEvaluation { Score = Math.Round(Squash(raw), 2), RawPoints = Math.Round(raw, 2), Hits = hits };
    }

    /// <summary>Map unbounded raw points to 0-100 with diminishing returns.</summary>
    public static double Squash(double rawPoints) =>
        rawPoints <= 0 ? 0.0 : 100.0 * (1.0 - Math.Exp(-rawPoints / 40.0));

    private static Dictionary<string, object> Ev(params (string, object)[] kv)
    {
        var d = new Dictionary<string, object>();
        foreach (var (k, v) in kv) d[k] = v;
        return d;
    }

    // --- Individual rules (mirror the Python engine) -------------------------

    private static RuleHit? HighCpu(ProcessSnapshot s, BaselineDeviation? _)
    {
        if (s.CpuPercent >= 85)
            return new RuleHit("cpu_high", "Sustained very high CPU usage", 22.0, Severity.Medium,
                $"CPU usage is {s.CpuPercent:0}%, which is unusually high and can indicate " +
                "cryptomining, brute-forcing or a runaway/abused process.",
                Ev(("cpu_percent", Math.Round(s.CpuPercent, 1))));
        if (s.CpuPercent >= 60)
            return new RuleHit("cpu_elevated", "Elevated CPU usage", 10.0, Severity.Low,
                $"CPU usage is {s.CpuPercent:0}%.", Ev(("cpu_percent", Math.Round(s.CpuPercent, 1))));
        return null;
    }

    private static RuleHit? HighMemory(ProcessSnapshot s, BaselineDeviation? _)
    {
        if (s.MemoryPercent >= 40 || s.MemoryMb >= 2048)
            return new RuleHit("mem_high", "High memory footprint", 16.0, Severity.Medium,
                $"Process is using {s.MemoryMb:0} MB ({s.MemoryPercent:0}% of RAM), which may " +
                "indicate data staging or a memory-heavy payload.",
                Ev(("memory_mb", Math.Round(s.MemoryMb, 1)), ("memory_percent", Math.Round(s.MemoryPercent, 1))));
        return null;
    }

    private static RuleHit? ThreadStorm(ProcessSnapshot s, BaselineDeviation? _)
    {
        if (s.ThreadCount >= 400)
            return new RuleHit("thread_storm", "Abnormally high thread count", 18.0, Severity.Medium,
                $"Process holds {s.ThreadCount} threads; very high counts can indicate injection, " +
                "parallel scanning or resource abuse.", Ev(("num_threads", s.ThreadCount)));
        if (s.ThreadCount >= 200)
            return new RuleHit("thread_elevated", "Elevated thread count", 8.0, Severity.Low,
                $"Process holds {s.ThreadCount} threads.", Ev(("num_threads", s.ThreadCount)));
        return null;
    }

    private static RuleHit? NetworkBeacon(ProcessSnapshot s, BaselineDeviation? _)
    {
        if (s.ConnectionCount >= 50 || s.RemoteEndpointCount >= 30)
            return new RuleHit("net_many", "Large number of network connections", 20.0, Severity.Medium,
                $"Process has {s.ConnectionCount} connections to {s.RemoteEndpointCount} distinct remote " +
                "endpoints, which can indicate scanning, beaconing or C2-style traffic.",
                Ev(("connections", s.ConnectionCount), ("remote_endpoints", s.RemoteEndpointCount)));
        if (s.RemoteEndpointCount >= 12)
            return new RuleHit("net_elevated", "Several distinct remote endpoints", 9.0, Severity.Low,
                $"Process is talking to {s.RemoteEndpointCount} distinct remote hosts.",
                Ev(("remote_endpoints", s.RemoteEndpointCount)));
        return null;
    }

    private static RuleHit? SuspiciousPath(ProcessSnapshot s, BaselineDeviation? _)
    {
        if (s.InSuspiciousDir)
            return new RuleHit("path_suspicious", "Executable runs from an unusual location", 16.0, Severity.Medium,
                "The executable is located in a directory commonly abused by malware " +
                $"(e.g. Temp/Downloads/Public): {(string.IsNullOrEmpty(s.ExePath) ? "unknown" : s.ExePath)}.",
                Ev(("exe_path", s.ExePath)));
        return null;
    }

    private static RuleHit? Unsigned(ProcessSnapshot s, BaselineDeviation? _)
    {
        if (s.IsSigned == false)
        {
            double pts = s.InSuspiciousDir ? 18.0 : 12.0;
            return new RuleHit("unsigned", "Unsigned executable", pts, Severity.Medium,
                "The executable is not Authenticode-signed. Most legitimate software is signed; " +
                "unsigned binaries warrant closer inspection.",
                Ev(("is_signed", false), ("exe_path", s.ExePath)));
        }
        return null;
    }

    private static RuleHit? Lineage(ProcessSnapshot s, BaselineDeviation? _)
    {
        var parent = s.ParentName ?? string.Empty;
        var child = s.Name ?? string.Empty;
        if (OfficeParents.Contains(parent) && ShellChildren.Contains(child))
            return new RuleHit("lineage_office_shell", "Office application spawned a shell", 26.0, Severity.High,
                $"'{s.ParentName}' launched '{s.Name}'. Document applications spawning command " +
                "interpreters is a well-known malicious-macro pattern.",
                Ev(("parent", s.ParentName), ("child", s.Name)));
        if (ShellChildren.Contains(child) && !string.IsNullOrEmpty(parent) && !KnownShellParents.Contains(parent))
            return new RuleHit("lineage_unusual_shell", "Shell launched by an unusual parent", 12.0, Severity.Low,
                $"'{s.Name}' was started by '{s.ParentName}', an uncommon parent for a command interpreter.",
                Ev(("parent", s.ParentName), ("child", s.Name)));
        return null;
    }

    private static RuleHit? ShortLivedBurst(ProcessSnapshot s, BaselineDeviation? _)
    {
        if (s.LifetimeSeconds > 0 && s.LifetimeSeconds <= 30 && (s.CpuPercent >= 60 || s.MemoryMb >= 800))
            return new RuleHit("young_resource_burst", "Very new process consuming heavy resources", 14.0, Severity.Medium,
                $"Process is only {s.LifetimeSeconds:0}s old but already at {s.CpuPercent:0}% CPU / {s.MemoryMb:0} MB.",
                Ev(("lifetime_s", Math.Round(s.LifetimeSeconds, 1)), ("cpu", Math.Round(s.CpuPercent, 1))));
        return null;
    }

    private static RuleHit? StartupPersistence(ProcessSnapshot s, BaselineDeviation? _)
    {
        if (s.IsStartupPersistent && (s.IsSigned == false || s.InSuspiciousDir))
            return new RuleHit("persist_suspicious", "Auto-start entry for a low-reputation executable", 14.0, Severity.Medium,
                "This executable is configured to start automatically and is also unsigned or located " +
                "in an unusual directory.",
                Ev(("startup", true), ("suspicious_dir", s.InSuspiciousDir)));
        return null;
    }

    private static RuleHit? BaselineDeviationRule(ProcessSnapshot s, BaselineDeviation? d)
    {
        if (d is null || !d.Available || d.DeviatingMetrics.Count == 0) return null;
        double pts = Math.Min(24.0, 6.0 * d.DeviatingMetrics.Count + 1.5 * (d.MaxAbsZ - 3.0));
        pts = Math.Max(pts, 6.0);
        return new RuleHit("baseline_deviation", "Behaviour deviates from this program's baseline",
            Math.Round(pts, 1), Severity.Medium,
            "Compared with its own learned baseline, this process is behaving unusually on " +
            $"{string.Join(", ", d.DeviatingMetrics)} (max Z-score {d.MaxAbsZ:0.0}).",
            Ev(("deviating_metrics", d.DeviatingMetrics), ("max_abs_z", d.MaxAbsZ)));
    }
}
