using ProcAI.Core.Data;

namespace ProcAI.Core.Engine;

/// <summary>
/// Tracks whether ProcAI is still in its initial observation window. During
/// learning mode the engine computes everything but treats baseline-deviation
/// contributions as informational rather than alert-worthy.
/// </summary>
public sealed class LearningMode
{
    private readonly Database _db;

    public LearningMode(Database db) => _db = db;

    public void Start(int durationMinutes)
    {
        _db.SetSetting("learning_started_at", Now());
        _db.SetSetting("learning_duration_minutes", durationMinutes);
    }

    public bool HasStarted() => _db.GetSetting<double?>("learning_started_at") is not null;

    public double RemainingSeconds()
    {
        var started = _db.GetSetting<double?>("learning_started_at");
        var duration = _db.GetSetting<double?>("learning_duration_minutes");
        if (started is null || duration is null) return 0;
        double elapsed = Now() - started.Value;
        return Math.Max(0, duration.Value * 60.0 - elapsed);
    }

    public bool IsActive() => RemainingSeconds() > 0;

    private static double Now() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
}
