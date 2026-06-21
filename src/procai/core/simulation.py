"""Simulation mode: synthetic, harmless abnormal process behaviour.

This lets a user (or an examiner) exercise the full detection pipeline -- rules,
baseline deviation, ML and the hybrid engine -- WITHOUT running real malware.

Every snapshot produced here is *fabricated data only*: no process is created,
launched, modified or terminated. The PIDs are negative sentinels so they can
never collide with, or be mistaken for, real OS processes, and the names are
clearly labelled. This is purely a data generator for testing and demos.
"""

from __future__ import annotations

import random
import time
from typing import Iterable

from .models import ProcessSnapshot

# Negative PIDs guarantee these can never match a real process.
_SIM_PID_BASE = -1000


def _benign_processes() -> list[ProcessSnapshot]:
    """A handful of normal-looking processes for contrast."""
    now = time.time()
    return [
        ProcessSnapshot(
            pid=_SIM_PID_BASE - 1, name="sim_explorer.exe",
            exe_path=r"C:\Windows\explorer.exe", username="DEMO\\user",
            cpu_percent=1.2, memory_rss=120 * 1024 * 1024, memory_percent=1.5,
            num_threads=42, num_connections=2, num_remote_endpoints=1,
            ppid=_SIM_PID_BASE, parent_name="sim_winlogon.exe",
            create_time=now - 36000, is_signed=True, signer="Microsoft Windows",
        ),
        ProcessSnapshot(
            pid=_SIM_PID_BASE - 2, name="sim_browser.exe",
            exe_path=r"C:\Program Files\Browser\browser.exe", username="DEMO\\user",
            cpu_percent=8.0, memory_rss=512 * 1024 * 1024, memory_percent=6.0,
            num_threads=70, num_connections=14, num_remote_endpoints=9,
            ppid=_SIM_PID_BASE - 1, parent_name="sim_explorer.exe",
            create_time=now - 7200, is_signed=True, signer="Example Browser Inc",
        ),
    ]


# Named abnormal scenarios -> the indicator(s) each is designed to trigger.
SCENARIOS: dict[str, str] = {
    "cpu_spike": "Sustained very high CPU with low memory (crypto-miner-like profile).",
    "memory_balloon": "Rapidly growing memory footprint (leak / staging-like profile).",
    "thread_storm": "Abnormally high thread count.",
    "beacon_network": "Many short-lived outbound connections (beacon-like profile).",
    "temp_unsigned": "Unsigned executable running from a Temp/Downloads directory.",
    "orphan_lineage": "Unusual parent-child lineage (e.g. office app spawning a shell).",
    "short_lived_burst": "Very new process consuming heavy resources immediately.",
}


def _abnormal_process(scenario: str, idx: int) -> ProcessSnapshot:
    now = time.time()
    pid = _SIM_PID_BASE - 100 - idx
    base = ProcessSnapshot(
        pid=pid, name=f"sim_{scenario}.exe", username="DEMO\\user",
        exe_path=rf"C:\Program Files\Demo\sim_{scenario}.exe",
        ppid=_SIM_PID_BASE - 1, parent_name="sim_explorer.exe",
        create_time=now - 1800, is_signed=True, signer="Demo Signed Vendor",
        cpu_percent=2.0, memory_rss=80 * 1024 * 1024, memory_percent=1.0,
        num_threads=12, num_connections=1, num_remote_endpoints=1,
    )
    if scenario == "cpu_spike":
        base.cpu_percent = random.uniform(88, 99)
        base.num_threads = random.randint(8, 16)
    elif scenario == "memory_balloon":
        base.memory_rss = random.randint(2200, 4000) * 1024 * 1024
        base.memory_percent = random.uniform(35, 70)
    elif scenario == "thread_storm":
        base.num_threads = random.randint(400, 1200)
    elif scenario == "beacon_network":
        base.num_connections = random.randint(60, 200)
        base.num_remote_endpoints = random.randint(40, 150)
    elif scenario == "temp_unsigned":
        base.exe_path = r"C:\Users\user\AppData\Local\Temp\sim_temp_unsigned.exe"
        base.is_signed = False
        base.signer = ""
        base.in_suspicious_dir = True
    elif scenario == "orphan_lineage":
        # Use real, matchable names so the lineage rule fires. The negative PID
        # still guarantees this is recognisably synthetic, not a real process.
        base.name = "cmd.exe"
        base.exe_path = r"C:\Windows\System32\cmd.exe"
        base.parent_name = "winword.exe"
        base.ppid = _SIM_PID_BASE - 50
    elif scenario == "short_lived_burst":
        base.create_time = now - 3  # 3 seconds old
        base.cpu_percent = random.uniform(70, 95)
        base.memory_rss = random.randint(900, 1600) * 1024 * 1024
    return base


def generate(
    scenarios: Iterable[str] | None = None,
    include_benign: bool = True,
) -> list[ProcessSnapshot]:
    """Generate a batch of synthetic snapshots.

    Parameters
    ----------
    scenarios:
        Which abnormal scenarios to include. ``None`` -> all known scenarios.
    include_benign:
        Whether to mix in a couple of normal-looking processes.
    """
    chosen = list(scenarios) if scenarios is not None else list(SCENARIOS)
    out: list[ProcessSnapshot] = []
    if include_benign:
        out.extend(_benign_processes())
    for i, name in enumerate(chosen):
        if name in SCENARIOS:
            out.append(_abnormal_process(name, i))
    return out


def generate_training_data(n_normal: int = 400, n_suspicious: int = 200) -> list[tuple[dict, int]]:
    """Generate a synthetic labelled dataset for ML bootstrap/testing.

    Returns a list of ``(feature_dict, label)`` where label 0 = normal,
    1 = suspicious. Feature keys match :func:`procai.core.features.extract`.
    """
    from .features import extract  # local import to avoid cycle

    rng = random.Random(1337)
    rows: list[tuple[dict, int]] = []

    for _ in range(n_normal):
        snap = ProcessSnapshot(
            pid=1, name="normal.exe", exe_path=r"C:\Program Files\App\normal.exe",
            cpu_percent=rng.uniform(0, 12), memory_percent=rng.uniform(0, 8),
            memory_rss=int(rng.uniform(10, 400) * 1024 * 1024),
            num_threads=rng.randint(2, 60), num_connections=rng.randint(0, 8),
            num_remote_endpoints=rng.randint(0, 5),
            create_time=time.time() - rng.uniform(300, 200000),
            is_signed=True, in_suspicious_dir=False,
        )
        rows.append((extract(snap), 0))

    for _ in range(n_suspicious):
        snap = ProcessSnapshot(
            pid=2, name="susp.exe",
            exe_path=r"C:\Users\u\AppData\Local\Temp\susp.exe",
            cpu_percent=rng.uniform(60, 100), memory_percent=rng.uniform(20, 80),
            memory_rss=int(rng.uniform(800, 4000) * 1024 * 1024),
            num_threads=rng.randint(150, 1000), num_connections=rng.randint(30, 200),
            num_remote_endpoints=rng.randint(20, 150),
            create_time=time.time() - rng.uniform(1, 120),
            is_signed=rng.random() < 0.2, in_suspicious_dir=rng.random() < 0.8,
        )
        rows.append((extract(snap), 1))

    rng.shuffle(rows)
    return rows
