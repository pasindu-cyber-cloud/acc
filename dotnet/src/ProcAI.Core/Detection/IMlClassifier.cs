using ProcAI.Core.Models;

namespace ProcAI.Core.Detection;

/// <summary>
/// Abstraction over the ML classifier so the hybrid engine can be unit-tested
/// without ML.NET. The concrete implementation lives in ProcAI.Core.Ml.
/// </summary>
public interface IMlClassifier
{
    string Name { get; }
    bool IsLoaded { get; }
    MlResult Predict(ProcessSnapshot snapshot);
}
