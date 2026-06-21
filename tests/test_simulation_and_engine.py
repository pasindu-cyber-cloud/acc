"""Integration tests: simulation pipeline through the engine (no psutil/sklearn)."""

from __future__ import annotations

from procai.config import SensitivityProfile, Settings
from procai.core import simulation
from procai.core.engine import ProcAIEngine
from procai.core.models import Severity


def _engine(tmp_path):
    from procai.data import Database

    s = Settings(sensitivity=SensitivityProfile.STRICT, enable_ml=False,
                 learning_mode=False)
    return ProcAIEngine(settings=s, db=Database(tmp_path / "engine.db"))


def test_simulation_pids_are_synthetic():
    for snap in simulation.generate():
        assert snap.pid < 0, "Simulation PIDs must be negative sentinels (never real)."


def test_pipeline_flags_abnormal(tmp_path):
    eng = _engine(tmp_path)
    raised = []
    eng.add_alert_callback(lambda a, r: raised.append(a))
    results = eng.scan_once(simulation.generate(), enrich_reputation=False)
    assert len(results) == len(simulation.generate())
    # The clearly abnormal temp+unsigned scenario should reach at least MEDIUM.
    temp = next(r for r in results if r.snapshot.name == "sim_temp_unsigned.exe")
    assert temp.severity >= Severity.MEDIUM
    # Benign processes should not alert.
    benign = next(r for r in results if r.snapshot.name == "sim_explorer.exe")
    assert benign.should_alert is False
    eng.close()


def test_training_data_balanced():
    data = simulation.generate_training_data(100, 60)
    labels = [lbl for _f, lbl in data]
    assert labels.count(0) == 100 and labels.count(1) == 60


def test_health_reports_without_optional_deps(tmp_path):
    eng = _engine(tmp_path)
    h = eng.health()
    assert "psutil_available" in h
    assert h["audit_ok"] in (True, False)
    eng.close()
