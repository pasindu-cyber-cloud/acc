using System.Windows.Media;
using ProcAI.Core.Models;

namespace ProcAI.App.Services;

/// <summary>Shared colour mapping for severities/risk scores in the GUI.</summary>
public static class UiHelpers
{
    public static Brush SeverityBrush(Severity s) => new SolidColorBrush(s switch
    {
        Severity.Critical => Color.FromRgb(0xE7, 0x4C, 0x3C),
        Severity.High => Color.FromRgb(0xE6, 0x7E, 0x22),
        Severity.Medium => Color.FromRgb(0xF4, 0xD0, 0x3F),
        Severity.Low => Color.FromRgb(0x58, 0xD6, 0x8D),
        _ => Color.FromRgb(0x5D, 0xAD, 0xE2),
    });

    public static Brush RiskBrush(double score) => SeverityBrush(SeverityExtensions.FromScore(score));
}
