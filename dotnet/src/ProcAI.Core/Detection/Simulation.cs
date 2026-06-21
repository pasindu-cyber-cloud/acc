using ProcAI.Core.Models;

namespace ProcAI.Core.Detection;

/// <summary>
/// Simulation mode: synthetic, harmless abnormal process behaviour for exercising
/// the full detection pipeline WITHOUT running real malware. Every snapshot is
/// fabricated data only — no process is created, launched, modified or terminated.
/// PIDs are negative sentinels so they can never collide with real OS processes.
/// </summary>
public static class Simulation
{
    private const int SimPidBase = -1000;

    /// <summary>Known abnormal scenarios and the indicator each targets.</summary>
    public static readonly IReadOnlyDictionary<string, string> Scenarios = new Dictionary<string, string>
    {
        ["cpu_spike"] = "Sustained very high CPU with low memory (crypto-miner-like profile).",
        ["memory_balloon"] = "Rapidly growing memory footprint (leak / staging-like profile).",
        ["thread_storm"] = "Abnormally high thread count.",
        ["beacon_network"] = "Many short-lived outbound connections (beacon-like profile).",
        ["temp_unsigned"] = "Unsigned executable running from a Temp/Downloads directory.",
        ["orphan_lineage"] = "Unusual parent-child lineage (e.g. office app spawning a shell).",
        ["short_lived_burst"] = "Very new process consuming heavy resources immediately.",
    };

    private static List<ProcessSnapshot> BenignProcesses()
    {
        double now = ProcessSnapshot.UnixNow();
        return new List<ProcessSnapshot>
        {
            new()
            {
                Pid = SimPidBase - 1, Name = "sim_explorer.exe", ExePath = @"C:\Windows\explorer.exe",
                Username = "DEMO\\user", CpuPercent = 1.2, MemoryRss = 120L * 1024 * 1024,
                MemoryPercent = 1.5, ThreadCount = 42, ConnectionCount = 2, RemoteEndpointCount = 1,
                Ppid = SimPidBase, ParentName = "sim_winlogon.exe", CreateTime = now - 36000,
                IsSigned = true, Signer = "Microsoft Windows",
            },
            new()
            {
                Pid = SimPidBase - 2, Name = "sim_browser.exe",
                ExePath = @"C:\Program Files\Browser\browser.exe", Username = "DEMO\\user",
                CpuPercent = 8.0, MemoryRss = 512L * 1024 * 1024, MemoryPercent = 6.0,
                ThreadCount = 70, ConnectionCount = 14, RemoteEndpointCount = 9,
                Ppid = SimPidBase - 1, ParentName = "sim_explorer.exe", CreateTime = now - 7200,
                IsSigned = true, Signer = "Example Browser Inc",
            },
        };
    }

    private static ProcessSnapshot AbnormalProcess(string scenario, int idx, Random rng)
    {
        double now = ProcessSnapshot.UnixNow();
        var b = new ProcessSnapshot
        {
            Pid = SimPidBase - 100 - idx, Name = $"sim_{scenario}.exe", Username = "DEMO\\user",
            ExePath = $@"C:\Program Files\Demo\sim_{scenario}.exe",
            Ppid = SimPidBase - 1, ParentName = "sim_explorer.exe", CreateTime = now - 1800,
            IsSigned = true, Signer = "Demo Signed Vendor",
            CpuPercent = 2.0, MemoryRss = 80L * 1024 * 1024, MemoryPercent = 1.0,
            ThreadCount = 12, ConnectionCount = 1, RemoteEndpointCount = 1,
        };

        switch (scenario)
        {
            case "cpu_spike":
                b.CpuPercent = rng.NextDouble() * 11 + 88; b.ThreadCount = rng.Next(8, 16); break;
            case "memory_balloon":
                b.MemoryRss = (long)rng.Next(2200, 4000) * 1024 * 1024; b.MemoryPercent = rng.NextDouble() * 35 + 35; break;
            case "thread_storm":
                b.ThreadCount = rng.Next(400, 1200); break;
            case "beacon_network":
                b.ConnectionCount = rng.Next(60, 200); b.RemoteEndpointCount = rng.Next(40, 150); break;
            case "temp_unsigned":
                b.ExePath = @"C:\Users\user\AppData\Local\Temp\sim_temp_unsigned.exe";
                b.IsSigned = false; b.Signer = string.Empty; b.InSuspiciousDir = true; break;
            case "orphan_lineage":
                // Real, matchable names so the lineage rule fires; negative PID keeps it synthetic.
                b.Name = "cmd.exe"; b.ExePath = @"C:\Windows\System32\cmd.exe";
                b.ParentName = "winword.exe"; b.Ppid = SimPidBase - 50; break;
            case "short_lived_burst":
                b.CreateTime = now - 3; b.CpuPercent = rng.NextDouble() * 25 + 70;
                b.MemoryRss = (long)rng.Next(900, 1600) * 1024 * 1024; break;
        }
        return b;
    }

