using System.Collections.ObjectModel;
using System.Windows.Controls;
using System.Windows.Media;
using ProcAI.App.Services;
using ProcAI.Core.Detection;
using ProcAI.Core.Models;

namespace ProcAI.App.Views;

public sealed class FindingVm
{
    public string Severity { get; init; } = "";
    public string Detail { get; init; } = "";
    public Brush SeverityBrush { get; init; } = Brushes.Gray;
}

public partial class DeepScanPage : Page
{
    private readonly ObservableCollection<FindingVm> _findings = new();

    public DeepScanPage()
    {
        InitializeComponent();
        Findings.ItemsSource = _findings;
    }

    private void OnRun(object sender, System.Windows.RoutedEventArgs e) => Run(false);
    private void OnRunSim(object sender, System.Windows.RoutedEventArgs e) => Run(true);

    private void Run(bool simulate)
    {
        StatusText.Text = "Scanning...";
        var engine = AppServices.Instance.Engine;
        var results = simulate
            ? engine.ScanOnce(Simulation.Generate(), enrichReputation: false)
            : engine.ScanOnce();

        _findings.Clear();
        var groups = new (string Title, Func<DetectionResult, bool> Pred)[]
        {
            ("Unsigned / suspicious-location executables", r => r.Snapshot.IsSigned == false || r.Snapshot.InSuspiciousDir),
            ("Unusual parent-child chains", r => r.RuleHits.Any(h => h.RuleId.StartsWith("lineage"))),
            ("High resource usage", r => r.Snapshot.CpuPercent >= 60 || r.Snapshot.MemoryMb >= 1024 || r.Snapshot.ThreadCount >= 200),
            ("Heavy network activity", r => r.Snapshot.ConnectionCount >= 20),
            ("Startup-persistent items", r => r.Snapshot.IsStartupPersistent),
        };

        bool any = false;
        foreach (var (title, pred) in groups)
        {
            var items = results.Where(pred).OrderByDescending(r => r.RiskScore).Take(25).ToList();
            if (items.Count == 0) continue;
            any = true;
            _findings.Add(new FindingVm { Severity = "GROUP", Detail = $"{title}  ({items.Count})", SeverityBrush = Brushes.SteelBlue });
            foreach (var r in items)
                _findings.Add(new FindingVm
                {
                    Severity = r.Severity.Label(),
                    Detail = $"{r.Snapshot.Name} (PID {r.Snapshot.Pid})  -  risk {r.RiskScore:0}  -  {r.Snapshot.ExePath}",
                    SeverityBrush = UiHelpers.SeverityBrush(r.Severity),
                });
        }

        int flagged = results.Count(r => r.Severity >= Severity.Medium);
        StatusText.Text = any
            ? $"Scanned {results.Count} processes — {flagged} at MEDIUM+ risk."
            : $"Scanned {results.Count} processes — no noteworthy findings.";
    }
}
