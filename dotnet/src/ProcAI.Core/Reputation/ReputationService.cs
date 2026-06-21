using System.Collections.Concurrent;
using Microsoft.Win32;
using ProcAI.Core.Configuration;
using ProcAI.Core.Models;

namespace ProcAI.Core.Reputation;

/// <summary>
/// Enriches a <see cref="ProcessSnapshot"/> with advisory, read-only reputation
/// signals: Authenticode signing status, whether the executable lives in a
/// commonly-abused directory, and whether it is referenced by an auto-start
/// location. These are signals, never proof of malice, and are always shown to
/// the user with their reasoning. ProcAI never creates or removes persistence.
/// </summary>
public interface IReputationService
{
    ProcessSnapshot Enrich(ProcessSnapshot snapshot, bool checkSignature = true);
    void ClearCaches();
}

public sealed class ReputationService : IReputationService
{
    private readonly ConcurrentDictionary<string, (bool? Signed, string Signer)> _signatureCache = new();
    private readonly Lazy<HashSet<string>> _startupRefs;

    public ReputationService()
    {
        _startupRefs = new Lazy<HashSet<string>>(LoadStartupReferences);
    }

    public ProcessSnapshot Enrich(ProcessSnapshot s, bool checkSignature = true)
    {
        s.InSuspiciousDir = IsSuspiciousPath(s.ExePath);
        s.IsStartupPersistent = IsStartupPersistent(s);
        if (checkSignature && !string.IsNullOrEmpty(s.ExePath))
        {
            var (signed, signer) = _signatureCache.GetOrAdd(
                s.ExePath.ToLowerInvariant(), _ => NativeAuthenticode.Verify(s.ExePath));
            s.IsSigned = signed;
            s.Signer = signer;
        }
        return s;
    }

    public void ClearCaches()
    {
        _signatureCache.Clear();
    }

    // ------------------------------------------------------------------ //

    public static bool IsSuspiciousPath(string? exePath)
    {
        if (string.IsNullOrEmpty(exePath)) return false;
        var p = exePath.Replace('/', '\\').ToLowerInvariant();
        return SuspiciousLocations.Hints.Any(h => p.Contains(h, StringComparison.OrdinalIgnoreCase));
    }

    private bool IsStartupPersistent(ProcessSnapshot s)
    {
        var refs = _startupRefs.Value;
        if (refs.Count == 0) return false;
        var exe = (s.ExePath ?? string.Empty).ToLowerInvariant();
        var name = (s.Name ?? string.Empty).ToLowerInvariant();
        foreach (var r in refs)
        {
            if (exe.Length > 0 && r.Contains(exe)) return true;
            if (name.Length > 0 && r.Contains(name)) return true;
        }
        return false;
    }

    /// <summary>Collect executable references from common auto-start locations (read-only).</summary>
    private static HashSet<string> LoadStartupReferences()
    {
        var refs = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        void ReadRunKey(RegistryKey root)
        {
            try
            {
                using var key = root.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run");
                if (key is null) return;
                foreach (var valueName in key.GetValueNames())
                {
                    if (key.GetValue(valueName) is string v && !string.IsNullOrWhiteSpace(v))
                        refs.Add(v.ToLowerInvariant());
                }
            }
            catch { /* key missing or access denied */ }
        }

        try { ReadRunKey(Registry.CurrentUser); } catch { }
        try { ReadRunKey(Registry.LocalMachine); } catch { }

        foreach (var folder in new[] { Environment.SpecialFolder.Startup, Environment.SpecialFolder.CommonStartup })
        {
            try
            {
                var path = Environment.GetFolderPath(folder);
                if (string.IsNullOrEmpty(path) || !Directory.Exists(path)) continue;
                foreach (var entry in Directory.EnumerateFileSystemEntries(path))
                {
                    refs.Add(entry.ToLowerInvariant());
                    refs.Add(Path.GetFileName(entry).ToLowerInvariant());
                }
            }
            catch { /* ignore */ }
        }

        return refs;
    }
}
