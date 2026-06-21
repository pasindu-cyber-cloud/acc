# ProcAI (.NET) User Manual

## First launch
A consent & transparency screen explains exactly what ProcAI reads and the
guarantees it makes. Monitoring begins only after you accept.

## The dashboard
A Fluent sidebar (NavigationView) gives access to ten pages. A protection
**Start/Stop** button and live status sit at the bottom of the sidebar.

### Overview
Protection status, processes scanned, suspicious detections (24h), model status,
system memory, learning-mode progress, baselines learned, and recent alerts.

### Live Processes
A searchable, sortable grid of the latest scan: PID, name, user, CPU, memory,
threads, connections, risk, severity, signed status and executable path.
**Refresh** re-scans now; **Simulate** injects harmless synthetic abnormal
processes (negative PIDs) so you can see detection end-to-end.

### Alerts
Severity-filtered alert history with a detail panel. **Acknowledge** an alert or
**Add to allowlist** to suppress future alerts for that program.

### Process Intelligence
Enter a PID and **Inspect** to get a full explainable breakdown plus a
prioritised investigation checklist.

### Deep Scan
Runs a full scan and groups noteworthy findings: unsigned/suspicious-location
executables, unusual parent-child chains, high-resource processes, heavy network
activity, and startup-persistent items.

### Forensic Timeline
A chronological view of alerts and notable process events over the last hour,
24 hours or 7 days.

### Proc Assistant
Plain-language help. Offline by default (deterministic, no network): explain the
latest alert, ask about "status", or type a PID. Optional AI chat uses a **local
Ollama** model (private) or **Gemini** (cloud; blocked while privacy-first mode
is on) once enabled in Settings.

### Reports
Export alerts to **CSV** or **PDF**, and process history to CSV. Files are saved
locally; use **Open reports folder** to reveal them.

### Settings
Sensitivity profile (Low/Balanced/Strict/Research), scan interval, learning mode,
start-with-Windows, minimise-to-tray, ML toggle + model choice, **Train model on
synthetic data**, notifications, privacy-first mode, AI assistant + backend,
allow/block lists, and data retention.

### Protection Health
A transparent status board for ProcAI itself (monitoring, model, baseline,
notifications, learning, **audit-log integrity**, privacy mode). It states clearly
that ProcAI is independent and that you should keep Windows Defender enabled.

## Sensitivity profiles
| Profile | Behaviour |
|---|---|
| Low | Fewest alerts; only strong, corroborated signals |
| Balanced | Recommended default |
| Strict | More sensitive; good for high-value machines |
| Research | Most verbose; surfaces the whole pipeline for testing/teaching |

## Learning mode
For an initial window (default 30 min) ProcAI observes normal activity to build
baselines, holding back deviation-driven alerts (only strong rule signals alert),
then becomes stricter automatically.

## Terminating a process
ProcAI never terminates processes automatically — any termination is a manual,
confirmed, audited action.

## Where your data lives
`%LOCALAPPDATA%\ProcAI` (database, settings, models, reports, logs including the
tamper-evident `audit.log`). Nothing leaves your machine unless you explicitly
enable the cloud AI backend.
