using FluentAssertions;
using ProcAI.Core.Detection;
using ProcAI.Core.Models;
using Xunit;

namespace ProcAI.Tests;

public class FeatureTests
{
    [Fact]
    public void FeatureKeys_MatchNames_AndVectorLength()
    {
        var snap = new ProcessSnapshot { Pid = 1, Name = "x.exe" };
        var feats = FeatureExtractor.Extract(snap);
        feats.Keys.Should().BeEquivalentTo(FeatureExtractor.FeatureNames);
        FeatureExtractor.ToVector(feats).Should().HaveCount(FeatureExtractor.FeatureNames.Length);
    }

    [Fact]
    public void Unsigned_And_SuspiciousDir_Flags()
    {
        var snap = new ProcessSnapshot { Pid = 1, Name = "x.exe", IsSigned = false, InSuspiciousDir = true };
        var feats = FeatureExtractor.Extract(snap);
        feats["is_unsigned"].Should().Be(1.0);
        feats["in_suspicious_dir"].Should().Be(1.0);
    }

    [Fact]
    public void UnknownSignature_IsNotFlaggedUnsigned()
    {
        var snap = new ProcessSnapshot { Pid = 1, Name = "x.exe", IsSigned = null };
        FeatureExtractor.Extract(snap)["is_unsigned"].Should().Be(0.0);
    }

    [Fact]
    public void Lifetime_And_Memory_AreDerived()
    {
        double now = ProcessSnapshot.UnixNow();
        var snap = new ProcessSnapshot
        {
            Pid = 1, Name = "x.exe", CreateTime = now - 600, Timestamp = now,
            MemoryRss = 100L * 1024 * 1024,
        };
        var feats = FeatureExtractor.Extract(snap);
        feats["lifetime_minutes"].Should().BeApproximately(10.0, 0.1);
        feats["memory_mb"].Should().BeApproximately(100.0, 0.5);
    }
}
