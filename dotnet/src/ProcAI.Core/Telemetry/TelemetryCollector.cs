using System.Diagnostics;
using System.Management;
using ProcAI.Core.Models;

namespace ProcAI.Core.Telemetry;

/// <summary>
/// Live process telemetry via <see cref="Process"/> (resource usage), WMI
/// (executable path / command line / parent / owner) and IP Helper (per-process
/// network). Robust and read-only: per-process access errors for protected
/// processes are swallowed rather than throwing.
///
/// CPU% is computed from the change in total processor time between scans
/// (normalised by logical CPU count to a 0-100 range), so values are meaningful
/// from the second scan onward.
/// </summary>
public sealed class TelemetryCollector : ITelemetryCollector
{
    private readonly Dictionary<int, (TimeSpan Cpu, DateTime When)> _prevCpu = new();
    private readonly int _cpuCount = Math.Max(1, Environment.ProcessorCount);
    private ulong _totalPhys;
    private bool _primed;

    private ulong TotalPhys
    {
        get
        {
            if (_totalPhys == 0) _totalPhys = NativeMethods.GetMemoryStatus().TotalPhys;
            return _totalPhys == 0 ? 1 : _totalPhys;
        }
    }

    public void Prime()
    {
        var now = DateTime.UtcNow;
        foreach (var p in Process.GetProcesses())
        {
            try { _prevCpu[p.Id] = (p.TotalProcessorTime, now); }
            catch { /* access denied for protected processes */ }
            finally { p.Dispose(); }
        }
        _primed = true;
    }

    public IReadOnlyList<ProcessSnapshot> Collect()
    {
        if (!_primed) Prime();

        var wmi = QueryWmiProcessInfo();                 // pid -> (name, exe, cmdline, ppid, create)
        var nameByPid = wmi.ToDictionary(kv => kv.Key, kv => kv.Value.Name);
        var net = AggregateNetwork(NativeMethods.GetTcpConnections());

        var now = DateTime.UtcNow;
        var snapshots = new List<ProcessSnapshot>();

        foreach (var proc in Process.GetProcesses())
        {
            try
            {
                int pid = proc.Id;
                wmi.TryGetValue(pid, out var info);
                net.TryGetValue(pid, out var nstat);

                var snap = new ProcessSnapshot
                {
                    Pid = pid,
                    Name = info.Name ?? (proc.ProcessName + ".exe"),
                    ExePath = info.Exe ?? string.Empty,
                    CommandLine = info.CommandLine ?? string.Empty,
                    Ppid = info.Ppid,
                    ParentName = info.Ppid != 0 && nameByPid.TryGetValue(info.Ppid, out var pn) ? pn : string.Empty,
                    ThreadCount = Try(() => proc.Threads.Count, 0),
                    HandleCount = Try(() => proc.HandleCount, 0),
                    MemoryRss = Try(() => proc.WorkingSet64, 0L),
                    CreateTime = info.CreateTime > 0 ? info.CreateTime
                        : Try(() => new DateTimeOffset(proc.StartTime.ToUniversalTime()).ToUnixTimeMilliseconds() / 1000.0, 0.0),
                    CpuPercent = ComputeCpu(pid, Try(() => proc.TotalProcessorTime, TimeSpan.Zero), now),
                    ConnectionCount = nstat.Count,
                    RemoteEndpointCount = nstat.RemoteEndpoints,
                    ListeningPorts = nstat.ListeningPorts,
                };
                snap.MemoryPercent = TotalPhys > 0 ? snap.MemoryRss / (double)TotalPhys * 100.0 : 0.0;
                snapshots.Add(snap);
            }
            catch
            {
                // Skip processes we cannot read at all.
            }
            finally
            {
                proc.Dispose();
            }
        }

        // Forget CPU history for processes that have exited.
        var alive = snapshots.Select(s => s.Pid).ToHashSet();
        foreach (var dead in _prevCpu.Keys.Where(k => !alive.Contains(k)).ToList())
            _prevCpu.Remove(dead);

        return snapshots;
    }

    public ProcessSnapshot? CollectOne(int pid)
    {
        try
        {
            using var proc = Process.GetProcessById(pid);
            var wmi = QueryWmiProcessInfo(pid);
            wmi.TryGetValue(pid, out var info);
            var net = AggregateNetwork(NativeMethods.GetTcpConnections().Where(c => c.Pid == pid).ToList());
            net.TryGetValue(pid, out var nstat);

            var snap = new ProcessSnapshot
            {
                Pid = pid,
                Name = info.Name ?? (proc.ProcessName + ".exe"),
                ExePath = info.Exe ?? string.Empty,
                CommandLine = info.CommandLine ?? string.Empty,
                Ppid = info.Ppid,
                Username = GetProcessOwner(pid),
                ThreadCount = Try(() => proc.Threads.Count, 0),
                HandleCount = Try(() => proc.HandleCount, 0),
                MemoryRss = Try(() => proc.WorkingSet64, 0L),
                CreateTime = info.CreateTime,
                CpuPercent = ComputeCpu(pid, Try(() => proc.TotalProcessorTime, TimeSpan.Zero), DateTime.UtcNow),
                ConnectionCount = nstat.Count,
                RemoteEndpointCount = nstat.RemoteEndpoints,
                ListeningPorts = nstat.ListeningPorts,
            };
            if (info.Ppid != 0)
            {
                try { using var parent = Process.GetProcessById(info.Ppid); snap.ParentName = parent.ProcessName + ".exe"; }
                catch { /* parent may have exited */ }
            }
            snap.MemoryPercent = TotalPhys > 0 ? snap.MemoryRss / (double)TotalPhys * 100.0 : 0.0;
            return snap;
        }
        catch
        {
            return null;
        }
    }

