using System.Text.Json;
using Dapper;
using Microsoft.Data.Sqlite;
using ProcAI.Core.Configuration;
using ProcAI.Core.Detection;
using ProcAI.Core.Models;

namespace ProcAI.Core.Data;

/// <summary>
/// Local SQLite persistence shared by the engine, service and GUI. All data
/// remains on the user's machine. A single connection is guarded by a lock so
/// the monitor thread and the GUI thread can both use it safely. Also provides
/// the <see cref="IBaselineStore"/> used by the baseline manager.
/// </summary>
public sealed class Database : IBaselineStore, IDisposable
{
    private readonly SqliteConnection _conn;
    private readonly object _lock = new();

    public Database(string? path = null)
    {
        path ??= AppPaths.Default.DbPath;
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        _conn = new SqliteConnection($"Data Source={path}");
        _conn.Open();
        _conn.Execute("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;");
        InitSchema();
    }

    private void InitSchema()
    {
        lock (_lock) _conn.Execute(SchemaSql);
    }

    // ------------------------------------------------------------------ //
    // Settings (key/value)
    // ------------------------------------------------------------------ //
    public void SetSetting(string key, object value)
    {
        lock (_lock)
            _conn.Execute(
                "INSERT INTO settings(key,value,updated_at) VALUES(@k,@v,@t) " +
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                new { k = key, v = JsonSerializer.Serialize(value), t = Now() });
    }

    public T? GetSetting<T>(string key, T? fallback = default)
    {
        lock (_lock)
        {
            var v = _conn.QueryFirstOrDefault<string>("SELECT value FROM settings WHERE key=@k", new { k = key });
            if (v is null) return fallback;
            try { return JsonSerializer.Deserialize<T>(v); } catch { return fallback; }
        }
    }

    // ------------------------------------------------------------------ //
    // Process history
    // ------------------------------------------------------------------ //
    public void InsertSnapshots(IEnumerable<(ProcessSnapshot Snap, double Risk, int Severity)> rows)
    {
        lock (_lock)
        {
            using var tx = _conn.BeginTransaction();
            foreach (var (s, risk, sev) in rows)
            {
                _conn.Execute(
                    @"INSERT INTO process_history
                      (ts,pid,name,exe_path,username,ppid,parent_name,cpu_percent,memory_rss,
                       memory_percent,num_threads,num_handles,num_connections,is_signed,
                       in_suspicious_dir,risk_score,severity)
                      VALUES(@ts,@pid,@name,@exe,@user,@ppid,@parent,@cpu,@mem,@memp,@threads,
                             @handles,@conns,@signed,@susp,@risk,@sev)",
                    new
                    {
                        ts = s.Timestamp, pid = s.Pid, name = s.Name, exe = s.ExePath, user = s.Username,
                        ppid = s.Ppid, parent = s.ParentName, cpu = s.CpuPercent, mem = s.MemoryRss,
                        memp = s.MemoryPercent, threads = s.ThreadCount, handles = s.HandleCount,
                        conns = s.ConnectionCount, signed = s.IsSigned is null ? (int?)null : (s.IsSigned.Value ? 1 : 0),
                        susp = s.InSuspiciousDir ? 1 : 0, risk, sev,
                    }, tx);
            }
            tx.Commit();
        }
    }

    public IReadOnlyList<dynamic> RecentProcessHistory(int? pid = null, int limit = 200)
    {
        lock (_lock)
        {
            string sql = pid is null
                ? "SELECT * FROM process_history ORDER BY ts DESC LIMIT @lim"
                : "SELECT * FROM process_history WHERE pid=@pid ORDER BY ts DESC LIMIT @lim";
            return _conn.Query(sql, new { pid, lim = limit }).ToList();
        }
    }

