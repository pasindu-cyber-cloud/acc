using System.Collections.ObjectModel;
using System.Windows.Controls;
using ProcAI.App.Services;
using ProcAI.Core.Assistant;

namespace ProcAI.App.Views;

public partial class IntelligencePage : Page
{
    private readonly ObservableCollection<string> _guide = new();

    public IntelligencePage()
    {
        InitializeComponent();
        Guide.ItemsSource = _guide;
    }

    private void OnInspect(object sender, System.Windows.RoutedEventArgs e)
    {
        if (!int.TryParse(PidBox.Text?.Trim(), out int pid))
        {
            Explanation.Text = "Please enter a numeric PID.";
            return;
        }

        var engine = AppServices.Instance.Engine;
        var result = engine.Inspect(pid)
            ?? AppServices.Instance.Monitor.LastResults.FirstOrDefault(r => r.Snapshot.Pid == pid);

        _guide.Clear();
        if (result is null)
        {
            Explanation.Text = $"Could not inspect PID {pid} (it may have exited or require elevation).";
            return;
        }

        Explanation.Text = Explainer.ExplainDetection(result);
        foreach (var step in Explainer.InvestigationGuide(result)) _guide.Add(step);
    }
}
