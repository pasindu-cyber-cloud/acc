using System.Collections.ObjectModel;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using ProcAI.App.Services;
using ProcAI.Core.Models;

namespace ProcAI.App.Views;

public sealed class AlertRowVm
{
    public string Severity { get; init; } = "";
    public string Title { get; init; } = "";
    public string Time { get; init; } = "";
    public Brush SeverityBrush { get; init; } = Brushes.Gray;
}

public partial class OverviewPage : Page
{
    private readonly ObservableCollection<AlertRowVm> _alerts = new();
    private readonly DispatcherTimer _timer;

    public OverviewPage()
    {
        InitializeComponent();
        RecentAlerts.ItemsSource = _alerts;
        _timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(2) };
        _timer.Tick += (_, _) => Refresh();
        Loaded += (_, _) => { Refresh(); _timer.Start(); };
        Unloaded += (_, _) => _timer.Stop();
    }

    private void Refresh()
    {
        var engine = AppServices.Instance.Engine;
        var monitor = AppServices.Instance.Monitor;

        bool running = monitor.Running && !monitor.Paused;
        ProtectionValue.Text = running ? "Protected" : "Stopped";
        ProtectionValue.Foreground = running
            ? new SolidColorBrush(Color.FromRgb(0x2E, 0xCC, 0x71))
            : new SolidColorBrush(Color.FromRgb(0x8B, 0x98, 0xA5));
        ProtectionSub.Text = $"{monitor.ScanCount} scans";
        ScannedValue.Text = monitor.LastResults.Count.ToString();

        double since = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0 - 86400;
        var counts = engine.Db.AlertCountsBySeverity(since);
        int total = counts.Values.Sum();
        int high = counts.GetValueOrDefault((int)Severity.High) + counts.GetValueOrDefault((int)Severity.Critical);
        AlertsValue.Text = total.ToString();
        AlertsSub.Text = $"{high} high/critical";

        var health = engine.Health();
        ModelValue.Text = health.ModelLoaded ? "Active" : "Rules+Stats";
        ModelSub.Text = health.ModelLoaded ? health.ModelName : "ML model not trained";

        var ov = engine.Collector.GetSystemOverview();
        MemValue.Text = $"{ov.MemoryPercent:0}%";
        MemSub.Text = $"{ov.MemoryUsedGb:0.0} / {ov.MemoryTotalGb:0.0} GB";

        if (health.LearningActive)
        {
            LearnValue.Text = "Learning";
            LearnSub.Text = $"{health.LearningRemainingMinutes} min left";
        }
        else
        {
            LearnValue.Text = "Active";
            LearnSub.Text = "baseline established";
        }
        BaselineValue.Text = health.BaselineIdentities.ToString();

        _alerts.Clear();
        foreach (var a in engine.Db.GetAlerts(limit: 12))
        {
            _alerts.Add(new AlertRowVm
            {
                Severity = a.Severity.Label(),
                Title = $"{a.ProcessName} (PID {a.Pid})  -  risk {a.RiskScore:0}",
                Time = DateTimeOffset.FromUnixTimeMilliseconds((long)(a.Timestamp * 1000)).LocalDateTime.ToString("HH:mm:ss"),
                SeverityBrush = UiHelpers.SeverityBrush(a.Severity),
            });
        }
        NoAlerts.Visibility = _alerts.Count == 0 ? System.Windows.Visibility.Visible : System.Windows.Visibility.Collapsed;
    }
}
