using System.Collections.Generic;
using System.Diagnostics;
using System.Windows.Controls;
using System.Windows.Media;
using ProcAI.App.Services;
using ProcAI.Core.Configuration;
using ProcAI.Core.Reports;

namespace ProcAI.App.Views;

public partial class ReportsPage : Page
{
    public ReportsPage() => InitializeComponent();

    private void Done(string path)
    {
        StatusText.Foreground = new SolidColorBrush(Color.FromRgb(0x2E, 0xCC, 0x71));
        StatusText.Text = $"Saved: {path}";
    }

    private void OnAlertsCsv(object sender, System.Windows.RoutedEventArgs e)
    {
        var alerts = AppServices.Instance.Engine.Db.GetAlerts(limit: 10000);
        Done(ReportExporter.ExportAlertsCsv(alerts));
    }

    private void OnAlertsPdf(object sender, System.Windows.RoutedEventArgs e)
    {
        var alerts = AppServices.Instance.Engine.Db.GetAlerts(limit: 5000);
        var summary = new Dictionary<string, string>
        {
            ["Total alerts"] = alerts.Count.ToString(),
            ["Generated"] = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
            ["Sensitivity"] = AppServices.Instance.Settings.Sensitivity.ToString(),
        };
        Done(ReportExporter.ExportAlertsPdf(alerts, summary));
    }

    private void OnHistoryCsv(object sender, System.Windows.RoutedEventArgs e)
    {
        var rows = AppServices.Instance.Engine.Db.RecentProcessHistory(limit: 20000)
            .Select(r => (IDictionary<string, object>)r);
        Done(ReportExporter.ExportProcessHistoryCsv(rows));
    }

    private void OnOpenFolder(object sender, System.Windows.RoutedEventArgs e)
    {
        var path = AppPaths.Default.Ensure().ReportsDir;
        try { Process.Start(new ProcessStartInfo { FileName = path, UseShellExecute = true }); }
        catch
        {
            StatusText.Foreground = new SolidColorBrush(Color.FromRgb(0x8B, 0x98, 0xA5));
            StatusText.Text = $"Reports folder: {path}";
        }
    }
}
