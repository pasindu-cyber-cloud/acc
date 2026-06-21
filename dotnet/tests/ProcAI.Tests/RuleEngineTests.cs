using FluentAssertions;
using ProcAI.Core.Detection;
using ProcAI.Core.Models;
using Xunit;

namespace ProcAI.Tests;

public class RuleEngineTests
{
    private readonly RuleEngine _engine = new();

    [Fact]
    public void BenignProcess_ScoresZero()
    {
        var snap = new ProcessSnapshot
        {
            Pid = 1, Name = "explorer.exe", ExePath = @"C:\Windows\explorer.exe",
            CpuPercent = 1.0, MemoryPercent = 1.0, ThreadCount = 30, ConnectionCount = 2, IsSigned = true,
        };
        var ev = _engine.Evaluate(snap);
        ev.Score.Should().Be(0.0);
        ev.Hits.Should().BeEmpty();
    }

    [Fact]
    public void HighCpu_Fires()
    {
        var ev = _engine.Evaluate(new ProcessSnapshot { Pid = 1, Name = "x.exe", CpuPercent = 95.0 });
        ev.Hits.Select(h => h.RuleId).Should().Contain("cpu_high");
        ev.Score.Should().BeGreaterThan(0);
    }

    [Fact]
    public void Unsigned_In_Temp_Stacks()
    {
        var snap = new ProcessSnapshot
        {
            Pid = 1, Name = "x.exe", ExePath = @"C:\Users\u\AppData\Local\Temp\x.exe",
            IsSigned = false, InSuspiciousDir = true,
        };
        var ev = _engine.Evaluate(snap);
        var ids = ev.Hits.Select(h => h.RuleId).ToHashSet();
        ids.Should().Contain("path_suspicious");
        ids.Should().Contain("unsigned");
        ev.Score.Should().BeGreaterThan(40);
    }

    [Fact]
    public void Office_Spawns_Shell_IsHigh()
    {
        var snap = new ProcessSnapshot { Pid = 1, Name = "cmd.exe", ParentName = "winword.exe" };
        var ev = _engine.Evaluate(snap);
        var hit = ev.Hits.Single(h => h.RuleId == "lineage_office_shell");
        hit.Severity.Should().Be(Severity.High);
    }

    [Fact]
    public void Score_IsBounded()
    {
        var snap = new ProcessSnapshot
        {
            Pid = 1, Name = "cmd.exe", ParentName = "winword.exe", CpuPercent = 99, MemoryPercent = 90,
            MemoryRss = 4096L * 1024 * 1024, ThreadCount = 1000, ConnectionCount = 200,
            RemoteEndpointCount = 150, IsSigned = false, InSuspiciousDir = true, IsStartupPersistent = true,
        };
        var ev = _engine.Evaluate(snap);
        ev.Score.Should().BeInRange(0, 100);
    }

    [Fact]
    public void BaselineDeviation_Rule_Fires()
    {
        var snap = new ProcessSnapshot { Pid = 1, Name = "x.exe", CreateTime = ProcessSnapshot.UnixNow() - 100 };
        var dev = new BaselineDeviation
        {
            Available = true, Samples = 20, MaxAbsZ = 8.0,
            DeviatingMetrics = new[] { "cpu_percent", "num_threads" },
            ZScores = new Dictionary<string, double> { ["cpu_percent"] = 8.0, ["num_threads"] = 5.0 },
        };
        var ev = _engine.Evaluate(snap, dev);
        ev.Hits.Should().Contain(h => h.RuleId == "baseline_deviation");
    }
}
