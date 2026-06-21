using System.Windows;
using System.Windows.Media;
using System.Windows.Threading;
using ProcAI.App.Services;
using ProcAI.App.Views;
using Wpf.Ui.Controls;

namespace ProcAI.App;

public partial class MainWindow : FluentWindow
{
    private readonly DispatcherTimer _timer;

    public MainWindow()
    {
        InitializeComponent();

        RootNavigation.Loaded += (_, _) => RootNavigation.Navigate(typeof(OverviewPage));

        // Auto-start protection (consent already given).
        AppServices.Instance.Monitor.Start();

        _timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(2) };
        _timer.Tick += (_, _) => RefreshStatus();
        _timer.Start();
        RefreshStatus();
    }

    private void OnToggleProtection(object sender, RoutedEventArgs e)
    {
        var monitor = AppServices.Instance.Monitor;
        if (monitor.Running) monitor.Stop();
        else monitor.Start();
        RefreshStatus();
    }

    private void RefreshStatus()
    {
        var monitor = AppServices.Instance.Monitor;
        if (monitor.Running && !monitor.Paused)
        {
            StatusText.Text = "● Protected";
            StatusText.Foreground = new SolidColorBrush(Color.FromRgb(0x2E, 0xCC, 0x71));
            ToggleButton.Content = "Stop Protection";
            ToggleButton.Appearance = ControlAppearance.Danger;
        }
        else
        {
            StatusText.Text = "● Stopped";
            StatusText.Foreground = new SolidColorBrush(Color.FromRgb(0x8B, 0x98, 0xA5));
            ToggleButton.Content = "Start Protection";
            ToggleButton.Appearance = ControlAppearance.Success;
        }
    }
}
