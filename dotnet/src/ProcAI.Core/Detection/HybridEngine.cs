using ProcAI.Core.Configuration;
using ProcAI.Core.Models;

namespace ProcAI.Core.Detection;

/// <summary>Resolved tunables for one evaluation (derived from <see cref="Settings"/>).</summary>
public sealed class HybridConfig
{
    public SensitivityProfile Profile { get; init; }
    public double MlWeight { get; init; }
    public double Threshold { get; init; }
    public bool EnableMl { get; init; }
    public bool SuppressTrusted { get; init; }
    public IReadOnlySet<string> Allowlist { get; init; } = new HashSet<string>();
    public IReadOnlySet<string> Blocklist { get; init; } = new HashSet<string>();
    public bool LearningMode { get; init; }

    public static HybridConfig FromSettings(
        Settings settings,
        bool learningMode = false,
        IEnumerable<string>? extraAllow = null,
        IEnumerable<string>? extraBlock = null)
    {
        var allow = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var p in settings.Allowlist) allow.Add(p.ToLowerInvariant());
        if (extraAllow != null) foreach (var p in extraAllow) allow.Add(p.ToLowerInvariant());

        var block = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var p in settings.Blocklist) block.Add(p.ToLowerInvariant());
        if (extraBlock != null) foreach (var p in extraBlock) block.Add(p.ToLowerInvariant());

        return new HybridConfig
        {
            Profile = settings.Sensitivity,
            MlWeight = settings.EnableMl ? settings.Sensitivity.MlWeight() : 0.0,
            Threshold = settings.Sensitivity.AlertThreshold(),
            EnableMl = settings.EnableMl,
            SuppressTrusted = settings.SuppressTrusted,
            Allowlist = allow,
            Blocklist = block,
            LearningMode = learningMode,
        };
    }
}

/// <summary>
/// Fuses the three detectors (rules + baseline Z-score + ML) into one verdict:
/// a 0-100 risk score, severity, confidence and an alert decision, with a fully
/// transparent component/weight breakdown.
/// </summary>
public sealed class HybridEngine
{
    private readonly RuleEngine _rules;
    private readonly BaselineManager _baseline;
    private readonly IMlClassifier? _classifier;

    public HybridEngine(RuleEngine rules, BaselineManager baseline, IMlClassifier? classifier = null)
    {
        _rules = rules;
        _baseline = baseline;
        _classifier = classifier;
    }

    private static double BaselineScore(BaselineDeviation d)
    {
        if (!d.Available || d.MaxAbsZ < 3.0) return 0.0;
        double intensity = Math.Min(1.0, (d.MaxAbsZ - 3.0) / 7.0);
        double breadth = Math.Min(1.0, d.DeviatingMetrics.Count / 4.0);
        return Math.Round(100.0 * (0.7 * intensity + 0.3 * breadth), 2);
    }

    private static bool MatchesList(ProcessSnapshot s, IReadOnlySet<string> patterns)
    {
        if (patterns.Count == 0) return false;
        var name = (s.Name ?? string.Empty).ToLowerInvariant();
        var exe = (s.ExePath ?? string.Empty).ToLowerInvariant();
        foreach (var pat in patterns)
        {
            if (string.IsNullOrEmpty(pat)) continue;
            if (pat == name || pat == exe || (exe.Length > 0 && exe.Contains(pat))) return true;
        }
        return false;
    }

    public DetectionResult Evaluate(ProcessSnapshot snap, HybridConfig config)
    {
        // 1. blocklist short-circuit (always alert)
        if (MatchesList(snap, config.Blocklist))
            return BlockedResult(snap);

        // 2. run detectors
        var dev = _baseline.Deviation(snap);
        var ruleEval = _rules.Evaluate(snap, dev);
        var ml = (config.EnableMl && _classifier is { IsLoaded: true })
            ? _classifier.Predict(snap)
            : MlResult.Unavailable();

        double ruleScore = ruleEval.Score;
        double mlScore = ml.Available ? ml.Probability * 100.0 : 0.0;
        double baseScore = BaselineScore(dev);

        // 3. resolve weights, redistributing for unavailable components
        double wMl = ml.Available ? config.MlWeight : 0.0;
        double remaining = 1.0 - wMl;
        double wRules, wBase;
        if (dev.Available) { wRules = remaining * 0.65; wBase = remaining * 0.35; }
        else { wRules = remaining; wBase = 0.0; }
        double totalW = wMl + wRules + wBase;
        if (totalW <= 0) totalW = 1.0;
        wMl /= totalW; wRules /= totalW; wBase /= totalW;

        double risk = wMl * mlScore + wRules * ruleScore + wBase * baseScore;

        // corroboration boost when independent detectors agree
        int strong = (ruleScore >= 50 ? 1 : 0) + (mlScore >= 60 ? 1 : 0) + (baseScore >= 50 ? 1 : 0);
        if (strong >= 2) risk = Math.Min(100.0, risk + 6.0 * (strong - 1));

        risk = Math.Round(Math.Clamp(risk, 0.0, 100.0), 2);
        var severity = SeverityExtensions.FromScore(risk);
        double confidence = Confidence(ruleEval.Hits, ml, dev, strong);

        var result = new DetectionResult
        {
            Snapshot = snap,
            RiskScore = risk,
            Severity = severity,
            Confidence = Math.Round(confidence, 3),
            ShouldAlert = false,
            RuleScore = ruleScore,
            RuleHits = ruleEval.Hits,
            Ml = ml,
            Deviation = dev,
            RecommendedAction = Recommend(severity),
        };
        result.Components["rule_score"] = ruleScore;
        result.Components["ml_score"] = Math.Round(mlScore, 2);
        result.Components["baseline_score"] = baseScore;
        result.Components["w_rules"] = Math.Round(wRules, 3);
        result.Components["w_ml"] = Math.Round(wMl, 3);
        result.Components["w_baseline"] = Math.Round(wBase, 3);
        result.Reasons.AddRange(BuildReasons(ruleEval, ml, dev));

        DecideAlert(result, snap, config);
        return result;
    }