    // ------------------------------------------------------------------ //
    // Alerts
    // ------------------------------------------------------------------ //
    public long InsertAlert(Alert a)
    {
        lock (_lock)
        {
            return _conn.ExecuteScalar<long>(
                @"INSERT INTO alerts
                  (ts,pid,process_name,exe_path,username,risk_score,severity,confidence,
                   reasons_json,rule_hits_json,ml_probability,recommended_action,acknowledged,resolution)
                  VALUES(@ts,@pid,@name,@exe,@user,@risk,@sev,@conf,@reasons,@hits,@mlp,@action,@ack,@res);
                  SELECT last_insert_rowid();",
                new
                {
                    ts = a.Timestamp, pid = a.Pid, name = a.ProcessName, exe = a.ExePath, user = a.Username,
                    risk = a.RiskScore, sev = (int)a.Severity, conf = a.Confidence,
                    reasons = JsonSerializer.Serialize(a.Reasons), hits = JsonSerializer.Serialize(a.RuleHits),
                    mlp = a.MlProbability, action = a.RecommendedAction, ack = a.Acknowledged ? 1 : 0, res = a.Resolution,
                });
        }
    }

    public IReadOnlyList<Alert> GetAlerts(int limit = 200, Severity? minSeverity = null,
        bool unacknowledgedOnly = false, double? since = null)
    {
        var sql = "SELECT * FROM alerts WHERE 1=1";
        if (minSeverity is not null) sql += " AND severity >= @minSev";
        if (unacknowledgedOnly) sql += " AND acknowledged = 0";
        if (since is not null) sql += " AND ts >= @since";
        sql += " ORDER BY ts DESC LIMIT @lim";

        lock (_lock)
        {
            var rows = _conn.Query(sql, new
            {
                minSev = minSeverity is null ? 0 : (int)minSeverity.Value,
                since, lim = limit,
            });
            return rows.Select(MapAlert).ToList();
        }
    }

    public void AcknowledgeAlert(long id, string resolution = "")
    {
        lock (_lock)
            _conn.Execute("UPDATE alerts SET acknowledged=1, resolution=@res WHERE id=@id",
                new { id, res = resolution });
    }

    public Dictionary<int, int> AlertCountsBySeverity(double? since = null)
    {
        var sql = "SELECT severity, COUNT(*) c FROM alerts" + (since is not null ? " WHERE ts >= @since" : "") +
                  " GROUP BY severity";
        lock (_lock)
        {
            var result = new Dictionary<int, int>();
            foreach (var row in _conn.Query(sql, new { since }))
                result[(int)(long)row.severity] = (int)(long)row.c;
            return result;
        }
    }

    private static Alert MapAlert(dynamic r) => new()
    {
        Id = (long)r.id,
        Timestamp = (double)r.ts,
        Pid = (int)(long)r.pid,
        ProcessName = (string)r.process_name,
        ExePath = r.exe_path as string ?? string.Empty,
        Username = r.username as string ?? string.Empty,
        RiskScore = (double)r.risk_score,
        Severity = (Severity)(int)(long)r.severity,
        Confidence = (double)r.confidence,
        Reasons = DeserializeList(r.reasons_json as string),
        RuleHits = DeserializeList(r.rule_hits_json as string),
        MlProbability = r.ml_probability is null ? 0.0 : (double)r.ml_probability,
        RecommendedAction = r.recommended_action as string ?? string.Empty,
        Acknowledged = ((long)r.acknowledged) != 0,
        Resolution = r.resolution as string ?? string.Empty,
    };

    private static List<string> DeserializeList(string? json) =>
        string.IsNullOrEmpty(json) ? new List<string>()
            : JsonSerializer.Deserialize<List<string>>(json) ?? new List<string>();

    // ------------------------------------------------------------------ //
    // IBaselineStore
    // ------------------------------------------------------------------ //
    public RunningStat? Get(string identityKey, string metric)
    {
        lock (_lock)
        {
            var r = _conn.QueryFirstOrDefault(
                "SELECT count,mean,m2,min_value,max_value FROM baselines WHERE identity_key=@id AND metric=@m",
                new { id = identityKey, m = metric });
            if (r is null) return null;
            return new RunningStat
            {
                Count = (long)r.count, Mean = (double)r.mean, M2 = (double)r.m2,
                MinValue = (double)r.min_value, MaxValue = (double)r.max_value,
            };
        }
    }