    /// <summary>Generate a batch of synthetic snapshots.</summary>
    public static List<ProcessSnapshot> Generate(IEnumerable<string>? scenarios = null, bool includeBenign = true)
    {
        var rng = new Random();
        var chosen = (scenarios ?? Scenarios.Keys).ToList();
        var outList = new List<ProcessSnapshot>();
        if (includeBenign) outList.AddRange(BenignProcesses());
        int i = 0;
        foreach (var name in chosen)
        {
            if (Scenarios.ContainsKey(name)) outList.Add(AbnormalProcess(name, i, rng));
            i++;
        }
        return outList;
    }

    /// <summary>
    /// Generate a synthetic labelled dataset for ML bootstrap/testing.
    /// Returns (featureVector, label) where label 0 = normal, 1 = suspicious.
    /// </summary>
    public static List<(float[] Features, bool Label)> GenerateTrainingData(int nNormal = 400, int nSuspicious = 200)
    {
        var rng = new Random(1337);
        double now = ProcessSnapshot.UnixNow();
        var rows = new List<(float[], bool)>();

        for (int i = 0; i < nNormal; i++)
        {
            var snap = new ProcessSnapshot
            {
                Pid = 1, Name = "normal.exe", ExePath = @"C:\Program Files\App\normal.exe",
                CpuPercent = rng.NextDouble() * 12, MemoryPercent = rng.NextDouble() * 8,
                MemoryRss = (long)(rng.NextDouble() * 390 + 10) * 1024 * 1024,
                ThreadCount = rng.Next(2, 60), ConnectionCount = rng.Next(0, 8),
                RemoteEndpointCount = rng.Next(0, 5),
                CreateTime = now - (rng.NextDouble() * 199700 + 300),
                IsSigned = true, InSuspiciousDir = false,
            };
            rows.Add((FeatureExtractor.ToVector(snap), false));
        }

        for (int i = 0; i < nSuspicious; i++)
        {
            var snap = new ProcessSnapshot
            {
                Pid = 2, Name = "susp.exe", ExePath = @"C:\Users\u\AppData\Local\Temp\susp.exe",
                CpuPercent = rng.NextDouble() * 40 + 60, MemoryPercent = rng.NextDouble() * 60 + 20,
                MemoryRss = (long)(rng.NextDouble() * 3200 + 800) * 1024 * 1024,
                ThreadCount = rng.Next(150, 1000), ConnectionCount = rng.Next(30, 200),
                RemoteEndpointCount = rng.Next(20, 150),
                CreateTime = now - (rng.NextDouble() * 119 + 1),
                IsSigned = rng.NextDouble() < 0.2, InSuspiciousDir = rng.NextDouble() < 0.8,
            };
            rows.Add((FeatureExtractor.ToVector(snap), true));
        }

        return rows.OrderBy(_ => rng.Next()).ToList();
    }
}
