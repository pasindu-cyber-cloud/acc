namespace ProcAI.Core.Configuration;

/// <summary>
/// How aggressively ProcAI raises alerts. The profile scales the alert threshold
/// and the relative weight of ML vs. rules. Research is the most verbose.
/// </summary>
public enum SensitivityProfile
{
    Low,
    Balanced,
    Strict,
    Research,
}

public static class SensitivityProfileExtensions
{
    /// <summary>Final risk score (0-100) at/above which an alert is raised.</summary>
    public static double AlertThreshold(this SensitivityProfile p) => p switch
    {
        SensitivityProfile.Low => 75.0,
        SensitivityProfile.Balanced => 60.0,
        SensitivityProfile.Strict => 45.0,
        SensitivityProfile.Research => 30.0,
        _ => 60.0,
    };

    /// <summary>Weight given to the ML component in the hybrid fusion (0-1).</summary>
    public static double MlWeight(this SensitivityProfile p) => p switch
    {
        SensitivityProfile.Low => 0.35,
        SensitivityProfile.Balanced => 0.45,
        SensitivityProfile.Strict => 0.55,
        SensitivityProfile.Research => 0.50,
        _ => 0.45,
    };
}