    public void Upsert(string identityKey, string metric, RunningStat stat)
    {
        lock (_lock)
            _conn.Execute(
                @"INSERT INTO baselines(identity_key,metric,count,mean,m2,min_value,max_value,updated_at)
                  VALUES(@id,@m,@count,@mean,@m2,@min,@max,@t)
                  ON CONFLICT(identity_key,metric) DO UPDATE SET
                    count=excluded.count, mean=excluded.mean, m2=excluded.m2,
                    min_value=excluded.min_value, max_value=excluded.max_value, updated_at=excluded.updated_at",
                new
                {
                    id = identityKey, m = metric, count = stat.Count, mean = stat.Mean, m2 = stat.M2,
                    min = double.IsInfinity(stat.MinValue) ? 0.0 : stat.MinValue,
                    max = double.IsInfinity(stat.MaxValue) ? 0.0 : stat.MaxValue, t = Now(),
                });
    }

    public int IdentityCount()
    {
        lock (_lock)
            return _conn.ExecuteScalar<int>("SELECT COUNT(DISTINCT identity_key) FROM baselines");
    }

    // ------------------------------------------------------------------ //
    // Model metadata
    // ------------------------------------------------------------------ //
    public void UpsertModelMetadata(ModelMetadata md)
    {
        lock (_lock)
            _conn.Execute(
                @"INSERT INTO model_metadata(name,algorithm,trained_at,n_samples,n_features,feature_names_json,
                    accuracy,precision_,recall,f1,notes)
                  VALUES(@name,@algo,@trained,@ns,@nf,@feats,@acc,@prec,@rec,@f1,@notes)
                  ON CONFLICT(name) DO UPDATE SET algorithm=excluded.algorithm, trained_at=excluded.trained_at,
                    n_samples=excluded.n_samples, n_features=excluded.n_features,
                    feature_names_json=excluded.feature_names_json, accuracy=excluded.accuracy,
                    precision_=excluded.precision_, recall=excluded.recall, f1=excluded.f1, notes=excluded.notes",
                new
                {
                    name = md.Name, algo = md.Algorithm, trained = md.TrainedAt, ns = md.SampleCount,
                    nf = md.FeatureCount, feats = JsonSerializer.Serialize(md.FeatureNames),
                    acc = md.Accuracy, prec = md.Precision, rec = md.Recall, f1 = md.F1, notes = md.Notes,
                });
    }

    public ModelMetadata? GetModelMetadata(string name)
    {
        lock (_lock)
        {
            var r = _conn.QueryFirstOrDefault("SELECT * FROM model_metadata WHERE name=@n", new { n = name });
            if (r is null) return null;
            return new ModelMetadata
            {
                Name = (string)r.name, Algorithm = (string)r.algorithm, TrainedAt = (double)r.trained_at,
                SampleCount = (int)(long)r.n_samples, FeatureCount = (int)(long)r.n_features,
                FeatureNames = DeserializeList(r.feature_names_json as string),
                Accuracy = r.accuracy is null ? 0 : (double)r.accuracy,
                Precision = r.precision_ is null ? 0 : (double)r.precision_,
                Recall = r.recall is null ? 0 : (double)r.recall,
                F1 = r.f1 is null ? 0 : (double)r.f1,
                Notes = r.notes as string ?? string.Empty,
            };
        }
    }

    // ------------------------------------------------------------------ //
    // Reputation lists
    // ------------------------------------------------------------------ //
    public void AddReputation(string listType, string pattern, string note = "")
    {
        lock (_lock)
            _conn.Execute(
                "INSERT OR IGNORE INTO reputation_list(list_type,pattern,note,created_at) VALUES(@t,@p,@n,@c)",
                new { t = listType, p = pattern.ToLowerInvariant(), n = note, c = Now() });
    }

    public void RemoveReputation(string listType, string pattern)
    {
        lock (_lock)
            _conn.Execute("DELETE FROM reputation_list WHERE list_type=@t AND pattern=@p",
                new { t = listType, p = pattern.ToLowerInvariant() });
    }

    public IReadOnlyList<string> GetReputation(string listType)
    {
        lock (_lock)
            return _conn.Query<string>("SELECT pattern FROM reputation_list WHERE list_type=@t",
                new { t = listType }).ToList();
    }

    // ------------------------------------------------------------------ //
    // Labelled samples
    // ------------------------------------------------------------------ //
    public void AddLabelledSample(float[] features, int label, string source = "user")
    {
        lock (_lock)
            _conn.Execute("INSERT INTO labelled_samples(ts,features_json,label,source) VALUES(@t,@f,@l,@s)",
                new { t = Now(), f = JsonSerializer.Serialize(features), l = label, s = source });
    }

    public IReadOnlyList<(float[] Features, bool Label)> GetLabelledSamples()
    {
        lock (_lock)
        {
            var list = new List<(float[], bool)>();
            foreach (var r in _conn.Query("SELECT features_json,label FROM labelled_samples"))
            {
                var feats = JsonSerializer.Deserialize<float[]>((string)r.features_json) ?? Array.Empty<float>();
                list.Add((feats, ((long)r.label) != 0));
            }
            return list;
        }
    }

    public int LabelledSampleCount()
    {
        lock (_lock) return _conn.ExecuteScalar<int>("SELECT COUNT(*) FROM labelled_samples");
    }

    // ------------------------------------------------------------------ //
    // Retention
    // ------------------------------------------------------------------ //
    public Dictionary<string, int> PruneRetention(int processHistoryDays, int? alertDays = null)
    {
        double now = Now();
        var deleted = new Dictionary<string, int>();
        lock (_lock)
        {
            deleted["process_history"] = _conn.Execute(
                "DELETE FROM process_history WHERE ts < @cut", new { cut = now - processHistoryDays * 86400.0 });
            if (alertDays is not null)
                deleted["alerts"] = _conn.Execute(
                    "DELETE FROM alerts WHERE ts < @cut AND acknowledged = 1",
                    new { cut = now - alertDays.Value * 86400.0 });
        }
        return deleted;
    }

    private static double Now() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;

    public void Dispose()
    {
        lock (_lock) { _conn.Close(); _conn.Dispose(); }
    }

    // ------------------------------------------------------------------ //
    private const string SchemaSql = @"
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS process_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, pid INTEGER NOT NULL, name TEXT NOT NULL,
    exe_path TEXT, username TEXT, ppid INTEGER, parent_name TEXT, cpu_percent REAL, memory_rss INTEGER,
    memory_percent REAL, num_threads INTEGER, num_handles INTEGER, num_connections INTEGER,
    is_signed INTEGER, in_suspicious_dir INTEGER, risk_score REAL, severity INTEGER);
