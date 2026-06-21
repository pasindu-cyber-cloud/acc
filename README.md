# ProcAI — AI-Powered Suspicious Process Detection

ProcAI is a **defensive, transparent, user-consented** Windows endpoint-security
tool. It continuously monitors running processes, learns what *normal* looks like
on your machine, and uses a **hybrid detection engine** — transparent rules,
statistical (Z-score) deviation, and machine learning — to flag suspicious
behaviour *after execution has begun*, when signature-based tools may miss it.

> **Defensive by design.** ProcAI never hides itself, never disables Windows
> Defender, never modifies security settings without explicit user action, and
> never sends your data anywhere unless you explicitly opt in. It is intended for
> education, research, and as a university dissertation / portfolio project.

---

## Highlights

- **Hybrid anomaly engine** — fuses rule-based scoring, baseline Z-score
  deviation and ML probability into a single 0–100 risk score with severity,
  confidence and a transparent breakdown.
- **Explainable AI (Proc Assistant)** — every verdict comes with a plain-English
  explanation, evidence and a guided investigation checklist (offline by
  default; optional local Ollama or cloud Gemini chat).
- **Modern dashboard** — sidebar UI with Overview, Live Processes, Alerts,
  Process Intelligence, Deep Scan, Forensic Timeline, Proc Assistant, Reports,
  Settings and Protection Health.
- **Real product behaviour** — background monitoring service, system-tray icon,
  desktop notifications, Windows startup option, installer + uninstaller.
- **Privacy-first & auditable** — local SQLite storage, a tamper-evident
  hash-chained audit log, sensitivity profiles, allow/block lists, learning mode
  and a harmless simulation mode for testing the pipeline without malware.

## Architecture at a glance

```
telemetry (psutil)  ->  features  ->  ┌─ rule engine ─────┐
                                      ├─ baseline Z-score ─┤ -> hybrid engine -> alert
                                      └─ ML (DT / RF) ─────┘        |
                                                            SQLite + audit log
                                                                    |
                          GUI (CustomTkinter)  /  tray + background service
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design,
data-flow, database schema and scoring formula.

## Project layout

```
src/procai/
  config.py            paths, settings, sensitivity profiles
  core/
    telemetry.py       psutil process collection
    reputation.py      signing / suspicious path / startup checks
    features.py        snapshot -> feature vector
    baseline.py        Welford running stats + Z-score deviation
    rules.py           transparent rule engine
    ml.py              Decision Tree / Random Forest
    hybrid.py          fusion -> risk, severity, alert decision
    engine.py          orchestration facade
    monitor.py         background scan loop
    simulation.py      harmless synthetic abnormal data
  data/                SQLite schema + database layer
  assistant/           offline explainer + optional AI backends
  reports/             CSV / PDF export
  service/             tray, notifications, background service, autostart
  gui/                 CustomTkinter dashboard (10 pages)
installer/             PyInstaller spec + Inno Setup + build script
docs/                  architecture, user manual, testing, privacy, installer
tests/                 unit + integration tests (stdlib-only runnable)
```

## Install & run (development)

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -e .[all]          # core + ml + gui + reports + ai
python -m procai               # launch the dashboard
python -m procai --service --tray   # run headless background service + tray
```

Optional dependency groups: `procai[ml]`, `procai[gui]`, `procai[reports]`,
`procai[ai]`. The **core detection engine** only needs `psutil`; everything else
degrades gracefully when not installed.

## Build a Windows installer

```bat
pip install -r requirements-dev.txt
python installer\build.py --installer
```

Produces `dist\ProcAI\ProcAI.exe` and an Inno Setup `ProcAI-Setup-2.0.0.exe`.
See [`docs/INSTALLER.md`](docs/INSTALLER.md), including the honest position on
Windows Security Center integration and code signing.

## Testing

```bash
pytest                  # 34 tests; core logic runs without psutil/sklearn/ctk
```

See [`docs/TESTING.md`](docs/TESTING.md) for the full test plan.

## Responsible use

ProcAI is **defensive security software**. Do not use it to build anything
stealthy, evasive, or designed to bypass security controls. Keep Windows
Defender enabled; ProcAI complements, and never replaces or impersonates, it.

## License

MIT — see [`LICENSE`](LICENSE).
