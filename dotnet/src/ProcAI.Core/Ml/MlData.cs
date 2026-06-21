using Microsoft.ML.Data;
using ProcAI.Core.Detection;

namespace ProcAI.Core.Ml;

/// <summary>
/// ML.NET input row. The feature vector length matches
/// <see cref="FeatureExtractor.FeatureNames"/> (kept in sync; update both together).
/// </summary>
public sealed class ProcessFeatures
{
    [VectorType(14)]
    public float[] Features { get; set; } = new float[14];

    [ColumnName("Label")]
    public bool Label { get; set; }
}

/// <summary>ML.NET prediction output.</summary>
public sealed class ProcessPrediction
{
    [ColumnName("PredictedLabel")]
    public bool IsSuspicious { get; set; }

    public float Probability { get; set; }

    public float Score { get; set; }
}
