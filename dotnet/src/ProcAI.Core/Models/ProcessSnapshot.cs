namespace ProcAI.Core.Models;

/// <summary>
/// A single point-in-time, read-only observation of one process. All resource
/// fields are best-effort; collection on a live OS frequently hits access errors
/// for protected processes, so missing values use sensible defaults rather than
/// throwing.
/// </summary>
public sealed class ProcessSnapshot
{
    public int Pid { get; set; }
    public string Name { get; set; } = string.Empty;
    public double Timestamp { get; set; } = UnixNow();

    // Identity / lineage
    public string Username { get; set; } = string.Empty;
    public string ExePath { get; set; } = string.Empty;
    public string CommandLine { get; set; } = string.Empty;
    public int Ppid { get; set; }
    public string ParentName { get; set; } = string.Empty;
    public double CreateTime { get; set; }

    // Resource telemetry
    public double CpuPercent { get; set; }
    public long MemoryRss { get; set; }          // bytes (working set)
    public double MemoryPercent { get; set; }
    public int ThreadCount { get; set; }
    public int HandleCount { get; set; }
    public long IoReadBytes { get; set; }
    public long IoWriteBytes { get; set; }

    // Network
    public int ConnectionCount { get; set; }
    public int RemoteEndpointCount { get; set; }
    public IReadOnlyList<int> ListeningPorts { get; set; } = Array.Empty<int>();

    // Reputation (filled by the reputation service; advisory only)
    public bool? IsSigned { get; set; }          // null == unknown / not checked
    public string Signer { get; set; } = string.Empty;
    public bool InSuspiciousDir { get; set; }
    public bool IsStartupPersistent { get; set; }
    public string Status { get; set; } = "running";

    public double LifetimeSeconds =>
        CreateTime <= 0 ? 0 : Math.Max(0, Timestamp - CreateTime);

    public double MemoryMb => MemoryRss / (1024.0 * 1024.0);

    /// <summary>Stable key for baseline tracking (per executable, not per PID).</summary>
    public string IdentityKey() =>
        (string.IsNullOrEmpty(ExePath) ? Name : ExePath).ToLowerInvariant();

    public static double UnixNow() =>
        DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
}
