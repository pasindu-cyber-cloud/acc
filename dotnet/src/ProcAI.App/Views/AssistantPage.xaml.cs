using System.Windows.Controls;
using ProcAI.App.Services;
using ProcAI.Core.Assistant;

namespace ProcAI.App.Views;

public partial class AssistantPage : Page
{
    private string _lastContext = "";

    public AssistantPage()
    {
        InitializeComponent();
        Loaded += (_, _) => UpdateModeLabel();
    }

    private void UpdateModeLabel()
    {
        var s = AppServices.Instance.Settings;
        var status = AiBackends.Status(s);
        if (!status.AssistantEnabled)
            ModeLabel.Text = "Offline mode (deterministic, no network). Enable AI chat in Settings.";
        else if (status.SelectedBackend == "ollama")
            ModeLabel.Text = "AI chat: local Ollama (data stays on this machine).";
        else if (status.SelectedBackend == "gemini")
            ModeLabel.Text = status.CloudAllowed
                ? "AI chat: Gemini (cloud)."
                : "Gemini selected but blocked by privacy-first mode; using offline mode.";
        else
            ModeLabel.Text = "Offline mode.";
    }

    private void Append(string who, string text)
    {
        Chat.AppendText($"\n[{who}]\n{text}\n");
        Chat.ScrollToEnd();
    }

    private void OnExplainLatest(object sender, System.Windows.RoutedEventArgs e)
    {
        var engine = AppServices.Instance.Engine;
        var alerts = engine.Db.GetAlerts(limit: 1);
        if (alerts.Count == 0) { Append("Proc Assistant", "There are no alerts to explain yet."); return; }

        var a = alerts[0];
        var result = AppServices.Instance.Monitor.LastResults.FirstOrDefault(r => r.Snapshot.Pid == a.Pid);
        string text = result is not null
            ? Explainer.ExplainDetection(result)
            : $"{a.ProcessName} (PID {a.Pid}) - {a.Severity.Label()} risk {a.RiskScore:0}/100.\n"
              + string.Join("\n", a.Reasons.Select(r => "- " + r)) + $"\n\nRecommended: {a.RecommendedAction}";
        _lastContext = text;
        Append("Proc Assistant (offline)", text);
    }

    private async void OnSend(object sender, System.Windows.RoutedEventArgs e)
    {
        string q = (Input.Text ?? "").Trim();
        if (q.Length == 0) return;
        Input.Text = "";
        Append("You", q);

        var settings = AppServices.Instance.Settings;
        if (!settings.AiAssistantEnabled || settings.AiBackend == "offline")
        {
            Append("Proc Assistant (offline)", OfflineAnswer(q));
            return;
        }

        try
        {
            string answer = await AiBackends.AskAsync(settings, q, _lastContext, AppServices.Instance.Engine.Audit);
            Append("Proc Assistant", answer);
        }
        catch (AiUnavailableException ex)
        {
            Append("Proc Assistant", $"(AI unavailable) {ex.Message}\n\nFalling back to offline guidance:\n" + OfflineAnswer(q));
        }
    }

    private string OfflineAnswer(string q)
    {
        var ql = q.ToLowerInvariant();
        var engine = AppServices.Instance.Engine;
        if (ql.Contains("status") || ql.Contains("protect"))
        {
            var h = engine.Health();
            return $"Protection is {(AppServices.Instance.Monitor.Running ? "active" : "stopped")}. " +
                   $"Model loaded: {h.ModelLoaded}. Baselines: {h.BaselineIdentities}. Sensitivity: {h.Sensitivity}.";
        }
        if (int.TryParse(ql, out int pid))
        {
            var result = engine.Inspect(pid);
            if (result is not null) { _lastContext = Explainer.ExplainDetection(result); return _lastContext; }
            return $"I couldn't inspect PID {pid} (it may have exited).";
        }
        return "I'm in offline mode, so I can explain alerts and processes deterministically. " +
               "Try 'explain latest alert', ask about 'status', or type a PID number. " +
               "For free-form chat, enable the AI assistant in Settings.";
    }
}
