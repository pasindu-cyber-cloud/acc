using System.Text;
using ProcAI.Core.Models;

namespace ProcAI.Core.Assistant;

/// <summary>
/// Offline, deterministic, plain-language explanations (no network, no AI keys).
/// The default Proc Assistant backend and the source of truth for *why* ProcAI
/// reached a verdict. Auditable, reproducible and privacy-preserving.
/// </summary>
public static class Explainer
{
    private static string RiskPhrase(Severity s) => s switch
    {
        Severity.Critical => "a critical-risk process that needs immediate attention",
        Severity.High => "a high-risk process you should review soon",
        Severity.Medium => "a medium-risk process worth keeping an eye on",
        Severity.Low => "a low-risk anomaly",
        _ => "normal-looking behaviour",
    };

    public static string SummariseAlert(DetectionResult r)
    {
        var s = r.Snapshot;
        return $"{s.Name} (PID {s.Pid}) is {RiskPhrase(r.Severity)} - risk {r.RiskScore:0}/100, " +
               $"confidence {r.Confidence:P0}.";
    }

    public static string ExplainDetection(DetectionResult r)
    {
        var s = r.Snapshot;
        var sb = new StringBuilder();
        sb.AppendLine($"## {s.Name} (PID {s.Pid})").AppendLine();
        sb.AppendLine($"**Verdict:** {r.Severity.Label()} risk ({r.RiskScore:0}/100), confidence {r.Confidence:P0}.")
          .AppendLine();

        sb.AppendLine("**What this process is doing**");
        sb.AppendLine($"- CPU: {s.CpuPercent:0}%  |  Memory: {s.MemoryMb:0} MB ({s.MemoryPercent:0}% of RAM)  |  Threads: {s.ThreadCount}");
        sb.AppendLine($"- Network: {s.ConnectionCount} connections to {s.RemoteEndpointCount} distinct hosts");
        if (!string.IsNullOrEmpty(s.ExePath)) sb.AppendLine($"- Location: {s.ExePath}");
        if (!string.IsNullOrEmpty(s.ParentName)) sb.AppendLine($"- Started by: {s.ParentName} (PID {s.Ppid})");
        string sign = s.IsSigned == false ? "unsigned"
            : s.IsSigned == true ? "signed" + (string.IsNullOrEmpty(s.Signer) ? "" : $" by {s.Signer}")
            : "unknown signature";
        sb.AppendLine($"- Code signature: {sign}");
        if (s.LifetimeSeconds > 0) sb.AppendLine($"- Running for: {s.LifetimeSeconds / 60.0:0.0} minutes");
        sb.AppendLine();

        sb.AppendLine("**Why ProcAI flagged it**");
        if (r.RuleHits.Count > 0)
            foreach (var h in r.RuleHits) sb.AppendLine($"- {h.Title} (+{h.Points:0}): {h.Explanation}");
        else
            sb.AppendLine("- No individual rules fired strongly.");
        if (r.Ml.Available)
        {
            string verdict = r.Ml.IsSuspicious ? "suspicious" : "normal";
            sb.AppendLine($"- ML model ({r.Ml.ModelName}): classified as **{verdict}** (P(suspicious)={r.Ml.Probability:P0}).");
        }
        if (r.Deviation.Available && r.Deviation.DeviatingMetrics.Count > 0)
            sb.AppendLine($"- Baseline deviation on {string.Join(", ", r.Deviation.DeviatingMetrics)} (max Z-score {r.Deviation.MaxAbsZ:0.0}).");
        sb.AppendLine();

        if (r.Components.TryGetValue("rule_score", out var rs))
        {
            sb.AppendLine("**How the score was combined**");
            sb.AppendLine($"- Rule score {rs:0} (weight {Get(r, "w_rules"):P0}), " +
                          $"ML score {Get(r, "ml_score"):0} (weight {Get(r, "w_ml"):P0}), " +
                          $"baseline score {Get(r, "baseline_score"):0} (weight {Get(r, "w_baseline"):P0}).");
            sb.AppendLine();
        }

        sb.AppendLine("**Recommended action**");
        sb.AppendLine($"- {r.RecommendedAction}");
        if (r.Suppressed)
            sb.AppendLine("- Note: this process is on your trusted allowlist, so no alert was raised.");
        sb.AppendLine();
        sb.AppendLine("_Explanation generated offline by ProcAI. No data left your machine._");
        return sb.ToString();
    }

    private static double Get(DetectionResult r, string key) =>
        r.Components.TryGetValue(key, out var v) ? v : 0.0;

    public static IReadOnlyList<string> InvestigationGuide(DetectionResult r)
    {
        var s = r.Snapshot;
        var steps = new List<string>();
        var ruleIds = r.RuleHits.Select(h => h.RuleId).ToHashSet();

        steps.Add($"Confirm whether you recognise '{s.Name}' and expect it to be running now.");
        if (!string.IsNullOrEmpty(s.ExePath))
            steps.Add($"Verify the executable location is legitimate: {s.ExePath}");
        if (ruleIds.Contains("unsigned") || s.IsSigned == false)
            steps.Add("Check the publisher/signature; treat unsigned binaries with caution.");
        if (ruleIds.Contains("net_many") || ruleIds.Contains("net_elevated"))
            steps.Add("Review the remote addresses it is connecting to; look for unknown IPs/domains.");
        if (ruleIds.Contains("lineage_office_shell") || ruleIds.Contains("lineage_unusual_shell"))
            steps.Add($"Investigate the parent process '{s.ParentName}' - why did it start a shell?");
        if (ruleIds.Contains("cpu_high") || ruleIds.Contains("thread_storm") || ruleIds.Contains("mem_high"))
            steps.Add("Determine whether the resource usage matches the program's normal workload.");
        if (ruleIds.Contains("path_suspicious"))
            steps.Add("Be cautious: software rarely runs legitimately from Temp/Downloads folders.");
        steps.Add("If unsure, leave monitoring on and watch whether the behaviour persists or escalates.");
        steps.Add("Only terminate the process after confirming it is not a needed system task " +
                  "(ProcAI requires explicit confirmation before terminating).");
        return steps;
    }
}