    public SystemOverview GetSystemOverview()
    {
        var (total, load) = NativeMethods.GetMemoryStatus();
        double totalGb = total / (1024.0 * 1024.0 * 1024.0);
        double usedGb = totalGb * (load / 100.0);
        int count = 0;
        try { count = Process.GetProcesses().Length; } catch { /* ignore */ }
        return new SystemOverview(0.0, load, Math.Round(totalGb, 1), Math.Round(usedGb, 1), count);
    }

    // ------------------------------------------------------------------ //

    private double ComputeCpu(int pid, TimeSpan cpuNow, DateTime now)
    {
        double cpu = 0.0;
        if (_prevCpu.TryGetValue(pid, out var prev))
        {
            double elapsed = (now - prev.When).TotalSeconds;
            if (elapsed > 0)
            {
                double deltaCpu = (cpuNow - prev.Cpu).TotalSeconds;
                cpu = deltaCpu / (elapsed * _cpuCount) * 100.0;
            }
        }
        _prevCpu[pid] = (cpuNow, now);
        return Math.Clamp(cpu, 0.0, 100.0);
    }

    private readonly record struct WmiInfo(string? Name, string? Exe, string? CommandLine, int Ppid, double CreateTime);

    private static Dictionary<int, WmiInfo> QueryWmiProcessInfo(int? onlyPid = null)
    {
        var map = new Dictionary<int, WmiInfo>();
        string where = onlyPid is int p ? $" WHERE ProcessId = {p}" : string.Empty;
        string query = "SELECT ProcessId, Name, ExecutablePath, CommandLine, ParentProcessId, CreationDate FROM Win32_Process" + where;
        try
        {
            using var searcher = new ManagementObjectSearcher(query);
            foreach (ManagementObject mo in searcher.Get())
            {
                try
                {
                    int pid = Convert.ToInt32(mo["ProcessId"]);
                    int ppid = mo["ParentProcessId"] != null ? Convert.ToInt32(mo["ParentProcessId"]) : 0;
                    double create = 0;
                    if (mo["CreationDate"] is string cd && cd.Length >= 14)
                    {
                        try
                        {
                            var dt = ManagementDateTimeConverter.ToDateTime(cd).ToUniversalTime();
                            create = new DateTimeOffset(dt).ToUnixTimeMilliseconds() / 1000.0;
                        }
                        catch { /* malformed date */ }
                    }
                    map[pid] = new WmiInfo(
                        mo["Name"] as string,
                        mo["ExecutablePath"] as string,
                        mo["CommandLine"] as string,
                        ppid, create);
                }
                catch { /* skip malformed row */ }
                finally { mo.Dispose(); }
            }
        }
        catch
        {
            // WMI unavailable/insufficient rights: degrade gracefully.
        }
        return map;
    }

    private static string GetProcessOwner(int pid)
    {
        try
        {
            using var searcher = new ManagementObjectSearcher(
                $"SELECT * FROM Win32_Process WHERE ProcessId = {pid}");
            foreach (ManagementObject mo in searcher.Get())
            {
                var outParams = new object[2];
                int ret = Convert.ToInt32(mo.InvokeMethod("GetOwner", outParams));
                mo.Dispose();
                if (ret == 0)
                {
                    string domain = outParams[1] as string ?? string.Empty;
                    string user = outParams[0] as string ?? string.Empty;
                    return string.IsNullOrEmpty(domain) ? user : $"{domain}\\{user}";
                }
            }
        }
        catch { /* access denied */ }
        return string.Empty;
    }

    private readonly record struct NetStat(int Count, int RemoteEndpoints, IReadOnlyList<int> ListeningPorts);

    private static Dictionary<int, NetStat> AggregateNetwork(List<NativeMethods.TcpConnection> conns)
    {
        var byPid = new Dictionary<int, (int count, HashSet<uint> remotes, SortedSet<int> listening)>();
        foreach (var c in conns)
        {
            if (c.Pid <= 0) continue;
            if (!byPid.TryGetValue(c.Pid, out var agg))
            {
                agg = (0, new HashSet<uint>(), new SortedSet<int>());
                byPid[c.Pid] = agg;
            }
            agg.count++;
            if (c.IsListening) agg.listening.Add(c.LocalPort);
            else if (c.RemoteAddr != 0) agg.remotes.Add(c.RemoteAddr);
            byPid[c.Pid] = agg;
        }
        return byPid.ToDictionary(
            kv => kv.Key,
            kv => new NetStat(kv.Value.count, kv.Value.remotes.Count, kv.Value.listening.ToList()));
    }

    private static T Try<T>(Func<T> f, T fallback)
    {
        try { return f(); } catch { return fallback; }
    }
}
