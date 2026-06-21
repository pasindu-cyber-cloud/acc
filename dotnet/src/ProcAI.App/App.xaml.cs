using System.Windows;
using ProcAI.App.Services;
using ProcAI.App.Views;

namespace ProcAI.App;

/// <summary>
/// WPF application bootstrap: initialise the shared engine, gate on first-run
/// consent, then show the Fluent dashboard.
/// </summary>
public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        AppServices.Instance.Initialize();

        if (!AppServices.Instance.Settings.ConsentAccepted)
        {
            var consent = new ConsentWindow();
            if (consent.ShowDialog() != true)
            {
                Shutdown();
                return;
            }
            var s = AppServices.Instance.Settings;
            s.ConsentAccepted = true;
            s.ConsentVersion = "1.0";
            AppServices.Instance.ApplySettings(s);
            AppServices.Instance.Engine.Audit.Record("consent.accept", new { version = "1.0" });
        }

        var main = new MainWindow();
        MainWindow = main;
        main.Show();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        AppServices.Instance.Shutdown();
        base.OnExit(e);
    }
}
