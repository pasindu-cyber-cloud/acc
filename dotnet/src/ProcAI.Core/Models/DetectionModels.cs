namespace ProcAI.Core.Models;

/// <summary>One transparent heuristic that fired for a process.</summary>
public sealed record RuleHit(
    string RuleId,
    string Title,
    double Points,
    Severity Severity,
    string Explanation,
    IReadOnlyDictionary<string, object>? Evidence = null);

/// <summary>Output of the machine-learning classifier for one process.</summary>
public sealed class MlResult
{
    public bool Available { get; init; }
    public string ModelName { get; init; } = string.Empty;
    public bool IsSuspicious { get; init; }
    public double Probability { get; init; }   // P(suspicious), 0-1
    public double Confidence { get; init; }    // |p - 0.5| * 2, 0-1
    public IReadOnlyList<(string Feature, double Weight)> TopFeatures { get; init; }
        = Array.Empty<(string, double)>();

    public static MlResult Unavailable(string name = "") =>
        new() { Available = false, ModelName = name };
}

/// <summary>Z-score deviation of the current snapshot from the learned baseline.</summary>
public sealed class BaselineDeviation
{
    public bool Available { get; init; }
    public int Samples { get; init; }
    public IReadOnlyDictionary<string, double> ZScores { get; init; }
        = new Dictionary<string, double>();
    public double MaxAbsZ { get; init; }
    public IReadOnlyList<string> DeviatingMetrics { get; init; } = Array.Empty<string>();

    public static BaselineDeviation NotReady(int samples = 0) =>
        new() { Available = false, Samples = samples };
}

/// <summary>Final fused verdict produced by the hybrid engine for one snapshot.</summary>
public sealed class DetectionResult
{
    public required ProcessSnapshot Snapshot { get; init; }
    public double RiskScore { get; set; }                 // 0-100
    public Severity Severity { get; set; }
    public double Confidence { get; set; }                // 0-1
    public bool ShouldAlert { get; set; }

    public double RuleScore { get; set; }
    public IReadOnlyList<RuleHit> RuleHits { get; set; } = Array.Empty<RuleHit>();
    public MlResult Ml { get; set; } = MlResult.Unavailable();
    public BaselineDeviation Deviation { get; set; } = BaselineDeviation.NotReady();

    public Dictionary<string, double> Components { get; } = new();
    public List<string> Reasons { get; } = new();
    public bool Suppressed { get; set; }
    public string RecommendedAction { get; set; } = string.Empty;
}

/// <summary>Metadata describing a trained ML model on disk.</summary>
public sealed class ModelMetadata
{
    public string Name { get; set; } = string.Empty;
    public string Algorithm { get; set; } = string.Empty;
    public double TrainedAt { get; set; }
    public int SampleCount { get; set; }
    public int FeatureCount { get; set; }
    public List<string> FeatureNames { get; set; } = new();
    public double Accuracy { get; set; }
    public double Precision { get; set; }
    public double Recall { get; set; }
    public double F1 { get; set; }
    public string Notes { get; set; } = string.Empty;
}
