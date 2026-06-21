using FluentAssertions;
using ProcAI.Core.Configuration;
using ProcAI.Core.Detection;
using ProcAI.Core.Models;
using Xunit;

namespace ProcAI.Tests;

public class SimulationTests
{
    [Fact]
    public void Simulation_Pids_Are_Synthetic_Negative()
    {
        foreach (var snap in Simulation.Generate())
            snap.Pid.Should().BeLessThan(0, "simulation PIDs must never collide with real processes");
    }

    [Fact]
    public void TrainingData_IsBalanced()
    {
        var data = Simulation.GenerateTrainingData(100, 60);
        data.Count(d => !d.Label).Should().Be(100);
        data.Count(d => d.Label).Should().Be(60);
    }

    [Fact]
    public void Pipeline_Flags_Abnormal_NotBenign()
    {
        var engine = new HybridEngine(new RuleEngine(),
            new BaselineManager(new InMemoryBaselineStore(), minSamples: 5));
        var cfg = HybridConfig.FromSettings(new Settings
        {
            EnableMl = false, Sensitivity = SensitivityProfile.Strict, LearningMode = false,
        });

        var snaps = Simulation.Generate();
        var results = snaps.Select(s => engine.Evaluate(s, cfg)).ToList();

        var temp = results.Single(r => r.Snapshot.Name == "sim_temp_unsigned.exe");
        ((int)temp.Severity).Should().BeGreaterThanOrEqualTo((int)Severity.Medium);

        var benign = results.Single(r => r.Snapshot.Name == "sim_explorer.exe");
        benign.ShouldAlert.Should().BeFalse();
    }
}
