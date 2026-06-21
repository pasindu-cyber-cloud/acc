using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Windows.Controls;
using ProcAI.App.Services;
using ProcAI.Core.Models;

namespace ProcAI.App.Views;

public sealed class TimelineVm
{
    public string Time { get; init; } = "";
    public string Type { get; init; } = "";
    public string Severity { get; init; } = "";
    public string Process { get; init; } = "";
    public string Detail { get; init; } = "";
    public double Ts { get; init; }
}

public partial class TimelinePage : Page
{
    private readonly ObservableCollection<TimelineVm> _rows = new();

    public TimelinePage()
    {
        InitializeComponent();
        Grid.ItemsSource = _rows;
        Loaded += (_, _) => Refresh();
    }

    private void OnWindowChanged(object sender, SelectionChangedEventArgs e) => Refresh();
    private void OnRefresh(object sender, System.Windows.RoutedEventArgs e) => Refresh();

    private double SinceSeconds()
    {
        double now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
        string sel = (WindowBox.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? "Last 24h";
        return sel switch
        {
            "Last hour" => now - 3600,
            "Last 7 days" => now - 7 * 86400,
            _ => now - 86400,
        };
    }

    private void Refresh()
    {
        if (WindowBox.SelectedItem is null) return;
        var db = AppServices.Instance.Engine.Db;
        double since = SinceSeconds();
        var events = new List<TimelineVm>();

        foreach (var a in db.GetAlerts(limit: 500, since: since))
            events.Add(new TimelineVm
            {
                Ts = a.Timestamp,
                Time = DateTimeOffset.FromUnixTimeMilliseconds((long)(a.Timestamp * 1000)).LocalDateTime.ToString("yyyy-MM-dd HH:mm:ss"),
                Type = "Alert",
                Severity = a.Severity.Label(),
                Process = a.ProcessName,
                Detail = a.Reasons.Count > 0 ? a.Reasons[0] : a.RecommendedAction,
            });

        foreach (var row in db.RecentProcessHistory(limit: 400))
        {
            var dict = (IDictionary<string, object>)row;
            double ts = dict.TryGetValue("ts", out var t) && t is double d ? d : 0;
            if (ts < since) continue;
            int sev = dict.TryGetValue("severity", out var sv) && sv is long l ? (int)l : 0;
            if (sev < (int)Severity.Medium) continue;
            events.Add(new TimelineVm
            {
                Ts = ts,
                Time = DateTimeOffset.FromUnixTimeMilliseconds((long)(ts * 1000)).LocalDateTime.ToString("yyyy-MM-dd HH:mm:ss"),
                Type = "Process",
                Severity = ((Severity)sev).Label(),
                Process = dict.TryGetValue("name", out var n) ? n?.ToString() ?? "" : "",
                Detail = $"risk {(dict.TryGetValue("risk_score", out var rs) ? rs : 0)}",
            });
        }

        _rows.Clear();
        foreach (var ev in events.OrderByDescending(e => e.Ts).Take(600)) _rows.Add(ev);
    }
}
