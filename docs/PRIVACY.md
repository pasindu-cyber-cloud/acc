# ProcAI Privacy & Safety Statement

ProcAI is defensive security software built to be **transparent, local-first and
user-consented**. This document states plainly what it does and does not do.

## Data collection & storage

- ProcAI reads process information the operating system already exposes to your
  account: process names, resource usage, network-connection counts, executable
  paths and parent-child relationships.
- All data is stored **locally** in `%LOCALAPPDATA%\ProcAI` (SQLite database,
  settings, models, reports, logs). Nothing is uploaded by default.
- Retention is configurable; old process history and acknowledged alerts are
  pruned automatically.

## No data leaves your machine — unless you opt in

- The **Proc Assistant runs offline by default**, producing deterministic,
  rule-based explanations with zero network access.
- Optional AI chat is **off by default**. When enabled you choose the backend:
  - **Ollama (local)** — prompts stay on your machine.
  - **Gemini (cloud)** — prompt text is sent to Google's API. This is **blocked**
    while *privacy-first mode* is on; you must explicitly disable privacy-first
    mode to use it.

## What ProcAI will never do

- It will **not** hide itself. A dashboard and tray icon are always available, and
  the background component appears in Task Manager.
- It will **not** disable, weaken or modify Windows Defender or any antivirus.
- It will **not** modify Windows security settings without an explicit, deliberate
  user action.
- It will **not** terminate processes automatically — termination is a manual,
  confirmed, audited action.
- It will **not** impersonate Microsoft, forge signatures, or attempt to bypass
  SmartScreen, UAC or any security control.

## Transparency & integrity

- Every state-changing action (start/stop monitoring, settings changes, enabling
  the AI assistant, exporting reports, terminating a process, changing startup) is
  written to a **tamper-evident, hash-chained audit log** you can read and verify.
- The detection logic is fully explainable: each alert lists the exact rules that
  fired, the ML view, the baseline deviation and the score breakdown.

## Your controls

- Stop monitoring at any time.
- Adjust sensitivity, notifications, retention and lists in Settings.
- Export or delete your data; the uninstaller asks whether to keep or remove it.
- Keep Windows Defender enabled — ProcAI complements it and never replaces it.

## Intended use

ProcAI is for education, research, dissertation/portfolio work and personal
endpoint visibility. It must not be used to build stealthy, evasive or malicious
software.
