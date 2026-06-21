using FluentAssertions;
using ProcAI.Core.Utils;
using Xunit;

namespace ProcAI.Tests;

public class AuditLogTests : IDisposable
{
    private readonly string _path = Path.Combine(Path.GetTempPath(), $"procai_audit_{Guid.NewGuid():N}.log");

    [Fact]
    public void Records_And_Verifies()
    {
        var log = new AuditLog(_path);
        log.Record("test.one", new { x = 1 });
        log.Record("test.two", new { y = 2 });

        var entries = log.ReadAll();
        entries.Should().HaveCount(2);
        entries[0].Action.Should().Be("test.one");

        var (ok, idx) = log.Verify();
        ok.Should().BeTrue();
        idx.Should().Be(-1);
    }

    [Fact]
    public void Chain_Links_Entries()
    {
        var log = new AuditLog(_path);
        log.Record("a");
        log.Record("b");
        var entries = log.ReadAll();
        entries[1].Prev.Should().Be(entries[0].Hash);
    }

    [Fact]
    public void Tamper_IsDetected()
    {
        var log = new AuditLog(_path);
        log.Record("a", new { v = 1 });
        log.Record("b", new { v = 2 });

        var lines = File.ReadAllLines(_path);
        lines[0] = lines[0].Replace("\"v\":1", "\"v\":999");
        File.WriteAllLines(_path, lines);

        var (ok, idx) = log.Verify();
        ok.Should().BeFalse();
        idx.Should().Be(0);
    }

    public void Dispose()
    {
        try { if (File.Exists(_path)) File.Delete(_path); } catch { /* ignore */ }
    }
}
