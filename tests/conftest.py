"""시험 공용 준비물."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

# 시험이 쓰는 로봇 구성. **사람이 등록한 install/robots/를 쓰지 않는다** —
# 그 디렉터리는 .gitignore 대상이라 사람마다 다르다.
FIXTURE_ROBOTS = Path(__file__).resolve().parent / "fixtures" / "robots"


def install_fixture_robots(monkeypatch, tmp_path):
    """시험용 로봇 구성을 tmp에 펼치고 콘솔이 그쪽만 보게 한다."""
    from hangeul_console import app as app_mod
    from hangeul_console.registry import Registry

    robots = tmp_path / "robots"
    robots.mkdir(parents=True, exist_ok=True)
    for path in FIXTURE_ROBOTS.glob("*.json"):
        shutil.copy2(path, robots / path.name)
    monkeypatch.setattr(app_mod, "ROBOT_CONFIG_DIR", robots)
    monkeypatch.setattr(app_mod, "registry", Registry(app_mod.MODULE_DIR, robots))
    return robots


def isolate_console_state(monkeypatch, tmp_path):
    """사람의 화면 상태·작업·장치 임대를 건드리지 않는다."""
    from hangeul_console import app as app_mod
    from hangeul_console.device_lease import LeaseBook

    monkeypatch.setattr(app_mod, "INSTANCE_DIR", tmp_path / "instances")
    monkeypatch.setattr(app_mod, "CONSOLE_STATE", tmp_path / "console.json")
    monkeypatch.setattr(app_mod, "TASK_PATH", tmp_path / "tasks.json")
    monkeypatch.setattr(app_mod, "leases", LeaseBook(tmp_path / "leases"))


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


# 사람이 실제로 띄우는 콘솔·런타임이 쓰는 자리(화면 8099, 로봇 8601~, 설치본 시험 8199 등).
REAL_SERVICE_PORTS = range(8000, 9000)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def _is_real_service(url: str) -> bool:
    import urllib.parse
    try:
        parts = urllib.parse.urlsplit(url)
        return (parts.scheme in ("http", "https") and (parts.hostname or "") in LOOPBACK_HOSTS
                and parts.port in REAL_SERVICE_PORTS)
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def never_send_to_real_robots(monkeypatch):
    """**시험은 실제로 떠 있는 로봇에 아무것도 보내지 않는다.**

    시험용 로봇 구성(fixtures/robots/young_omx.json)의 주소가 실제 로봇1의 주소
    (127.0.0.1:8601)와 같다. 그래서 `/api/estop`을 부르는 시험이 **떠 있던 실제
    로봇1에 긴급 정지를 걸었고**, 화면이 그것을 보고 돌던 FR5 반복을 멈췄다. 정지
    해제를 부르는 시험은 운영자가 건 진짜 정지를 풀 수도 있었다(2026-11-10).

    시험이 직접 띄우는 서버는 빈 자리(0번 → 임시 포트)를 쓰므로 막히지 않는다.
    막힌 요청은 런타임이 꺼져 있을 때와 같은 URLError가 된다 — 시험 결과가
    실제 로봇이 떠 있는지에 따라 달라지지 않는다.
    """
    import urllib.error
    import urllib.request

    real_urlopen = urllib.request.urlopen

    def guarded(url, *args, **kwargs):
        target = url.full_url if isinstance(url, urllib.request.Request) else str(url)
        if _is_real_service(target):
            raise urllib.error.URLError(f"시험 중에는 실제 서비스로 보내지 않습니다: {target}")
        return real_urlopen(url, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", guarded)


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
    # 로봇 추가 시험이 실제 런타임을 띄우지 않게 한다(콘솔의 _ensure_runtimes).
    monkeypatch.setenv("HANGEUL_NO_AUTOSTART", "1")
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
