using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using ProcAI.Core.Configuration;

namespace ProcAI.Core.Utils;

/// <summary>One entry in the tamper-evident audit log.</summary>
public sealed record AuditEntry(
    double Ts, string Iso, string Actor, string Action, string Detail, string Prev, string Hash);

/// <summary>
/// Hash-chained, append-only audit log of user and system actions. Each entry
/// stores the SHA-256 of the previous entry, so any after-the-fact deletion or
/// edit breaks the chain and is detectable via <see cref="Verify"/>. This is
/// evidence integrity, not secrecy — the log is human-readable JSON lines.
/// </summary>
public sealed class AuditLog
{
    private const string Genesis = "0000000000000000000000000000000000000000000000000000000000000000";
    private readonly string _path;
    private readonly object _lock = new();

    public AuditLog(string? path = null)
    {
        _path = path ?? AppPaths.Default.AuditPath;
    }

    public void Record(string action, object? detail = null, string actor = "user")
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
        lock (_lock)
        {
            string prev = LastHash();
            double ts = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
            string iso = DateTime.Now.ToString("yyyy-MM-ddTHH:mm:ss");
            string detailJson = JsonSerializer.Serialize(detail ?? new { });
            string hash = ComputeHash(prev, ts, actor, action, detailJson);
            var entry = new AuditEntry(ts, iso, actor, action, detailJson, prev, hash);
            File.AppendAllText(_path, JsonSerializer.Serialize(entry) + "\n");
        }
    }

    public IReadOnlyList<AuditEntry> ReadAll()
    {
        if (!File.Exists(_path)) return Array.Empty<AuditEntry>();
        var entries = new List<AuditEntry>();
        foreach (var line in File.ReadLines(_path))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            try
            {
                var e = JsonSerializer.Deserialize<AuditEntry>(line);
                if (e is not null) entries.Add(e);
            }
            catch (JsonException) { /* skip malformed line */ }
        }
        return entries;
    }

    /// <summary>Verify the chain. Returns (ok, indexOfFirstBrokenEntry or -1).</summary>
    public (bool Ok, int Index) Verify()
    {
        string prev = Genesis;
        var entries = ReadAll();
        for (int i = 0; i < entries.Count; i++)
        {
            var e = entries[i];
            string recomputed = ComputeHash(prev, e.Ts, e.Actor, e.Action, e.Detail);
            if (e.Prev != prev || recomputed != e.Hash)
                return (false, i);
            prev = e.Hash;
        }
        return (true, -1);
    }

    private string LastHash()
    {
        if (!File.Exists(_path)) return Genesis;
        string last = Genesis;
        foreach (var line in File.ReadLines(_path))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            try
            {
                var e = JsonSerializer.Deserialize<AuditEntry>(line);
                if (e is not null) last = e.Hash;
            }
            catch (JsonException) { /* skip */ }
        }
        return last;
    }

    private static string ComputeHash(string prev, double ts, string actor, string action, string detailJson)
    {
        // Canonical, internally-consistent representation.
        string canonical = $"{prev}|{ts:R}|{actor}|{action}|{detailJson}";
        byte[] bytes = SHA256.HashData(Encoding.UTF8.GetBytes(canonical));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }
}
