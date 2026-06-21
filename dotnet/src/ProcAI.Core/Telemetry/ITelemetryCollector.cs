using ProcAI.Core.Models;

namespace ProcAI.Core.Telemetry;

/// <summary>Collects read-only process telemetry from the running OS.</summary>
public interface ITelemetryCollector
{
    /// <summary>Initialise CPU counters so the next scan returns real CPU values.</summary>
    void Prime();

    /// <summary>Return a snapshot of all visible processes.</summary>
    IReadOnlyList<ProcessSnapshot> Collect();

    /// <summary>Collect a single process by PID (for deep scan / intelligence view).</summary>
    ProcessSnapshot? CollectOne(int pid);
}

/// <summary>Host-level resource usage for the dashboard.</summary>
public readonly record struct SystemOverview(
    double CpuPercent,
    double MemoryPercent,
    double MemoryTotalGb,
    double MemoryUsedGb,
    int ProcessCount);
