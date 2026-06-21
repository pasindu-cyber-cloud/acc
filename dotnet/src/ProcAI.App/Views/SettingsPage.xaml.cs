using System.Windows.Controls;
using System.Windows.Media;
using ProcAI.App.Services;
using ProcAI.Core.Configuration;
using ProcAI.Core.Detection;
using ProcAI.Core.Ml;

namespace ProcAI.App.Views;

public partial class SettingsPage : Page
{
    public SettingsPage()
    {
        InitializeComponent();
        ScanInterval.ValueChanged += (_, _) => ScanIntervalLabel.Text = $"{ScanInterval.Value:0}s";
        Loaded += (_, _) => LoadSettings();
    }

    private static void Select(ComboBox box, string value)
    {
        foreach (var item in box.Items)
            if (item is ComboBoxItem c && string.Equals(c.Content?.ToString(), value, StringComparison.OrdinalIgnoreCase))
            { box.SelectedItem = c; return; }
        if (box.Items.Count > 0) box.SelectedIndex = 0;
    }

    private static string Selected(ComboBox box) =>
        (box.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? "";

    private void LoadSettings()
    {
        var s = AppServices.Instance.Settings;
        Select(Sensitivity, s.Sensitivity.ToString());
        ScanInterval.Value = s.ScanIntervalSeconds;
        ScanIntervalLabel.Text = $"{s.ScanIntervalSeconds:0}s";
        LearningMode.IsChecked = s.LearningMode;
        StartWithWindows.IsChecked = s.StartWithWindows;
        TrayMin.IsChecked = s.StartMinimizedToTray;
        EnableMl.IsChecked = s.EnableMl;
        Select(Model, s.PreferredModel);
        Notifications.IsChecked = s.DesktopNotifications;
        Select(MinSeverity, s.NotifyMinSeverity);
        PrivacyFirst.IsChecked = s.PrivacyFirstMode;
        AiEnabled.IsChecked = s.AiAssistantEnabled;
        Select(AiBackend, s.AiBackend);
        OllamaHost.Text = s.AiOllamaHost;
        OllamaModel.Text = s.AiOllamaModel;
        GeminiKey.Password = s.AiGeminiApiKey;
        AllowBox.Text = string.Join("\n", s.Allowlist);
        BlockBox.Text = string.Join("\n", s.Blocklist);
        HistDays.Text = s.ProcessHistoryRetentionDays.ToString();
        LogDays.Text = s.LogRetentionDays.ToString();
    }

    private void OnTrain(object sender, System.Windows.RoutedEventArgs e)
    {
        TrainStatus.Text = "Training...";
        string modelName = Selected(Model);
        Task.Run(() =>
        {
            try
            {
                var data = Simulation.GenerateTrainingData();
                var md = MlClassifier.TrainAndSave(modelName, data);
                AppServices.Instance.Engine.Db.UpsertModelMetadata(md);
                Dispatcher.Invoke(() => TrainStatus.Text =
                    $"Trained {md.Algorithm}: acc {md.Accuracy:P0}, F1 {md.F1:P0} on {md.SampleCount} samples.");
            }
            catch (Exception ex)
            {
                Dispatcher.Invoke(() => TrainStatus.Text = $"Training failed: {ex.Message}");
            }
        });
    }

    private void OnSave(object sender, System.Windows.RoutedEventArgs e)
    {
        var s = AppServices.Instance.Settings.Clone();
        s.Sensitivity = Enum.TryParse<SensitivityProfile>(Selected(Sensitivity), out var prof) ? prof : SensitivityProfile.Balanced;
        s.ScanIntervalSeconds = ScanInterval.Value;
        s.LearningMode = LearningMode.IsChecked == true;
        s.StartWithWindows = StartWithWindows.IsChecked == true;
        s.StartMinimizedToTray = TrayMin.IsChecked == true;
        s.EnableMl = EnableMl.IsChecked == true;
        s.PreferredModel = Selected(Model);
        s.DesktopNotifications = Notifications.IsChecked == true;
        s.NotifyMinSeverity = Selected(MinSeverity);
        s.PrivacyFirstMode = PrivacyFirst.IsChecked == true;
        s.AiAssistantEnabled = AiEnabled.IsChecked == true;
        s.AiBackend = Selected(AiBackend);
        s.AiOllamaHost = OllamaHost.Text.Trim();
        s.AiOllamaModel = OllamaModel.Text.Trim();
        s.AiGeminiApiKey = GeminiKey.Password.Trim();
        s.Allowlist = AllowBox.Text.Split('\n').Select(x => x.Trim()).Where(x => x.Length > 0).ToList();
        s.Blocklist = BlockBox.Text.Split('\n').Select(x => x.Trim()).Where(x => x.Length > 0).ToList();
        if (int.TryParse(HistDays.Text, out int hd)) s.ProcessHistoryRetentionDays = hd;
        if (int.TryParse(LogDays.Text, out int ld)) s.LogRetentionDays = ld;

        AppServices.Instance.ApplySettings(s);
        SaveStatus.Foreground = new SolidColorBrush(Color.FromRgb(0x2E, 0xCC, 0x71));
        SaveStatus.Text = "Settings saved.";
    }
}
