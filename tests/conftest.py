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


@pytest.fixture(autouse=True)
def never_touch_real_robot_data(tmp_path_factory, monkeypatch):
    """**시험은 운영자의 실제 파일에 쓰지 않는다.**

    런타임의 `build()`는 경로를 안 주면 저장소의 `data/`에 묶인다. 시험이
    거기에 묶인 채 `latch_estop("시험")`을 부르면 **운영자의 정지 래치 파일에
    '시험'이라고 적힌다.** 실제로 그랬다(2026-09-24 전수조사:
    `data/safety_state_arm_omx.json`에 `estop_latched: true, 사유 "시험"`).
    그 상태로 런타임을 켜면 정지가 걸린 채로 뜬다.

    주행거리계도 같다 — 시험이 민 거리가 실제 로봇의 이력에 더해지면
    정비 주기가 틀어진다.
    """
    try:
        from hangeul_runtime import server
    except Exception:                              # noqa: BLE001
        return

    sandbox = tmp_path_factory.mktemp("runtime_data")
    real_build = server.build

    def build(module_id, device, limits_path="", **kw):
        kw.setdefault("state_path", str(sandbox / f"safety_state_{module_id}.json"))
        kw.setdefault("usage_path", str(sandbox / f"usage_{module_id}.json"))
        return real_build(module_id, device, limits_path, **kw)

    monkeypatch.setattr(server, "build", build)
