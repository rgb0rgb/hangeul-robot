"""시험 공용 준비물."""
from __future__ import annotations

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    """실제 자산을 건드리지 않는 콘솔 한 대."""
    from fastapi.testclient import TestClient
    from hangeul_console import app as app_mod
    from hangeul_console.device_lease import LeaseBook

    monkeypatch.setattr(app_mod, "INSTANCE_DIR", tmp_path / "instances")
    monkeypatch.setattr(app_mod, "CONSOLE_STATE", tmp_path / "console.json")
    monkeypatch.setattr(app_mod, "TASK_PATH", tmp_path / "tasks.json")
    monkeypatch.setattr(app_mod, "leases", LeaseBook(tmp_path / "leases"))
    return TestClient(app_mod.app)