CREATE INDEX IF NOT EXISTS idx_ph_ts ON process_history(ts);
CREATE INDEX IF NOT EXISTS idx_ph_pid ON process_history(pid);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, pid INTEGER NOT NULL, process_name TEXT NOT NULL,
    exe_path TEXT, username TEXT, risk_score REAL NOT NULL, severity INTEGER NOT NULL, confidence REAL NOT NULL,
    reasons_json TEXT, rule_hits_json TEXT, ml_probability REAL, recommended_action TEXT,
    acknowledged INTEGER NOT NULL DEFAULT 0, resolution TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts);
CREATE INDEX IF NOT EXISTS idx_alerts_sev ON alerts(severity);
CREATE TABLE IF NOT EXISTS baselines (
    identity_key TEXT NOT NULL, metric TEXT NOT NULL, count INTEGER NOT NULL, mean REAL NOT NULL,
    m2 REAL NOT NULL, min_value REAL, max_value REAL, updated_at REAL NOT NULL,
    PRIMARY KEY (identity_key, metric));
CREATE TABLE IF NOT EXISTS model_metadata (
    name TEXT PRIMARY KEY, algorithm TEXT NOT NULL, trained_at REAL NOT NULL, n_samples INTEGER NOT NULL,
    n_features INTEGER NOT NULL, feature_names_json TEXT NOT NULL, accuracy REAL, precision_ REAL,
    recall REAL, f1 REAL, notes TEXT);
CREATE TABLE IF NOT EXISTS reputation_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT, list_type TEXT NOT NULL, pattern TEXT NOT NULL, note TEXT,
    created_at REAL NOT NULL, UNIQUE(list_type, pattern));
CREATE TABLE IF NOT EXISTS labelled_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, features_json TEXT NOT NULL,
    label INTEGER NOT NULL, source TEXT NOT NULL DEFAULT 'user');
";
}