    private static void DecideAlert(DetectionResult result, ProcessSnapshot snap, HybridConfig config)
    {
        if (config.SuppressTrusted && MatchesList(snap, config.Allowlist))
        {
            result.Suppressed = true;
            result.ShouldAlert = false;
            result.Reasons.Insert(0, "Process is on the trusted allowlist; alert suppressed.");
            return;
        }

        bool above = result.RiskScore >= config.Threshold;
        if (config.LearningMode)
        {
            result.ShouldAlert = above && result.RuleScore >= 60.0;
            if (above && !result.ShouldAlert)
                result.Reasons.Insert(0, "Learning mode active: alert held while baseline is established.");
        }
        else
        {
            result.ShouldAlert = above;
        }
    }

    private static DetectionResult BlockedResult(ProcessSnapshot snap)
    {
        var r = new DetectionResult
        {
            Snapshot = snap,
            RiskScore = 100.0,
            Severity = Severity.Critical,
            Confidence = 1.0,
            ShouldAlert = true,
            RuleScore = 100.0,
            RecommendedAction = "Investigate immediately; this item was explicitly blocklisted.",
        };
        r.Components["blocklist"] = 1.0;
        r.Reasons.Add("Process matches a user-defined blocklist entry.");
        return r;
    }

    private static double Confidence(IReadOnlyList<RuleHit> hits, MlResult ml, BaselineDeviation dev, int strong)
    {
        var parts = new List<double>();
        if (ml.Available) parts.Add(ml.Confidence);
        if (dev.Available) parts.Add(Math.Min(1.0, dev.Samples / 30.0));
        parts.Add(Math.Min(1.0, hits.Count / 4.0));
        double base_ = parts.Count > 0 ? parts.Average() : 0.3;
        base_ += 0.1 * Math.Max(0, strong - 1);
        return Math.Clamp(base_, 0.0, 1.0);
    }

    private static List<string> BuildReasons(RuleEvaluation ruleEval, MlResult ml, BaselineDeviation dev)
    {
        var reasons = ruleEval.Hits.Select(h => $"{h.Title}: {h.Explanation}").ToList();
        if (ml.Available)
        {
            string verdict = ml.IsSuspicious ? "suspicious" : "normal";
            reasons.Add($"ML model ({ml.ModelName}) classifies this process as {verdict} " +
                        $"(P(suspicious)={ml.Probability:P0}, confidence {ml.Confidence:P0}).");
        }
        if (dev.Available && dev.DeviatingMetrics.Count > 0)
            reasons.Add($"Statistical deviation from this program's baseline on " +
                        $"{string.Join(", ", dev.DeviatingMetrics)} (max Z={dev.MaxAbsZ:0.0}).");
        if (reasons.Count == 0)
            reasons.Add("No suspicious indicators detected; behaviour looks normal.");
        return reasons;
    }

    private static string Recommend(Severity severity) => severity switch
    {
        Severity.Critical => "Investigate now. Review the process lineage and network activity, and " +
            "consider terminating it after confirming it is not a needed system task.",
        Severity.High => "Review this process soon. Check its origin, signature and connections; use " +
            "the Proc Assistant for a guided explanation.",
        Severity.Medium => "Keep an eye on this process. If it is unfamiliar, inspect its details.",
        Severity.Low => "Low-risk anomaly. No action needed unless it recurs.",
        _ => "Informational only. No action needed.",
    };
}
