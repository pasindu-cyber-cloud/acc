using System.Collections.ObjectModel;
using System.Windows.Controls;
using System.Windows.Media;
using ProcAI.App.Services;

namespace ProcAI.App.Views;

public sealed class HealthRowVm
{
    public string Label { get; init; } = "";
    public string Value { get; init; } = "";
    public Brush DotBrush { get; init; } = Brushes.Gray;
}

public partial class ProtectionHealthPage : Page
{
    private static readonly Brush Good = new SolidColorBrush(Color.FromRgb(0x2E, 0xCC, 0x71));
    private static readonly Brush Warn = new SolidColorBrush(Color.FromRgb(0xF3, 0x9C, 0x12));
    private static readonly Brush Muted = new SolidColorBrush(Color.FromRgb(0x8B, 0x98, 0xA5));

    private readonly ObservableCollection<HealthRowVm> _rows = new();

    public ProtectionHealthPage()
    {
        InitializeComponent();
        StatusList.ItemsSource = _rows;
        Loaded += (_, _) => Refresh();
    }

    private void Refresh()
    {
        var engine = AppServices.Instance.Engine;
        var monitor = AppServices.Instance.Monitor;
        var h = engine.Health();
        bool running = monitor.Running && !monitor.Paused;

        _rows.Clear();
        Add("Monitoring service", running ? "Protecting" : monitor.Paused ? "Paused" : "Stopped", running ? Good : Warn);
        Add("ML model", h.ModelLoaded ? $"Loaded ({h.ModelName})" : "Available, not trained", h.ModelLoaded ? Good : Muted);
        Add("Baseline engine", $"{h.BaselineIdentities} programs learned", h.BaselineIdentities > 0 ? Good : Muted);
        Add("Desktop notifications", AppServices.Instance.Settings.DesktopNotifications ? "On" : "Off",
            AppServices.Instance.Settings.DesktopNotifications ? Good : Muted);
        Add("Learning mode", h.LearningActive ? $"{h.LearningRemainingMinutes} min left" : "Complete", Good);
        Add("Audit-log integrity", h.AuditOk ? "Verified" : "TAMPER DETECTED", h.AuditOk ? Good : Warn);
        Add("Privacy-first mode", h.PrivacyFirst ? "On" : "Off", Good);

        if (running && h.AuditOk)
        {
            BannerTitle.Text = "You're protected";
            BannerTitle.Foreground = Good;
            BannerSub.Text = "ProcAI is actively monitoring process behaviour.";
        }
        else if (!running)
        {
            BannerTitle.Text = "Protection is off";
            BannerTitle.Foreground = Warn;
            BannerSub.Text = "Start protection from the sidebar to begin monitoring.";
        }
        else
        {
            BannerTitle.Text = "Attention needed";
            BannerTitle.Foreground = Warn;
            BannerSub.Text = "Review the items below.";
        }
    }

    private void Add(string label, string value, Brush brush) =>
        _rows.Add(new HealthRowVm { Label = label, Value = value, DotBrush = brush });
}
