using System.Collections.ObjectModel;
using System.Windows.Controls;
using ProcAI.App.Services;
using ProcAI.Core.Detection;
using ProcAI.Core.Models;

namespace ProcAI.App.Views;

public sealed class ProcRowVm
{
    public int Pid { get; init; }
    public string Name { get; init; } = "";
    public string User { get; init; } = "";
    public string Cpu { get; init; } = "";
    public string MemMb { get; init; } = "";
    public int Threads { get; init; }
    public int Conns { get; init; }
    public string Risk { get; init; } = "";
    public string Severity { get; init; } = "";
    public string Signed { get; init; } = "";
    public string Path { get; init; } = "";
}

public partial class LiveProcessesPage : Page
{
    private readonly ObservableCollection<ProcRowVm> _rows = new();
    private IReadOnlyList<DetectionResult> _results = Array.Empty<DetectionResult>();

    public LiveProcessesPage()
    {
        InitializeComponent();
        Grid.ItemsSource = _rows;
        Loaded += (_, _) => LoadFromMonitorOrScan();
    }

    private void LoadFromMonitorOrScan()
    {
        var monitor = AppServices.Instance.Monitor;
        _results = monitor.LastResults.Count > 0 ? monitor.LastResults : AppServices.Instance.Engine.ScanOnce();
        Render();
    }

    private void OnRefresh(object sender, System.Windows.RoutedEventArgs e)
    {
        _results = AppServices.Instance.Engine.ScanOnce();
        Render();
    }

    private void OnSimulate(object sender, System.Windows.RoutedEventArgs e)
    {
        _results = AppServices.Instance.Engine.ScanOnce(Simulation.Generate(), enrichReputation: false);
        Render();
    }

    private void OnSearchChanged(object sender, TextChangedEventArgs e) => Render();

    private void Render()
    {
        string q = (SearchBox.Text ?? "").Trim().ToLowerInvariant();
        IEnumerable<DetectionResult> rows = _results;
        if (q.Length > 0)
            rows = rows.Where(r =>
                r.Snapshot.Name.ToLowerInvariant().Contains(q) ||
                (r.Snapshot.ExePath ?? "").ToLowerInvariant().Contains(q) ||
                (r.Snapshot.Username ?? "").ToLowerInvariant().Contains(q));

        _rows.Clear();
        foreach (var r in rows.OrderByDescending(r => r.RiskScore))
        {
            var s = r.Snapshot;
            _rows.Add(new ProcRowVm
            {
                Pid = s.Pid,
                Name = s.Name,
                User = s.Username,
                Cpu = s.CpuPercent.ToString("0"),
                MemMb = s.MemoryMb.ToString("0"),
                Threads = s.ThreadCount,
                Conns = s.ConnectionCount,
                Risk = r.RiskScore.ToString("0"),
                Severity = r.Severity.Label(),
                Signed = s.IsSigned == true ? "Yes" : s.IsSigned == false ? "No" : "?",
                Path = s.ExePath,
            });
        }
    }
}
