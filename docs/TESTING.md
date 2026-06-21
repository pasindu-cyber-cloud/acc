# ProcAI Testing Plan

ProcAI's detection core is intentionally pure-Python so it can be unit-tested
without `psutil`, `scikit-learn` or `customtkinter`. Optional layers degrade
gracefully and are verified by import/guard tests.

## Running the tests

```bash
pip install -r requirements-dev.txt   # or just: pip install pytest
pytest
```

Current suite: **34 tests, all passing**, runtime < 1s.

## Test inventory

| File | Focus |
|---|---|
| `tests/test_features.py` | Feature keys/order, unsigned/unknown handling, derived values |
| `tests/test_rules.py` | Each rule fires correctly; benign = 0; score bounded; lineage severity |
| `tests/test_baseline.py` | Welford vs `statistics`; Z-score clamping; maturity gating; persistence |
| `tests/test_hybrid.py` | Fusion, blocklist=critical, allowlist suppression, profile sensitivity, components |
| `tests/test_database.py` | Settings, alerts (filter/ack/counts), reputation lists, history batch + prune, labelled samples |
| `tests/test_audit.py` | Hash-chained log records, links, and tamper detection |
| `tests/test_simulation_and_engine.py` | Synthetic PIDs are negative; end-to-end pipeline; balanced training data; health |

## What the tests guarantee

- **Correct statistics** — running mean/variance match `statistics.stdev`.
- **Stable scoring** — risk scores stay within 0–100 even for pathological inputs.
- **Transparent decisions** — rule hits, components and reasons are populated.
- **Safe simulation** — synthetic data can never reference a real process (PIDs < 0).
- **Integrity** — any edit/deletion in the audit log is detected by `verify()`.
- **Graceful degradation** — engine/health work with no optional dependencies.

## Manual / on-Windows test checklist

These require a real Windows host with optional deps installed:

1. **Live telemetry** — `python -m procai`, confirm Live Processes populates with
   real PIDs, CPU values become non-zero from the second scan.
2. **Signing/reputation** — verify signed Microsoft binaries show *Signed* and an
   unsigned binary in `%TEMP%` is flagged.
3. **ML** — Settings → *Train model on synthetic data*; confirm metrics appear and
   Protection Health shows the model loaded.
4. **Alerts & notifications** — use *Simulate* / Deep Scan on simulation data and
   confirm alerts, toasts and desktop notifications at the chosen severity.
5. **Tray & background** — close to tray, reopen from the icon; run
   `--service --tray`; stop via `procai --stop`.
6. **Reports** — export CSV and PDF; open the reports folder.
7. **Installer** — build with `installer\build.py --installer`; install, verify
   shortcuts and the optional (visible) startup entry; uninstall and confirm the
   keep/delete-data prompt.
8. **Privacy** — confirm the AI assistant is off by default and that Gemini is
   refused while privacy-first mode is on.

## Continuous integration (suggested)

Run `ruff`, `black --check`, `mypy src/procai`, then `pytest` on Windows and
Linux runners. The Linux run validates the dependency-light core; the Windows run
additionally exercises psutil-backed telemetry.
