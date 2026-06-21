# ProcAI (.NET) Architecture

A native Windows reimplementation of ProcAI in C#/.NET 8, mirroring the Python
prototype's detection design with native performance and a Fluent WPF UI.

## Projects

| Project | Responsibility |
|---|---|
| **ProcAI.Core** | Detection engine, telemetry, reputation, ML, data, audit, orchestration |
| **ProcAI.App** | WPF + WPF-UI Fluent dashboard (10 pages) |
| **ProcAI.Service** | Headless Windows Service host (`BackgroundService`) |
| **ProcAI.Tests** | xUnit unit/integration tests |

## Detection pipeline (same as the Python version)

```
TelemetryCollector ──► ReputationService ──► FeatureExtractor
                                                   │
                 ┌─────────────────────────────────┼─────────────────────────┐
                 ▼                                  ▼                         ▼
            RuleEngine                       BaselineManager             MlClassifier
       (transparent heuristics)          (Welford + clamped Z)      (FastForest / FastTree)
                 └─────────────────────────────────┼─────────────────────────┘
                                                    ▼
                                              HybridEngine
                              weighted fusion + corroboration + allow/block
                                                    ▼
                         DetectionResult { risk, severity, confidence, reasons }
                                                    ▼
                               ProcAIEngine ──► Database + AuditLog ──► AlertRaised
```

## Namespace map (Python → C#)

| Python module | C# location |
|---|---|
| `core/telemetry.py` | `ProcAI.Core.Telemetry.TelemetryCollector` (+ `NativeMethods`) |
| `core/reputation.py` | `ProcAI.Core.Reputation.ReputationService` (+ `NativeAuthenticode`) |
| `core/features.py` | `ProcAI.Core.Detection.FeatureExtractor` |
| `core/baseline.py` | `ProcAI.Core.Detection.BaselineManager`, `RunningStat` |
| `core/rules.py` | `ProcAI.Core.Detection.RuleEngine` |
| `core/ml.py` | `ProcAI.Core.Ml.MlClassifier` |
| `core/hybrid.py` | `ProcAI.Core.Detection.HybridEngine`, `HybridConfig` |
| `core/engine.py` | `ProcAI.Core.Engine.ProcAIEngine` |
| `core/monitor.py` | `ProcAI.Core.Engine.ProcessMonitor` |
| `core/simulation.py` | `ProcAI.Core.Detection.Simulation` |
| `data/database.py` | `ProcAI.Core.Data.Database` |
| `utils/audit.py` | `ProcAI.Core.Utils.AuditLog` |
| `assistant/explain.py` | `ProcAI.Core.Assistant.Explainer` |
| `assistant/ai_backends.py` | `ProcAI.Core.Assistant.AiBackends` |
| `reports/exporter.py` | `ProcAI.Core.Reports.ReportExporter` (QuestPDF) |
| `service/background.py` | `ProcAI.Service` (`MonitorWorker`) |
| `gui/` (CustomTkinter) | `ProcAI.App` (WPF + WPF-UI) |

## Why native is faster/smoother

- Compiled IL + JIT, true multithreading (no GIL): the scan loop runs on a
  background `Task` and never blocks the UI.
- Per-process network via a single IP Helper call; CPU via processor-time deltas.
- ML.NET runs in-process (no Python interop).
- WPF renders on the GPU; the Fluent (Mica) chrome is native.

## Scoring formula

Identical to the Python design: rule points are squashed
`100 * (1 - exp(-raw/40))`; baseline Z-scores are floored/clamped to ±12; the
hybrid risk is a weighted sum (ML weight from the sensitivity profile, remainder
split rules/baseline) with a corroboration bonus when ≥2 detectors agree. See
the Python `docs/ARCHITECTURE.md` for the full derivation.

## Safety invariants

Read-only observation; negative-PID simulation data; manual+confirmed process
termination only; AI off by default and cloud blocked under privacy-first mode;
tamper-evident audit log; honest Protection Health page (no Defender spoofing).
