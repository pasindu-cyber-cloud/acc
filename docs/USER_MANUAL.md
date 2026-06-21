# ProcAI User Manual

## First launch

On first run ProcAI shows a **consent & transparency** dialog explaining exactly
what it reads and the guarantees it makes. Monitoring begins only after you
accept. You can decline and exit at any time.

## The dashboard

A sidebar gives access to ten pages. The **Start/Stop Protection** button and a
live status chip are always visible.

### Overview
At-a-glance protection status, processes scanned, suspicious detections in the
last 24h, model confidence, system CPU/memory, learning-mode progress, and the
most recent alerts.

### Live Processes
A sortable, searchable table of every process from the latest scan: PID, name,
user, CPU, memory, threads, connections, risk score, severity, signed status and
executable path. Click any column header to sort; type in the search box to
filter. **Double-click** a row to open it in Process Intelligence. *Refresh*
re-scans now; *Simulate* injects harmless synthetic abnormal processes.

### Alerts
Severity-coloured alert history with a detail panel. Filter by severity or show
only unacknowledged. Select an alert to read its full reasoning, then
**Acknowledge** it or **Add to allowlist** (which suppresses future alerts for
that program).

### Process Intelligence
Enter a PID (or arrive by double-clicking a process) to see a full explainable
breakdown: behaviour summary, parent process, code-signature, the rules that
fired with their points, the ML classification and most-influential features,
baseline deviation, the score breakdown, and a prioritised investigation guide.

### Deep Scan
Runs a full scan and groups noteworthy findings: unsigned / suspicious-location
executables, unusual parent-child chains, high-resource processes, heavy network
activity and startup-persistent items. Each finding can be opened for inspection.

### Forensic Timeline
A chronological view of alerts and notable process events over the last hour,
24 hours or 7 days.

### Proc Assistant
Plain-language help. In **offline mode** (default) it deterministically explains
the latest alert, your protection status, or any PID you type — with no network
access. If you enable AI chat in Settings, it can also use a **local Ollama**
model (recommended, private) or **Gemini** (cloud; blocked while privacy-first
mode is on).

### Reports
Export alerts to **CSV** or **PDF** (PDF requires `procai[reports]`) and process
history to CSV. Reports are written locally to your reports folder, which you can
open from here.

### Settings
- **Monitoring**: sensitivity profile (Low / Balanced / Strict / Research), scan
  interval, learning mode, start-with-Windows, minimise-to-tray.
- **Detection & ML**: enable/disable ML, choose Decision Tree or Random Forest,
  train a model on synthetic data with one click.
- **Notifications**: toggle desktop notifications and the minimum severity.
- **Privacy & AI**: privacy-first mode, enable AI assistant, backend selection,
  Ollama host/model, Gemini API key.
- **Allowlist / blocklist**: trusted programs (alerts suppressed) and always-alert
  programs.
- **Retention**: how long to keep process history and alerts.

### Protection Health
A transparent status board for ProcAI itself: monitoring service, telemetry,
ML model, baseline engine, notifications, tray/background mode, learning progress
and **audit-log integrity**. It clearly states ProcAI is independent software and
that you should keep Windows Defender enabled.

## Sensitivity profiles

| Profile | Behaviour |
|---|---|
| **Low** | Fewest alerts; only strong, corroborated signals. |
| **Balanced** | Recommended default. |
| **Strict** | More sensitive; good for high-value machines. |
| **Research** | Most verbose; surfaces the whole pipeline for testing/teaching. |

## Learning mode

When enabled, ProcAI spends an initial window (default 30 min) observing normal
activity to build baselines. During this time it holds back deviation-driven
alerts (only strong rule signals alert), then becomes stricter automatically.

## Simulation mode

From Live Processes (*Simulate*) or Deep Scan (*Run on simulation data*) you can
generate harmless synthetic abnormal processes to exercise the detection
pipeline. These never run, never touch real processes, and use negative PIDs.

## Background & tray

Closing the window (with *minimise to tray* on) keeps protection running and
shows a tray icon — right-click it to open the dashboard, pause, or quit. You can
also run headless: `python -m procai --service --tray`.

## Terminating a process

ProcAI never terminates processes automatically. Any termination is a manual
action requiring typed confirmation and is recorded in the audit log.

## Where your data lives

`%LOCALAPPDATA%\ProcAI` — database (`procai.db`), `settings.json`, `models\`,
`reports\`, `logs\` (including the tamper-evident `audit.log`). Nothing leaves
your machine unless you explicitly enable the cloud AI backend.
