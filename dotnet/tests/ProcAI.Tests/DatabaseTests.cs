using FluentAssertions;
using ProcAI.Core.Data;
using ProcAI.Core.Models;
using Xunit;

namespace ProcAI.Tests;

public class DatabaseTests : IDisposable
{
    private readonly string _path = Path.Combine(Path.GetTempPath(), $"procai_db_{Guid.NewGuid():N}.db");
    private readonly Database _db;

    public DatabaseTests() => _db = new Database(_path);

    [Fact]
    public void Settings_Roundtrip()
    {
        _db.SetSetting("k", new { a = 1, b = new[] { 1, 2, 3 } });
        var v = _db.GetSetting<Dictionary<string, object>>("k");
        v.Should().NotBeNull();
        _db.GetSetting<string>("missing", "default").Should().Be("default");
    }

    [Fact]
    public void Alert_Insert_And_Query()
    {
        var a = new Alert
        {
            Pid = 10, ProcessName = "x.exe", RiskScore = 80, Severity = Severity.High,
            Confidence = 0.9, Reasons = new() { "r1", "r2" }, RuleHits = new() { "cpu_high" },
        };
        var id = _db.InsertAlert(a);
        id.Should().BeGreaterThan(0);

        var rows = _db.GetAlerts();
        rows.Should().HaveCount(1);
        rows[0].ProcessName.Should().Be("x.exe");
        rows[0].Reasons.Should().BeEquivalentTo(new[] { "r1", "r2" });
        rows[0].Severity.Should().Be(Severity.High);
    }

    [Fact]
    public void Alert_SeverityFilter_And_Acknowledge()
    {
        _db.InsertAlert(new Alert { Pid = 1, ProcessName = "a", RiskScore = 20, Severity = Severity.Low, Confidence = 0.1 });
        var id = _db.InsertAlert(new Alert { Pid = 2, ProcessName = "b", RiskScore = 90, Severity = Severity.Critical, Confidence = 0.9 });

        _db.GetAlerts(minSeverity: Severity.High).Should().ContainSingle();
        _db.AcknowledgeAlert(id, "dismissed");
        _db.GetAlerts(unacknowledgedOnly: true).Should().ContainSingle(); // only the Low one remains
    }

    [Fact]
    public void Reputation_Lists_Lowercased()
    {
        _db.AddReputation("allow", "Trusted.EXE");
        _db.GetReputation("allow").Should().Contain("trusted.exe");
        _db.RemoveReputation("allow", "trusted.exe");
        _db.GetReputation("allow").Should().BeEmpty();
    }

    [Fact]
    public void LabelledSamples_Roundtrip()
    {
        _db.AddLabelledSample(new float[] { 1, 2, 3 }, 1);
        _db.AddLabelledSample(new float[] { 4, 5, 6 }, 0);
        _db.LabelledSampleCount().Should().Be(2);
        _db.GetLabelledSamples().Select(s => s.Label).Should().BeEquivalentTo(new[] { true, false });
    }

    public void Dispose()
    {
        _db.Dispose();
        try { if (File.Exists(_path)) File.Delete(_path); } catch { /* ignore */ }
    }
}
