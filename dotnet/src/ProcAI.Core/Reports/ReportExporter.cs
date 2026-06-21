using System.Collections.Generic;
using System.Globalization;
using System.Text;
using ProcAI.Core.Configuration;
using ProcAI.Core.Models;
using QuestPDF.Fluent;
using QuestPDF.Helpers;
using QuestPDF.Infrastructure;

namespace ProcAI.Core.Reports;

/// <summary>
/// Export alerts and process history to CSV / PDF. CSV uses only the standard
/// library; PDF uses QuestPDF (Community license). All reports are written
/// locally to the per-user reports directory and the path is returned.
/// </summary>
public static class ReportExporter
{
    private static readonly AppPaths Paths = AppPaths.Default;

    static ReportExporter()
    {
        // QuestPDF Community license (free for individuals / small businesses).
        QuestPDF.Settings.License = LicenseType.Community;
    }

    public static bool PdfAvailable => true;

    private static string TimestampName(string prefix, string ext)
    {
        Paths.Ensure();
        return Path.Combine(Paths.ReportsDir, $"{prefix}_{DateTime.Now:yyyyMMdd_HHmmss}.{ext}");
    }

    private static string Csv(string? field)
    {
        field ??= string.Empty;
        if (field.Contains(',') || field.Contains('"') || field.Contains('\n'))
            return "\"" + field.Replace("\"", "\"\"") + "\"";
        return field;
    }

    // ------------------------------------------------------------------ //
    public static string ExportAlertsCsv(IEnumerable<Alert> alerts, string? path = null)
    {
        path ??= TimestampName("procai_alerts", "csv");
        var sb = new StringBuilder();
        sb.AppendLine("timestamp,pid,process_name,exe_path,username,risk_score,severity,confidence," +
                      "ml_probability,reasons,rule_hits,recommended_action,acknowledged,resolution");
        foreach (var a in alerts)
        {
            var when = DateTimeOffset.FromUnixTimeMilliseconds((long)(a.Timestamp * 1000)).LocalDateTime
                .ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture);
            sb.AppendLine(string.Join(",",
                Csv(when), a.Pid, Csv(a.ProcessName), Csv(a.ExePath), Csv(a.Username),
                a.RiskScore.ToString("0.00", CultureInfo.InvariantCulture), Csv(a.Severity.Label()),
                a.Confidence.ToString("0.000", CultureInfo.InvariantCulture),
                a.MlProbability.ToString("0.000", CultureInfo.InvariantCulture),
                Csv(string.Join(" | ", a.Reasons)), Csv(string.Join(", ", a.RuleHits)),
                Csv(a.RecommendedAction), a.Acknowledged ? "yes" : "no", Csv(a.Resolution)));
        }
        File.WriteAllText(path, sb.ToString());
        return path;
    }

    public static string ExportProcessHistoryCsv(IEnumerable<IDictionary<string, object>> rows, string? path = null)
    {
        path ??= TimestampName("procai_process_history", "csv");
        string[] fields =
        {
            "ts", "pid", "name", "exe_path", "username", "ppid", "parent_name", "cpu_percent",
            "memory_rss", "memory_percent", "num_threads", "num_connections", "is_signed",
            "in_suspicious_dir", "risk_score", "severity",
        };
        var sb = new StringBuilder();
        sb.AppendLine(string.Join(",", fields));
        foreach (var row in rows)
        {
            var values = fields.Select(f =>
            {
                if (!row.TryGetValue(f, out var v) || v is null) return string.Empty;
                if (f == "ts" && v is double d)
                    return DateTimeOffset.FromUnixTimeMilliseconds((long)(d * 1000)).LocalDateTime
                        .ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture);
                return Convert.ToString(v, CultureInfo.InvariantCulture) ?? string.Empty;
            });
            sb.AppendLine(string.Join(",", values.Select(Csv)));
        }
        File.WriteAllText(path, sb.ToString());
        return path;
    }

    // ------------------------------------------------------------------ //
    public static string ExportAlertsPdf(IReadOnlyList<Alert> alerts, IReadOnlyDictionary<string, string>? summary = null,
        string? path = null, string title = "ProcAI Security Report")
    {
        path ??= TimestampName("procai_report", "pdf");
        var accent = "#1976D2";

        Document.Create(container =>
        {
            container.Page(page =>
            {
                page.Margin(36);
                page.Size(PageSizes.A4);
                page.DefaultTextStyle(t => t.FontSize(9));

                page.Header().Column(col =>
                {
                    col.Item().Text(title).FontSize(20).Bold().FontColor(accent);
                    col.Item().Text($"Generated {DateTime.Now:yyyy-MM-dd HH:mm:ss}").FontSize(9).FontColor(Colors.Grey.Medium);
                });

                page.Content().PaddingVertical(10).Column(col =>
                {
                    if (summary is { Count: > 0 })
                    {
                        col.Item().PaddingBottom(8).Text("Summary").FontSize(13).Bold();
                        foreach (var (k, v) in summary)
                            col.Item().Text($"{k}: {v}");
                        col.Item().PaddingBottom(8);
                    }

                    col.Item().Text($"Alerts ({alerts.Count})").FontSize(13).Bold();
                    col.Item().PaddingTop(6).Table(table =>
                    {
                        table.ColumnsDefinition(c =>
                        {
                            c.ConstantColumn(95); c.RelativeColumn(2); c.ConstantColumn(45);
                            c.ConstantColumn(40); c.ConstantColumn(55); c.RelativeColumn(4);
                        });
                        void Head(string t) => table.Cell().Background(accent).Padding(4)
                            .Text(t).FontColor(Colors.White).Bold();
                        Head("Time"); Head("Process"); Head("PID"); Head("Risk"); Head("Severity"); Head("Top reason");

                        foreach (var a in alerts)
                        {
                            var when = DateTimeOffset.FromUnixTimeMilliseconds((long)(a.Timestamp * 1000))
                                .LocalDateTime.ToString("MM-dd HH:mm");
                            string reason = a.Reasons.Count > 0 ? a.Reasons[0] : string.Empty;
                            if (reason.Length > 80) reason = reason[..80];
                            table.Cell().Padding(3).Text(when);
                            table.Cell().Padding(3).Text(a.ProcessName);
                            table.Cell().Padding(3).Text(a.Pid.ToString());
                            table.Cell().Padding(3).Text(a.RiskScore.ToString("0"));
                            table.Cell().Padding(3).Text(a.Severity.Label());
                            table.Cell().Padding(3).Text(reason);
                        }
                    });
                });

                page.Footer().Text("Generated by ProcAI - defensive endpoint monitoring. Produced locally; no data left this machine.")
                    .FontSize(8).FontColor(Colors.Grey.Medium);
            });
        }).GeneratePdf(path);

        return path;
    }
}
