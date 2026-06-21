# ProcAI Architecture & Detection Design

This document describes ProcAI's modules, data flow, database schema, scoring
formula, ML workflow and threading model.

## 1. Layered design

ProcAI separates a dependency-light **detection core** from optional, heavier
layers (ML, GUI, reporting, AI). The core runs on the Python standard library
plus `psutil`; everything else is optional and guarded behind lazy imports.

| Layer | Package | Responsibility |
|---|---|---|
| Telemetry | `core/telemetry.py` | Read process table via psutil |
| Reputation | `core/reputation.py` | Signing, suspicious paths, startup persistence |
| Features | `core/features.py` | Snapshot → numeric feature vector |
| Detectors | `core/rules.py`, `core/baseline.py`, `core/ml.py` | Three independent signals |
| Fusion | `core/hybrid.py` | Combine into risk/severity/decision |
| Orchestration | `core/engine.py`, `core/monitor.py` | Run pipeline, raise alerts, loop |
| Persistence | `data/database.py` | SQLite storage |
| Explainability | `assistant/` | Plain-language explanations + optional AI |
| Output | `reports/`, `service/` | CSV/PDF, tray, notifications, service |
| UI | `gui/` | CustomTkinter dashboard |
| Integrity | `utils/audit.py` | Tamper-evident audit log |

## 2. Detection data flow

```
ProcessSnapshot ── enrich (reputation) ──┐
                                         ▼
                                    features.extract
              ┌──────────────────────────┼───────────────────────────┐
              ▼                          ▼                            ▼
        RuleEngine               BaselineManager                 MLClassifier
   (transparent heuristics)   (Welford Z-scores)        (Decision Tree / Random Forest)
              │                          │                            │
        rule_score (0-100)       baseline_score (0-100)        ml_score (0-100)
              └──────────────────────────┼───────────────────────────┘
                                         ▼
                                   HybridEngine.evaluate
                       weighted fusion + corroboration boost
                                         ▼
        DetectionResult { risk_score, severity, confidence, reasons, components }
                                         ▼
                        threshold + allow/block + learning mode
                                         ▼
                              Alert (persisted + notified)
```

## 3. Feature set

`features.FEATURE_NAMES` (stable, append-only) — 14 interpretable features:
`cpu_percent, memory_percent, memory_mb, num_threads, num_connections,
num_remote_endpoints, lifetime_minutes, is_unsigned, in_suspicious_dir,
is_startup_persistent, log_memory_mb, log_threads, conn_per_minute,
cmdline_length`.

## 4. Scoring formula

**Rule score.** Each rule that fires contributes `points`. The raw sum is
squashed so no single rule saturates the score and corroborating weak signals
still accumulate:

```
rule_score = 100 * (1 - exp(-raw_points / 40))
```

**Baseline score.** Using per-executable Welford statistics, the Z-score of each
metric is `z = (x - mean) / max(std, 0.05*|mean|, 1)`, clamped to ±12. The
baseline sub-score ramps with deviation intensity and breadth:

```
baseline_score = 100 * (0.7 * intensity + 0.3 * breadth)     (0 below |Z|=3)
intensity = clamp((max|Z| - 3) / 7, 0, 1)
breadth   = clamp(#deviating_metrics / 4, 0, 1)
```

**ML score.** `ml_score = P(suspicious) * 100` from the classifier.

**Fusion.** The ML weight `w_ml` comes from the active sensitivity profile; the
remainder is split rules (0.65) / baseline (0.35). Weights of unavailable
components (no trained model, immature baseline) are redistributed, then
renormalised:

```
risk = w_ml*ml_score + w_rules*rule_score + w_base*baseline_score
if (#strong detectors >= 2): risk += 6 * (#strong - 1)     # corroboration
risk = clamp(risk, 0, 100)
severity = f(risk):  >=85 Critical, >=65 High, >=45 Medium, >=25 Low, else Info
```

**Decision.** Alert when `risk >= profile.alert_threshold`, unless the process is
allowlisted (suppressed) — blocklisted processes always alert at 100. During
**learning mode** only strong rule signals (rule_score ≥ 60) alert.

| Profile | Threshold | ML weight |
|---|---|---|
| Low | 75 | 0.35 |
| Balanced | 60 | 0.45 |
| Strict | 45 | 0.55 |
| Research | 30 | 0.50 |

## 5. ML workflow

1. Collect labelled samples locally (user labels, simulation bootstrap, or
   imported) → `labelled_samples` table.
2. `MLClassifier.train` does a stratified train/test split, fits a
   `DecisionTreeClassifier` (depth-limited, transparent) or
   `RandomForestClassifier` (default), and records accuracy/precision/recall/F1
   in `ModelMetadata`.
3. Models persist to `%LOCALAPPDATA%\ProcAI\models\<name>.joblib` with metadata.
4. `predict` returns `P(suspicious)`, a confidence (`|p-0.5|*2`) and the top
   feature importances for explanation.

All training and inference happen **locally**.

## 6. Database schema (SQLite)

`meta`, `settings`, `process_history`, `alerts`, `baselines` (Welford
`count/mean/m2/min/max` per identity+metric), `model_metadata`,
`reputation_list` (allow/block), `labelled_samples`. Full DDL in
`src/procai/data/schema.sql`. WAL mode; retention pruning by age.

## 7. Threading model

- **Monitor thread** (`core/monitor.py`): daemon loop calling `engine.scan_once`
  every `scan_interval` seconds; responsive stop via small sleep slices.
- **GUI thread**: alerts raised on the monitor thread are pushed to a
  `queue.Queue` and drained by the Tk main loop (`_poll_alerts`) — Tk widgets are
  only ever touched from the main thread.
- **SQLite**: opened `check_same_thread=False` and guarded by a re-entrant lock.
- **Long GUI actions** (training, deep scan, AI chat) run on worker threads and
  marshal results back with `after(0, ...)`.

## 8. Safety invariants

- Read-only observation of OS-exposed data; no injection, no hooking, no hiding.
- Simulation uses **negative PIDs** so synthetic data can never be confused with
  or act upon real processes.
- Process termination (a GUI action, not automatic) requires explicit typed
  confirmation and is audit-logged.
- The AI assistant is off by default; privacy-first mode blocks all cloud calls.
