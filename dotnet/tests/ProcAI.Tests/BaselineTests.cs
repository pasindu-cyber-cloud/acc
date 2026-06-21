using FluentAssertions;
using ProcAI.Core.Detection;
using ProcAI.Core.Models;
using Xunit;

namespace ProcAI.Tests;

public class BaselineTests
{
    private static ProcessSnapshot Snap(double cpu, double mem = 5.0, int threads = 20, int conns = 2) => new()
    {
        Pid = 1, Name = "app.exe", ExePath = "C:/app.exe", CpuPercent = cpu, MemoryPercent = mem,
        MemoryRss = 100L * 1024 * 1024, ThreadCount = threads, ConnectionCount = conns,
    };

    [Fact]
    public void RunningStat_Matches_StandardFormulas()
    {
        var rs = new RunningStat();
        double[] xs = { 10, 12, 11, 9, 10, 13, 8, 12, 11, 10, 14, 7 };
        foreach (var x in xs) rs.Update(x);

        double mean = xs.Average();
        double variance = xs.Sum(v => (v - mean) * (v - mean)) / (xs.Length - 1);

        rs.Count.Should().Be(xs.Length);
        rs.Mean.Should().BeApproximately(mean, 1e-9);
        rs.Std.Should().BeApproximately(Math.Sqrt(variance), 1e-9);
        rs.MinValue.Should().Be(xs.Min());
        rs.MaxValue.Should().Be(xs.Max());
    }

    [Fact]
    public void ZScore_IsBounded_AndZeroWhenImmature()
    {
        var rs = new RunningStat();
        rs.ZScore(100).Should().Be(0.0); // count < 2
        rs.Update(10); rs.Update(10);
        Math.Abs(rs.ZScore(10_000)).Should().BeLessThanOrEqualTo(12.0);
    }

    [Fact]
    public void Baseline_Unavailable_Until_MinSamples()
    {
        var bm = new BaselineManager(new InMemoryBaselineStore(), minSamples: 8);
        for (int i = 0; i < 3; i++) bm.Update(Snap(10));
        bm.Deviation(Snap(10)).Available.Should().BeFalse();
    }

    [Fact]
    public void Baseline_Detects_Anomaly()
    {
        var bm = new BaselineManager(new InMemoryBaselineStore(), minSamples: 5);
        for (int i = 0; i < 10; i++) bm.Update(Snap(10 + (i % 3)));
        var normal = bm.Deviation(Snap(11));
        normal.Available.Should().BeTrue();
        normal.MaxAbsZ.Should().BeLessThan(3.0);

        var anomalous = bm.Deviation(Snap(99, mem: 80, threads: 900, conns: 150));
        anomalous.MaxAbsZ.Should().BeGreaterThanOrEqualTo(3.0);
        anomalous.DeviatingMetrics.Should().NotBeEmpty();
    }

    [Fact]
    public void Baseline_Persists_Across_Managers_SharingStore()
    {
        var store = new InMemoryBaselineStore();
        var bm1 = new BaselineManager(store, minSamples: 5);
        for (int i = 0; i < 6; i++) bm1.Update(Snap(10));
        var bm2 = new BaselineManager(store, minSamples: 5);
        bm2.IdentityMaturity("c:/app.exe").Should().BeGreaterThanOrEqualTo(6);
    }
}
