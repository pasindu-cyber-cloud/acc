namespace ProcAI.Core.Models;

/// <summary>A persisted alert raised for a suspicious process.</summary>
public sealed class Alert
{
    public long? Id { get; set; }
    public double Timestamp { get; set; } = ProcessSnapshot.UnixNow();
    public int Pid { get; set; }
    public string ProcessName { get; set; } = string.Empty;
    public string ExePath { get; set; } = string.Empty;
    public string Username { get; set; } = string.Empty;
    public double RiskScore { get; set; }
    public Severity Severity { get; set; } = Severity.Info;
    public double Confidence { get; set; }
    public List<string> Reasons { get; set; } = new();
    public List<string> RuleHits { get; set; } = new();
    public double MlProbability { get; set; }
    public string RecommendedAction { get; set; } = string.Empty;
    public bool Acknowledged { get; set; }
    public string Resolution { get; set; } = string.Empty; // "" | dismissed | terminated | allowlisted

    public static Alert FromDetection(DetectionResult result)
    {
        var s = result.Snapshot;
        return new Alert
        {
            Timestamp = s.Timestamp,
            Pid = s.Pid,
            ProcessName = s.Name,
            ExePath = s.ExePath,
            Username = s.Username,
            RiskScore = Math.Round(result.RiskScore, 2),
            Severity = result.Severity,
            Confidence = Math.Round(result.Confidence, 3),
            Reasons = new List<string>(result.Reasons),
            RuleHits = result.RuleHits.Select(h => h.RuleId).ToList(),
            MlProbability = Math.Round(result.Ml.Probability, 3),
            RecommendedAction = result.RecommendedAction,
        };
    }
}
