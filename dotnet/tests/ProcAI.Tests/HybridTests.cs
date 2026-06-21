using FluentAssertions;
using ProcAI.Core.Configuration;
using ProcAI.Core.Detection;
using ProcAI.Core.Models;
using Xunit;

namespace ProcAI.Tests;

public class HybridTests
{
    private static HybridEngine Engine() =>
        new(new RuleEngine(), new BaselineManager(new InMemoryBaselineStore(), minSamples: 5), classifier: null);

    private static HybridConfig Cfg(SensitivityProfile profile = SensitivityProfile.Balanced,
        IEnumerable<string>? allow = null, IEnumerable<string>? block = null, bool suppress = true)
    {
        var s = new Settings { EnableMl = false, Sensitivity = profile, SuppressTrusted = suppress };
        if (allow != null) s.Allowlist.AddRange(allow);
        if (block != null) s.Blocklist.AddRange(block);
        return HybridConfig.FromSettings(s);
    }

    [Fact]
    public void Benign_DoesNotAlert()
    {
        var snap = new ProcessSnapshot
        {
            Pid = 1, Name = "explorer.exe", ExePath = @"C:\Windows\explorer.exe",
            CpuPercent = 1, MemoryPercent = 1, ThreadCount = 30, IsSigned = true,
        };
        var r = Engine().Evaluate(snap, Cfg());
        r.RiskScore.Should().Be(0.0);
        r.ShouldAlert.Should().BeFalse();
        r.Severity.Should().Be(Severity.Info);
    }

    [Fact]
    public void Blocklist_Forces_CriticalAlert()
    {
        var snap = new ProcessSnapshot { Pid = 2, Name = "evil.exe", ExePath = @"C:\evil.exe" };
        var r = Engine().Evaluate(snap, Cfg(block: new[] { "evil.exe" }));
        r.RiskScore.Should().Be(100.0);
        r.Severity.Should().Be(Severity.Critical);
        r.ShouldAlert.Should().BeTrue();
    }

    [Fact]
    public void Allowlist_Suppresses_Alert()
    {
        var snap = new ProcessSnapshot
        {
            Pid = 3, Name = "x.exe", ExePath = @"C:\Users\u\AppData\Local\Temp\x.exe",
            IsSigned = false, InSuspiciousDir = true, CpuPercent = 95,
        };
        var r = Engine().Evaluate(snap, Cfg(SensitivityProfile.Strict, allow: new[] { "x.exe" }));
        r.Suppressed.Should().BeTrue();
        r.ShouldAlert.Should().BeFalse();
    }

    [Fact]
    public void Strict_AtLeastAsSensitive_AsLow()
    {
        var snap = new ProcessSnapshot
        {
            Pid = 4, Name = "x.exe", ExePath = @"C:\Users\u\AppData\Local\Temp\x.exe",
            IsSigned = false, InSuspiciousDir = true,
        };
        var strict = Engine().Evaluate(snap, Cfg(SensitivityProfile.Strict));
        var low = Engine().Evaluate(snap, Cfg(SensitivityProfile.Low));
        strict.RiskScore.Should().Be(low.RiskScore);
        (strict.ShouldAlert ? 1 : 0).Should().BeGreaterThanOrEqualTo(low.ShouldAlert ? 1 : 0);
    }

    [Fact]
    public void Components_AreRecorded()
    {
        var r = Engine().Evaluate(new ProcessSnapshot { Pid = 5, Name = "x.exe", CpuPercent = 95 }, Cfg());
        r.Components.Should().ContainKey("rule_score");
        r.Components.Should().ContainKey("w_rules");
        r.Confidence.Should().BeInRange(0.0, 1.0);
    }
}
