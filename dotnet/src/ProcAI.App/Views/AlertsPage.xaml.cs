using System.Collections.ObjectModel;
using System.Text;
using System.Windows.Controls;
using ProcAI.App.Services;
using ProcAI.Core.Models;

namespace ProcAI.App.Views;

public sealed class AlertListVm
{
    public long Id { get; init; }
    public string Time { get; init; } = "";
    public string Severity { get; init; } = "";
    public string Name { get; init; } = "";
    public int Pid { get; init; }
    public string Risk { get; init; } = "";
    public string Reason { get; init; } = "";
    public Alert Source { get; init; } = null!;
}

public partial class AlertsPage : Page
{
    private readonly ObservableCollection<AlertListVm> _rows = new();

    public AlertsPage()
    {
        InitializeComponent();
        Grid.ItemsSource = _rows;
        Loaded += (_, _) => Refresh();
    }

    private void OnFilterChanged(object sender, SelectionChangedEventArgs e) => Refresh();

    private string SelectedFilter() =>
        (FilterBox.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? "All";

    private void Refresh()
    {
        if (!IsLoaded && _rows.Count == 0 && FilterBox.SelectedItem is null) return;
        var db = AppServices.Instance.Engine.Db;
        string filter = SelectedFilter();

        IReadOnlyList<Alert> alerts;
        if (filter == "Unacknowledged")
            alerts = db.GetAlerts(limit: 500, unacknowledgedOnly: true);
        else if (filter is "Critical" or "High" or "Medium" or "Low")
        {
            var target = SeverityExtensions.FromName(filter);
            alerts = db.GetAlerts(limit: 500, minSeverity: target).Where(a => a.Severity == target).ToList();
        }
        else
            alerts = db.GetAlerts(limit: 500);

        _rows.Clear();
        foreach (var a in alerts)
        {
            _rows.Add(new AlertListVm
            {
                Id = a.Id ?? 0,
                Time = DateTimeOffset.FromUnixTimeMilliseconds((long)(a.Timestamp * 1000)).LocalDateTime.ToString("yyyy-MM-dd HH:mm:ss"),
                Severity = a.Severity.Label(),
                Name = a.ProcessName,
                Pid = a.Pid,
                Risk = a.RiskScore.ToString("0"),
                Reason = a.Reasons.Count > 0 ? a.Reasons[0] : "",
                Source = a,
            });
        }
    }

    private AlertListVm? Selected => Grid.SelectedItem as AlertListVm;

    private void OnSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        var a = Selected?.Source;
        if (a is null) return;
        var sb = new StringBuilder();
        sb.AppendLine($"{a.ProcessName}  (PID {a.Pid})");
        sb.AppendLine($"Severity: {a.Severity.Label()}    Risk: {a.RiskScore:0}/100    Confidence: {a.Confidence:P0}");
        sb.AppendLine($"Executable: {(string.IsNullOrEmpty(a.ExePath) ? "unknown" : a.ExePath)}");
        sb.AppendLine($"ML P(suspicious): {a.MlProbability:P0}");
        sb.AppendLine();
        sb.AppendLine("Reasons:");
        foreach (var r in a.Reasons) sb.AppendLine($"  - {r}");
        sb.AppendLine();
        sb.AppendLine("Rule hits: " + (a.RuleHits.Count > 0 ? string.Join(", ", a.RuleHits) : "none"));
        sb.AppendLine();
        sb.AppendLine("Recommended action:");
        sb.AppendLine($"  {a.RecommendedAction}");
        Detail.Text = sb.ToString();
    }

    private void OnAcknowledge(object sender, System.Windows.RoutedEventArgs e)
    {
        var a = Selected?.Source;
        if (a?.Id is null) return;
        AppServices.Instance.Engine.Db.AcknowledgeAlert(a.Id.Value, "dismissed");
        AppServices.Instance.Engine.Audit.Record("alert.acknowledge", new { id = a.Id, name = a.ProcessName });
        Refresh();
    }

    private void OnAllowlist(object sender, System.Windows.RoutedEventArgs e)
    {
        var a = Selected?.Source;
        if (a is null) return;
        string pattern = string.IsNullOrEmpty(a.ExePath) ? a.ProcessName : a.ExePath;
        AppServices.Instance.Engine.Db.AddReputation("allow", pattern, "from alert");
        if (a.Id is not null) AppServices.Instance.Engine.Db.AcknowledgeAlert(a.Id.Value, "allowlisted");
        AppServices.Instance.Engine.Audit.Record("reputation.allow.add", new { pattern });
        Refresh();
    }
}
