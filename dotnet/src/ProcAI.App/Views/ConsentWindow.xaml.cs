using System.Windows;
using Wpf.Ui.Controls;

namespace ProcAI.App.Views;

public partial class ConsentWindow : FluentWindow
{
    private const string Consent =
        "ProcAI is a defensive endpoint-monitoring tool. Before it starts, please review what it does:\n\n" +
        "WHAT PROCAI DOES\n" +
        "  • Reads the list of running processes and their resource usage (CPU, memory, threads, network " +
        "connections, executable path, parent process).\n" +
        "  • Builds a local baseline of normal behaviour and flags unusual activity using transparent rules, " +
        "statistics and an optional local machine-learning model.\n" +
        "  • Stores alerts, history and settings in a local database on THIS machine only.\n\n" +
        "WHAT PROCAI WILL NOT DO\n" +
        "  • It will not hide itself; a tray icon and dashboard are always available.\n" +
        "  • It will not disable or modify Windows Defender or any antivirus.\n" +
        "  • It will not send your data anywhere. The optional AI assistant is OFF by default and only contacts " +
        "a cloud service if you explicitly enable it and turn off privacy-first mode.\n" +
        "  • It will never terminate a process without your explicit confirmation.\n\n" +
        "You can stop monitoring, change settings, export your data, or uninstall ProcAI at any time. " +
        "By accepting you consent to local process monitoring as described.";

    public ConsentWindow()
    {
        InitializeComponent();
        ConsentText.Text = Consent;
    }

    private void OnAgreeChanged(object sender, RoutedEventArgs e) =>
        AcceptButton.IsEnabled = AgreeCheck.IsChecked == true;

    private void OnAccept(object sender, RoutedEventArgs e)
    {
        DialogResult = true;
        Close();
    }

    private void OnDecline(object sender, RoutedEventArgs e)
    {
        DialogResult = false;
        Close();
    }
}
