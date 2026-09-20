"""로봇 런타임 — 실물에 닿는 유일한 프로세스.

로봇 한 대에 런타임 하나. 다른 로봇이 죽어도 이 프로세스는 영향받지 않는다.

    콘솔 ──HTTP──▶ 런타임 ──시리얼──▶ 로봇
                    │
                    └─ 안전 판정(safety.py) · 장치 잠금 · 기록

콘솔이 고장 나거나 다른 프로그램이 요청해도 이 판정은 지나가야 한다.

**단위는 부품 기술서에서 읽는다.** 화면은 사람이 읽는 도(°)로 범위를 적고,
로봇은 자기 단위(틱·밀리도)로 움직인다. 그 사이를 옮기는 지식은 부품이 들고
다니는 `unit` 항목 하나뿐이다 — 런타임 코드에 로봇 이름별 상수를 두지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException

from . import safety
from .hardware_errors import HardwareConnectionLostError, InFlightSafetyViolationError
from .hardware_port_lock import HardwarePortBusyError, HardwarePortLock

# 시리얼은 한 줄이다. 두 요청이 동시에 말을 걸면 답이 섞여서 돌아온다 —
# J1 자리에 J4의 각도가 실려 오던 것이 이것이다. 화면은 자세를 계속 읽고,
# 그 사이에 사람이 미세 이동을 누르면 두 대화가 겹친다.
SERIAL_LOCK = threading.RLock()

# 같은 값을 짧은 사이에 여러 번 물어보지 않는다. 컨트롤러에 부담을 준다.
READ_CACHE_SEC = 0.25
_read_cache: dict[str, Any] = {"at": 0.0, "value": {}}

# 명령 사이의 최소 간격. 실패한 직후에는 더 벌린다 —
# 안 움직이는 로봇에 쉬지 않고 말을 걸면 컨트롤러가 멎는다.
MIN_GAP_SEC = 0.15
GAP_AFTER_FAILURE_SEC = 2.0
_pacing: dict[str, float] = {"last": 0.0, "gap": MIN_GAP_SEC}

# 되살리기가 두 번 연달아 소용없으면 그만한다. 되살리기는 연결을 다시 여는
# 일이고 그때 컨트롤러가 재부팅되므로, 효과 없는 되살리기를 반복하면 로봇을
# 계속 흔드는 셈이다. 사람이 '정지 해제'를 누르면 다시 시도한다.
AUTO_RECOVER_STRIKES = 2
_recovery: dict[str, int] = {"failed_in_a_row": 0}


# 되먹임 고리(추적)가 쓰는 최소 간격. 사람이 단추를 누르는 것과 성격이 다르다 —
# 화면이 매 프레임 결과를 보고 다음 걸음을 정하므로 스스로 속도를 맞춘다. 실패하면
# 여전히 GAP_AFTER_FAILURE_SEC(2초)로 벌어지고, 따라가기는 한 번 막히면 꺼진다.
CONTROL_LOOP_GAP_SEC = 0.05


def _pace(min_gap: float | None = None) -> None:
    """앞 명령과 너무 붙지 않게 한 박자 쉰다."""
    gap = _pacing["gap"] if min_gap is None else min(_pacing["gap"], min_gap)
    wait = _pacing["last"] + gap - time.monotonic()
    if wait > 0:
        time.sleep(min(wait, GAP_AFTER_FAILURE_SEC))
    _pacing["last"] = time.monotonic()


def _note_result(ok: bool) -> None:
    _pacing["gap"] = MIN_GAP_SEC if ok else GAP_AFTER_FAILURE_SEC
    _pacing["last"] = time.monotonic()


# 접근 키는 없다(2026-08-21). 런타임도 콘솔도 127.0.0.1에만 열리므로 키는
# 같은 컴퓨터 안에서 자기 자신에게 문을 잠그는 일이었다. 사람이 키를 만들고
# 넣어야 하는 단계만 남고 막아주는 것은 없었다. 밖에 열게 되는 날에는 키가
# 아니라 제대로 된 인증을 새로 놓아야 한다.
app = FastAPI(title="Hangeul Robot Runtime")
state = safety.SafetyState()
CONFIG: dict[str, Any] = {
    "module": None,          # 부품 ID
    "device": "",            # 장치 이름
    "descriptor": {},        # 부품 기술서 원본
    "limits": {},            # 관절별 [최소, 최대] — 로봇의 단위로 변환된 것
    "limits_raw": {},        # 화면이 저장한 그대로 (도 단위 · 온도 · 속도)
    "adapter": None,
    "simulate_reason": "",   # 시늉 모드라면 왜 그런지 (빈 값이면 실물에 붙어 있다)
    "modules_dir": None,
    "port_lock": None,
    "file_stamp": None,
    "device_stamp": None,
}

# 부품별 응답 확인. **폴링마다 실물을 두드리지 않는다** — 확인은 버스를
# 쓰는 일이라 움직이는 중에 끼어들면 안 된다. 연결할 때와 복구할 때만
# 새로 보고, 그 사이에는 **언제 본 것인지와 함께** 그대로 올린다.
_ATTEST: dict[str, Any] = {"at": "", "parts": {}, "error": ""}


def _refresh_attestation() -> dict[str, Any]:
    """지금 어떤 부품이 응답하는지 다시 본다. 실패해도 런타임은 계속 산다."""
    adapter = CONFIG.get("adapter")
    if adapter is None:
        _ATTEST.update({"at": datetime.now().isoformat(timespec="seconds"),
                        "parts": {}, "error": "",
                        "reason": CONFIG.get("simulate_reason") or "시늉 모드"})
        return _ATTEST
    try:
        with SERIAL_LOCK:
            parts = adapter.attest_parts()
        _ATTEST.update({"at": datetime.now().isoformat(timespec="seconds"),
                        "parts": parts or {}, "error": "", "reason": ""})
    except Exception as exc:                       # noqa: BLE001
        # 확인에 실패한 것과 부품이 없는 것은 다르다. 섞지 않는다.
        _ATTEST.update({"at": datetime.now().isoformat(timespec="seconds"),
                        "parts": {}, "error": f"{type(exc).__name__}: {exc}",
                        "reason": "부품 확인에 실패했습니다"})
    return _ATTEST


# 화면의 속도 낱말 → 실제 속도. 실물 검증(라운드 473)에서 나온 값이다.
SPEED_TO_VELOCITY = {"slow": 50, "normal": 120, "fast": 200}


def _refresh_files() -> None:
    """부품 기술서와 안전 범위가 바뀌었으면 다시 읽는다.

    **연결은 건드리지 않는다.** 포트를 다시 열면 컨트롤러가 재부팅되므로,
    설정을 고칠 때마다 런타임을 껐다 켜는 것은 로봇을 흔드는 일이다.
    """
    stamp = []
    for path in (_module_path(CONFIG["module"]), _limits_file()):
        try:
            stat = Path(path).stat()
            stamp.append((str(path), stat.st_mtime_ns))
        except OSError:
            stamp.append((str(path), 0))
    if tuple(stamp) == CONFIG.get("file_stamp"):
        return
    CONFIG["file_stamp"] = tuple(stamp)
    try:
        CONFIG["descriptor"] = _load_descriptor(CONFIG["module"])
        CONFIG["hand_joint"] = _load_hand(CONFIG["module"])
        if _limits_file().exists():
            raw = json.loads(_limits_file().read_text(encoding="utf-8"))
            CONFIG["limits_raw"] = raw
            CONFIG["limits"] = _normalize_limits(raw)
        state.note("부품 기술서/안전 범위를 다시 읽었습니다")
    except (OSError, ValueError) as exc:
        state.note(f"설정 다시 읽기 실패: {exc}", "stop")


def _device_stamp() -> tuple | None:
    """장치 파일의 신원. 로봇 전원을 껐다 켜면 이 값이 달라진다."""
    try:
        st = os.stat(CONFIG["device"])
    except OSError:
        return None
    return (st.st_ino, st.st_rdev, st.st_ctime_ns)


def _ensure_link() -> None:
    """장치가 다시 꽂혔으면 연결을 새로 연다.

    로봇 전원을 껐다 켜면 USB 장치가 새로 잡히는데, 옛 연결 손잡이를 계속
    붙잡고 있으면 읽기가 응답 없이 오래 매달린다 — 화면에서는 그냥
    '멈춘 것'으로 보인다. 전원 재기동이 잦은 로봇에서 이게 곧 고장처럼 보였다.
    """
    if CONFIG.get("adapter") is None or getattr(CONFIG["adapter"], "simulated", False):
        return
    stamp = _device_stamp()
    if stamp == CONFIG.get("device_stamp"):
        return
    state.note("장치가 다시 꽂혔습니다 — 연결을 새로 엽니다")
    adapter = CONFIG["adapter"]
    try:
        adapter.__exit__(None, None, None)
    except Exception:
        pass
    try:
        adapter.__enter__()
        time.sleep(1.0)
        CONFIG["device_stamp"] = stamp
        _read_cache["value"] = {}
        state.disconnect_latched = False
        state.disconnect_reason = ""
        _recovery["failed_in_a_row"] = 0
        state.note("새 연결로 이어졌습니다")
    except Exception as exc:
        state.note(f"새 연결 실패: {exc}", "stop")


def _read_present(*, fresh: bool = False, _retried: bool = False) -> dict[str, int]:
    """지금 관절 값. 아주 짧은 사이의 반복 질문은 방금 답으로 대신한다.

    답이 멎으면 **한 번은 스스로 이어 본다.** _ensure_link()는 USB 장치가 새로
    꽂혔을 때만 연결을 다시 여는데, 실제로는 장치가 꽂힌 채 컨트롤러만 답을
    멈추는 일이 있다(MyCobot M5). 그러면 장치 이름이 그대로라 아무것도 다시
    열리지 않고, 런타임을 재시작할 때까지 모든 명령이 계속 끊긴 것처럼 보인다 —
    실기에서 그랬다. 부품이 "사람 없이 되살려도 된다"고 밝힌 경우에만 한다.
    """
    _ensure_link()
    now = time.monotonic()
    if not fresh and _read_cache["value"] and now - _read_cache["at"] < READ_CACHE_SEC:
        return dict(_read_cache["value"])
    try:
        with SERIAL_LOCK:
            value = CONFIG["adapter"].read_joint_positions()
    except HardwareConnectionLostError as exc:
        if _retried or not _auto_recover_allowed():
            raise
        state.note(f"로봇이 답하지 않음({exc}) — 연결을 다시 엽니다", "stop")
        _recover_hardware(force=True)
        return _read_present(fresh=True, _retried=True)
    _read_cache.update({"at": time.monotonic(), "value": dict(value)})
    return value


def _adapter_class(module_id: str, descriptor: dict[str, Any] | None = None):
    """부품 기술서가 **자기 어댑터를 밝힌다.** 런타임은 로봇 이름을 모른다.

    이전에는 여기서 module_id에 'omx'/'mycobot'이 들어 있는지 문자열로 훑었다.
    그러면 로봇이 하나 늘 때마다 이 함수를 고쳐야 한다 — 부품을 바꿔도 코드를
    고치지 않는다는 이 제품의 주장이 바로 여기서 깨졌다(xArm 반증 시험 20260817).

        "runtime_adapter": "xarm_adapter:XArmAdapter"
                            └ hangeul_runtime.hardware 안의 파일 : 클래스

    새 로봇은 어댑터 파일 한 장과 기술서 한 줄로 붙는다. 이 함수는 그대로다.
    """
    spec = str((descriptor if descriptor is not None
                else CONFIG.get("descriptor") or {}).get("runtime_adapter") or "").strip()
    if not spec:
        raise ValueError(
            f"부품 기술서에 runtime_adapter가 없습니다: {module_id} "
            f'(예: "runtime_adapter": "xarm_adapter:XArmAdapter")')
    file_name, _, class_name = spec.partition(":")
    if not file_name or not class_name:
        raise ValueError(f"runtime_adapter 형식은 '파일:클래스'입니다: {spec}")
    import importlib
    try:
        module = importlib.import_module(f".hardware.{file_name}", package=__package__)
    except ImportError as exc:
        raise ValueError(f"어댑터 파일을 찾지 못했습니다: {file_name} ({exc})") from exc
    try:
        return getattr(module, class_name)
    except AttributeError as exc:
        raise ValueError(f"어댑터 클래스를 찾지 못했습니다: {spec}") from exc


def _make_adapter(cls, device: str, descriptor: dict[str, Any]):
    """어댑터가 **받겠다고 선언한 것만** 넘긴다. 호출부에 로봇별 분기를 만들지 않는다.

    로봇마다 필요한 것이 다르다 — MyCobot은 꺼둔 축을, xArm 5/6/7은 관절 수를
    알아야 한다. 이전에는 `cls(device, excluded_joint_ids=...)`를 시도하고
    TypeError가 나면 `cls(device)`로 물러섰는데, 그러면 **기술서에 관절이 5개인데
    어댑터는 6개를 만드는 일**이 조용히 지나간다(xArm 반증 시험 20260817에서
    실제로 그랬다 — 없는 6번 관절에 명령이 나갈 뻔했다).
    """
    import inspect

    joints = descriptor.get("joints") or []
    offered: dict[str, Any] = {
        # 기술서에서 꺼둔 축은 어댑터에도 알려야 한다. MyCobot은 제외 축이 있으면
        # 관절별 명령으로 바꿔 보낸다 — 이걸 빠뜨리면 꺼둔 축의 각도까지 함께
        # 실려 나가 SDK가 통째로 거절한다(J4가 180°에 있어 실제로 그랬다).
        "excluded_joint_ids": [str(j["id"]) for j in joints if j.get("disabled")] or None,
        "joint_count": len(joints) or None,
        "descriptor": descriptor,
    }
    accepted = inspect.signature(cls.__init__).parameters
    kwargs = {k: v for k, v in offered.items() if k in accepted and v is not None}
    return cls(device, **kwargs)


# ── 부품 기술서에서 읽는 것들 ──────────────────────────────────
def _arm_joint_ids() -> list[str]:
    joints = CONFIG["descriptor"].get("joints") or []
    return [str(j["id"]) for j in joints if not j.get("disabled")]


def _hand_joint_id() -> str:
    """손 관절 번호. 손 기술서가 들고 있다."""
    return str(CONFIG.get("hand_joint") or "")


def _degrees_to_value(degrees: float) -> int:
    unit = CONFIG["descriptor"].get("unit") or {}
    per = float(unit.get("per_degree") or 1)
    center = float(unit.get("center") or 0)
    return int(round(center + degrees * per))


def _normalize_limits(raw: dict[str, Any]) -> dict[str, list[int]]:
    """화면이 준 안전 범위를 로봇의 단위로 옮긴다.

    화면 모양: {"11": [-180, 180], "15_min": 1060, "15_max": 2720, ...}
    팔 관절은 도(°), 손은 자기 단위 그대로다.
    """
    out: dict[str, list[int]] = {}
    mins: dict[str, int] = {}
    maxs: dict[str, int] = {}
    for key, value in (raw or {}).items():
        if key.endswith("_min") and isinstance(value, (int, float)):
            mins[key[:-4]] = int(value)
        elif key.endswith("_max") and isinstance(value, (int, float)):
            maxs[key[:-4]] = int(value)
        elif isinstance(value, (list, tuple)) and len(value) == 2:
            out[str(key)] = sorted([_degrees_to_value(float(value[0])),
                                    _degrees_to_value(float(value[1]))])
    for joint in set(mins) & set(maxs):
        out[joint] = [mins[joint], maxs[joint]]
    return out


def _velocity_for(payload: dict[str, Any]) -> int | None:
    """속도 결정 순서: 직접 지정 → 화면의 속도 낱말 → 없음(기본값)."""
    if payload.get("velocity") is not None:
        return int(payload["velocity"])
    speed = str(payload.get("speed") or "").lower()
    return SPEED_TO_VELOCITY.get(speed)


def _per_joint_velocity() -> dict[str, int]:
    return {str(k): int(v) for k, v in
            (CONFIG["limits_raw"].get("velocity_limits") or {}).items()}


def _temperature_limits() -> dict[str, float]:
    return {str(k): float(v) for k, v in
            (CONFIG["limits_raw"].get("temperature_limits_c") or {}).items()}


# ── 0~360 표기 ─────────────────────────────────────────────────
# 부품이 `wrap_degrees: 360`을 밝히면 사람이 보는 값은 0~360으로 돈다.
# 로봇에 보낼 때만 SDK가 받는 범위(-180~180)로 되돌린다. 이 지식도 부품
# 기술서에만 있다 — 런타임에 로봇 이름은 나오지 않는다.
def _wrap_span(joint: str) -> int:
    """이 관절이 0~360으로 도는가. 도는 관절만 기술서가 지목한다."""
    unit = CONFIG["descriptor"].get("unit") or {}
    span = int(unit.get("wrap_degrees") or 0)
    if not span or joint == _hand_joint_id():
        return 0
    wrapped = unit.get("wrap_joints")
    if wrapped is not None and str(joint) not in [str(j) for j in wrapped]:
        return 0                      # 이 관절은 예전대로 부호 있는 각도
    return span * int(unit.get("per_degree") or 1)


def _to_display(joint: str, value: int) -> int:
    """로봇이 준 값 → 사람이 보는 값."""
    span = _wrap_span(joint)
    return int(value) % span if span else int(value)


def _to_robot(joint: str, value: int) -> int:
    """사람이 고른 값 → 로봇이 받는 값."""
    span = _wrap_span(joint)
    if not span:
        return int(value)
    turned = int(value) % span
    return turned - span if turned > span // 2 else turned


def _display_pose(present: dict[str, Any]) -> dict[str, int]:
    return {j: _to_display(j, v) for j, v in present.items()}


def _split_targets(targets: dict[str, Any]) -> tuple[dict[str, int], int | None]:
    """팔 목표와 손 목표를 가른다. 어댑터가 둘을 다른 길로 다루기 때문이다."""
    hand = _hand_joint_id()
    arm: dict[str, int] = {}
    hand_target: int | None = None
    for joint, value in targets.items():
        if hand and str(joint) == hand:
            hand_target = int(value)
        else:
            arm[str(joint)] = int(value)
    return arm, hand_target


def _send(targets: dict[str, Any], velocity: int, label: str,
          *, min_gap: float | None = None) -> dict[str, Any]:
    """실제로 보낸다. 팔과 손을 각자의 길로 보낸다."""
    adapter = CONFIG["adapter"]
    arm, hand_target = _split_targets({j: _to_robot(str(j), v) for j, v in targets.items()})
    result: dict[str, Any] = {}
    _ensure_link()                     # 전원을 껐다 켰으면 새 연결로 이어붙인다
    _pace(min_gap)                     # 앞 명령과 너무 붙지 않게
    _read_cache["value"] = {}          # 움직였으니 방금 값은 버린다
    with SERIAL_LOCK:
      if arm:
        result["arm"] = adapter.move_joints(
            arm, velocity=velocity, acceleration=20, label=label,
            temperature_limits_c=_temperature_limits(),
            velocity_per_joint=_per_joint_velocity())
      if hand_target is not None:
        result["hand"] = adapter.move_gripper(
            hand_target, velocity=velocity, acceleration=20, label=label)
    return result


def _stop_hardware() -> bool:
    """멈춤은 토크를 끊지 않는다 — 끊으면 팔이 떨어진다(라운드 472에서 확인).
    지금 위치를 목표로 다시 써서 그 자리에 세운다."""
    adapter = CONFIG.get("adapter")
    if adapter is None:
        return False
    stop = getattr(adapter, "stop", None)
    if callable(stop):                      # MyCobot은 자체 정지 명령이 있다
        stop()
    # 자체 정지 명령이 있어도 **그 자리에 세우는 일은 건너뛰지 않는다.**
    # 전에는 stop()만 부르고 돌아섰는데, 컨트롤러의 정지는 토크를 보장하지
    # 않는다 — 멈춤을 눌렀는데 팔이 처지는 일이 실제로 있었다.
    try:
        present = adapter.read_joint_positions()      # 로봇 단위 그대로
        arm = {j: v for j, v in present.items() if j in _arm_joint_ids()}
        if arm:
            adapter.move_joints(arm, velocity=safety.DEFAULT_VELOCITY, acceleration=20,
                                label="estop_freeze", bypass_temperature_check=True)
    except Exception as exc:                # noqa: BLE001 — 멈춤은 실패해도 계속 간다
        state.note(f"멈춤 뒤 그 자리에 세우지 못했습니다: {exc}", "stop")
    return True


def _recover_hardware(*, force: bool = False, may_reopen_link: bool = False) -> dict[str, Any]:
    """서보에 걸린 오류 래치(과부하·과열·충격)를 풀고 그 자리에 다시 세운다.

    사람이 정지를 풀었는데 로봇이 계속 안 움직이면 그건 해제가 아니다.
    그래서 해제는 이 순서를 밟는다.

        1. 오류가 걸린 관절을 REBOOT — 재시도로는 안 풀리는 래치를 푸는 표준 절차
        2. 곧바로 토크를 켜고 지금 위치를 목표로 써서 그 자리에 세운다
           (REBOOT 직후에는 토크가 꺼져 있어, 그냥 두면 팔이 처진다)
    """
    adapter = CONFIG.get("adapter")
    if adapter is None:
        return {"attempted": False, "reason": "시늉 모드"}

    # 되살리기 중 거친 부분(연결을 다시 여는 것)은 통신이 죽었을 때만 일어난다.
    # 오류 해제·서보 재장악·재개는 멀쩡한 로봇에도 해가 없으므로 늘 한다 —
    # 특히 재개(resume)를 빼먹으면 정지를 푼 뒤에도 로봇이 움직이지 않는다.
    report: dict[str, Any] = {"attempted": True}
    recover = getattr(adapter, "recover_from_fault", None)
    if callable(recover):
        try:
            # 연결 다시 열기는 컨트롤러를 재부팅시켜 토크를 끊는다 — 팔이 떨어진다.
            # 사람이 시킨 복구에서만 허락한다.
            try:
                answer = recover(may_reopen_link=may_reopen_link)
            except TypeError:            # 그 신호를 모르는 어댑터도 있다
                answer = recover()
            report["joints"] = {str(k): v for k, v in (answer or {}).items()}
        except Exception as exc:
            report["error"] = str(exc)
    try:
        present = adapter.read_joint_positions()      # 로봇 단위 그대로
        arm = {j: v for j, v in present.items() if j in _arm_joint_ids()}
        if arm:
            adapter.move_joints(arm, velocity=safety.DEFAULT_VELOCITY, acceleration=20,
                                label="recover_hold", bypass_temperature_check=True)
        report["present"] = _display_pose(present)
        report["held"] = bool(arm)
    except Exception as exc:
        report["hold_error"] = str(exc)
    state.note("오류 복구 시도" + (" — 실패" if report.get("hold_error") else " — 그 자리에 세움"))
    _refresh_attestation()          # 복구 뒤에는 무엇이 돌아왔는지 다시 본다
    return report


# ── 상태 ────────────────────────────────────────────────────────
@app.get("/api/estop-status")
def estop_status() -> dict:
    """콘솔이 살아있음을 확인하는 자리이기도 하다. 부작용 없는 읽기."""
    return {"ok": True, **state.to_dict(), "module": CONFIG["module"],
            "device": CONFIG["device"], "simulated": CONFIG["adapter"] is None or bool(getattr(CONFIG["adapter"], "simulated", False)),
            # 시늉이면 **왜 시늉인지** 함께 준다. 조용한 시늉은 거짓말에 가깝다
            "simulate_reason": CONFIG.get("simulate_reason") or "",
            # 부품별 응답 — **언제 본 것인지와 함께** 준다. 시각 없는 증거는
            # 증거가 아니다. 빈 사전이면 "부품별로 말할 수단이 없다"는 뜻이다.
            "parts": _ATTEST.get("parts") or {},
            "parts_checked_at": _ATTEST.get("at") or "",
            "parts_error": _ATTEST.get("error") or "",
            "parts_reason": _ATTEST.get("reason") or "",
            # 옛 노드와 같은 이름도 함께 준다 — 화면이 둘 다 읽는다
            "active": state.estop_latched}


@app.post("/api/attest-parts")
def attest_parts_now() -> dict:
    """부품 확인을 지금 다시 한다. 사람이 무언가를 꽂거나 뺀 뒤 누른다."""
    answer = _refresh_attestation()
    return {"ok": True, "parts": answer.get("parts") or {},
            "parts_checked_at": answer.get("at") or "",
            "parts_error": answer.get("error") or "",
            "parts_reason": answer.get("reason") or ""}


@app.post("/api/estop")
def estop(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """정지는 어떤 상태에서도 받는다. 안전 판정을 기다리지 않는다."""
    state.latch_estop(str(payload.get("reason") or "운영자 요청"))
    stopped = False
    try:
        stopped = _stop_hardware()
    except Exception as exc:                       # 정지는 실패해도 기록하고 계속
        state.note(f"정지 명령 중 오류: {exc}", "stop")
    return {"success": True, "stopped_hardware": stopped, **state.to_dict()}


@app.post("/api/estop-reset")
def estop_reset(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    operator = str(payload.get("operator") or "")
    if not operator:
        return {"success": False, "error": "누가 확인했는지 남겨야 해제할 수 있습니다"}
    if not payload.get("confirmed"):
        return {"success": False, "error": "confirmed=false: 긴급 정지 해제에는 명시적 확인이 필요합니다."}
    state.clear_estop(operator)
    _recovery["failed_in_a_row"] = 0        # 사람이 확인했으니 다시 시도할 기회를 준다
    # 서보 오류 래치까지 풀어야 실제로 다시 움직인다. 상태 표시만 바꾸지 않는다.
    # 사람이 확인하고 누른 해제다 — 여기서는 연결 다시 열기까지 허락한다.
    recovery = _recover_hardware(may_reopen_link=True)
    state.disconnect_latched = False
    state.disconnect_reason = ""
    ok = not recovery.get("hold_error")
    return {"success": ok, "message": ("🚨 긴급 정지가 해제되었습니다."
                                       if ok else "정지는 풀었으나 로봇이 아직 응답하지 않습니다."),
            "error": recovery.get("hold_error", ""),
            "effective_device": CONFIG["device"], "disconnect_latched": False,
            "disconnect_recovery": recovery, **state.to_dict()}


@app.post("/api/pause-hold")
def pause_hold(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    state.paused = bool(payload.get("paused", True))
    state.note("일시정지" if state.paused else "일시정지 해제")
    if state.paused:
        try:
            _stop_hardware()
        except Exception as exc:
            state.note(f"일시정지 중 오류: {exc}", "stop")
    return {"success": True, **state.to_dict()}


@app.post("/api/away-mode")
def away_mode(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    state.away_mode = bool(payload.get("away_mode"))
    state.note("부재 모드 " + ("켜짐" if state.away_mode else "꺼짐"))
    return {"success": True, "away_mode": state.away_mode}


# ── 읽기 ────────────────────────────────────────────────────────
@app.get("/api/read-pose")
def read_pose() -> dict:
    _refresh_files()
    adapter = CONFIG.get("adapter")
    if adapter is None:
        return {"success": False, "present": {}, "hardware_preflight": {},
                "reason": "로봇이 연결되지 않았습니다"}
    try:
        present = _read_present()
    except HardwareConnectionLostError as exc:
        state.latch_disconnect(str(exc))
        return {"success": False, "present": {}, "hardware_preflight": {}, "reason": str(exc)}
    except Exception as exc:                      # noqa: BLE001
        # 읽기 실패를 500으로 떨어뜨리면 화면에는 "접속이 끊겼다"만 남고 이유가
        # 사라진다. 어떤 어댑터가 무엇을 올리든 읽을 수 있는 말로 돌려준다.
        state.note(f"자세를 읽지 못했습니다: {exc}", "stop")
        return {"success": False, "present": {}, "hardware_preflight": {},
                "reason": f"자세를 읽지 못했습니다: {exc}"}
    present = _display_pose(present)
    preflight: dict[str, Any] = {}
    try:
        with SERIAL_LOCK:
            preflight = adapter.preflight()
    except Exception as exc:                      # 읽기 실패가 자세 읽기를 막지는 않는다
        preflight = {"passed": False, "error": str(exc)}
    return {"success": True, "present": present, "hardware_preflight": preflight}


@app.get("/api/servo-report")
def servo_report() -> dict:
    """서보 하나하나가 실제로 어떤 상태인지 읽는다. **읽기만 한다.**

    "왜 안 움직이는가"를 추측으로 답하지 않기 위해서다. 팔 전원이 꺼져 있는
    것과 서보 하나가 죽은 것은 화면에서 똑같이 '안 움직임'으로 보인다.
    """
    adapter = CONFIG.get("adapter")
    if adapter is None:
        return {"ok": False, "reason": "시늉 모드"}
    mc = getattr(adapter, "mc", None)
    if mc is None:
        return {"ok": False, "reason": "연결 없음"}
    out: dict[str, Any] = {"ok": True}

    def ask(name: str, *args):
        fn = getattr(mc, name, None)
        if not callable(fn):
            return "없는 명령"
        try:
            with SERIAL_LOCK:
                return fn(*args)
        except Exception as exc:              # noqa: BLE001
            return f"{type(exc).__name__}: {exc}"

    out["is_power_on"] = ask("is_power_on")
    out["is_all_servo_enable"] = ask("is_all_servo_enable")
    out["is_free_mode"] = ask("is_free_mode")
    out["error_information"] = ask("get_error_information")
    out["servo_enable"] = {str(i): ask("is_servo_enable", i) for i in range(1, 7)}
    out["servo_status"] = ask("get_servo_status")
    out["servo_voltages"] = ask("get_servo_voltages")
    out["servo_temps"] = ask("get_servo_temps")
    return out


@app.get("/api/history")
def history() -> dict:
    return {"ok": True, "history": state.history}


@app.get("/api/server-camera-frame")
def camera_frame() -> dict:
    """지금 한 장. 눈이 안 꽂혀 있으면 없다고 답한다 — 있는 척하지 않는다."""
    import base64

    if CONFIG.get("eye") is None:
        return {"success": False, "available": False,
                "reason": _eye_refusal() or "이 런타임에는 눈(카메라) 부품이 꽂혀 있지 않습니다"}
    # 추적이 돌고 있으면 그 화면을 그대로 준다. 카메라는 한 번에 한 프로그램만 연다.
    session = _TRACKING["session"]
    if session is not None and session.running:
        jpeg = session.frame_jpeg()
        if jpeg is not None:
            return {"success": True, "available": True, "source": "tracking",
                    "jpeg_base64": base64.b64encode(jpeg).decode("ascii")}
    try:
        with _eye_factory()() as camera:
            frame = camera.read_frame()
            if frame is None:
                return {"success": False, "available": False,
                        "reason": "카메라가 프레임을 주지 않습니다"}
            import cv2

            ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ok:
                return {"success": False, "available": False, "reason": "프레임을 담지 못했습니다"}
            return {"success": True, "available": True, "source": "camera",
                    "jpeg_base64": base64.b64encode(buffer.tobytes()).decode("ascii")}
    except Exception as exc:                      # noqa: BLE001 — 화면은 이유를 봐야 한다
        return {"success": False, "available": False, "reason": f"{type(exc).__name__}: {exc}"}


# ── 목표물 추적 ─────────────────────────────────────────────────
# 카메라도 시리얼도 한 줄이다. 판은 한 번에 하나만 돈다.
_TRACKING: dict[str, Any] = {"session": None}


def _eye_refusal() -> str:
    return str(CONFIG.get("eye_refusal") or "")


def _eye_factory():
    """눈 어댑터를 만드는 함수. 팔과 **똑같은 길로** 기술서에서 어댑터를 찾는다."""
    descriptor = CONFIG.get("eye_descriptor") or {}
    cls = _adapter_class(str(CONFIG.get("eye")), descriptor)
    device = str(CONFIG.get("eye_device") or "")
    return lambda: _make_adapter(cls, device, descriptor)


def _tracking_unavailable() -> dict:
    return {"success": False, "ok": True, "available": False,
            "running": False, "process_running": False, "tracking": False,
            "follow": "unavailable", "event": None, "last": None,
            "reason_code": "not_implemented",
            "error": "공개판에서는 물체·색상 추적을 제공하지 않습니다",
            "actual_hardware_called": False}


@app.get("/api/target-tracking-status")
@app.get("/api/color-tracking-status")
def target_tracking_status() -> dict:
    return _tracking_unavailable()


@app.post("/api/target-tracking/start")
@app.post("/api/target-tracking/stop")
@app.post("/api/target-tracking/select")
@app.post("/api/target-tracking/clear")
@app.post("/api/target-tracking/follow")
@app.post("/api/color-tracking/start")
@app.post("/api/color-tracking/stop")
def target_tracking_start(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    return _tracking_unavailable()


@app.get("/api/camera-stream")
def camera_stream():
    return _tracking_unavailable()


# ── 움직임 ──────────────────────────────────────────────────────
class UnsteadyReading(RuntimeError):
    """지금 위치를 두 번 읽었는데 서로 다르다."""


# 두 번 읽은 값이 이만큼 넘게 다르면 믿지 않는다. 미세 이동은 '지금 위치'에서
# 출발하므로, 흔들리는 값을 그대로 믿으면 팔이 엉뚱한 곳으로 간다.
STEADY_TOLERANCE = 2000


def _steady_reading(joint: str) -> dict[str, int]:
    """미세 이동의 출발점은 두 번 읽어 같을 때만 쓴다."""
    adapter = CONFIG["adapter"]
    first = _display_pose(_read_present(fresh=True))
    second = _display_pose(_read_present(fresh=True))
    a, b = first.get(joint), second.get(joint)
    if a is None or b is None:
        return first
    if abs(int(a) - int(b)) > STEADY_TOLERANCE:
        raise UnsteadyReading(
            f"관절 {joint}의 현재 값이 흔들립니다({a} vs {b}). "
            f"통신이 불안정합니다 — 로봇 전원과 연결을 확인하세요")
    return second


def _blocked(exc: safety.SafetyBlocked) -> dict:
    state.note(f"이동 차단: {exc}", "stop")
    return {"success": False, "verdict": "BLOCKED_SAFETY_PRECHECK_FAILED",
            "reason_code": exc.reason_code, "blocked_reasons": [str(exc)],
            "error": str(exc), "actual_hardware_called": False}


def _no_hardware() -> dict:
    return {"success": False, "verdict": "NO_HARDWARE",
            "blocked_reasons": ["로봇이 연결되지 않았습니다"],
            "error": "로봇이 연결되지 않았습니다", "actual_hardware_called": False}


def _auto_recover_allowed() -> bool:
    block = CONFIG["descriptor"].get("auto_recover") or {}
    if not block.get("safe_without_operator"):
        return False
    return _recovery["failed_in_a_row"] < AUTO_RECOVER_STRIKES


def _run(targets: dict[str, Any], velocity: int, label: str, verdict: str,
         *, _retried: bool = False, read_back: bool = True,
         min_gap: float | None = None) -> dict:
    physical = not bool(getattr(CONFIG.get("adapter"), "simulated", False))
    sent: dict[str, Any] = {}
    try:
        sent = _send(targets, velocity, label, min_gap=min_gap)
    except InFlightSafetyViolationError as exc:
        state.latch_estop(str(exc))
        return {"success": False, "verdict": "BLOCKED_IN_FLIGHT_SAFETY",
                "blocked_reasons": [str(exc)], "error": str(exc),
                "actual_hardware_called": physical, "simulated": not physical}
    except HardwareConnectionLostError as exc:
        state.latch_disconnect(str(exc))
        return {"success": False, "verdict": "DISCONNECTED",
                "blocked_reasons": [str(exc)], "error": str(exc),
                "actual_hardware_called": physical, "simulated": not physical}
    except (ValueError, KeyError) as exc:
        return {"success": False, "verdict": "BLOCKED_BAD_TARGET",
                "blocked_reasons": [str(exc)], "error": str(exc),
                "actual_hardware_called": False}
    except Exception as exc:
        # 컨트롤러가 도중에 멎는 일이 있다(여러 관절이 함께 움직일 때 특히).
        # 부품이 허락한 경우에는 스스로 되살리고 한 번만 다시 시도한다.
        if not _retried and _auto_recover_allowed():
            state.note(f"로봇이 응답하지 않음({exc}) — 되살리고 다시 시도합니다", "stop")
            report = _recover_hardware(force=True)
            if report.get("hold_error"):
                return {"success": False, "verdict": "BLOCKED_HARDWARE_REFUSED",
                        "blocked_reasons": [f"{exc}", "되살리기도 실패했습니다"],
                        "error": str(exc), "auto_recovery": report,
                        "actual_hardware_called": physical, "simulated": not physical}
            answer = _run(targets, velocity, label, verdict, _retried=True)
            answer["auto_recovery"] = report
            return answer
        # 로봇이 거절한 이유를 그대로 올린다. 500으로 떨어뜨리면 화면에는
        # "연결 안 됨"만 남아 진짜 이유가 사라진다.
        state.note(f"로봇이 거절함: {exc}", "stop")
        return {"success": False, "verdict": "BLOCKED_HARDWARE_REFUSED",
                "blocked_reasons": [str(exc)], "error": str(exc),
                "actual_hardware_called": physical, "simulated": not physical}
    present = {}
    if read_back:
        # 움직인 뒤의 자세를 화면에 돌려주기 위한 읽기다. 시리얼 왕복 한 번
        # (실측 40~50ms)이 더 든다. **추적처럼 곧바로 다음 명령이 이어지는
        # 자리에서는 이 값을 아무도 안 쓰므로 건너뛴다** — 안 쓰는 값을 읽느라
        # 제어 주기가 느려지면 팔이 목표를 못 따라간다.
        try:
            present = _display_pose(_read_present(fresh=True))
        except Exception:
            present = {}

    arm_result = sent.get("arm") or {}
    if (isinstance(arm_result, dict) and arm_result.get("settled") is False
            and not _retried and _auto_recover_allowed()):
        # 부품이 "사람 없이 복구해도 된다"고 밝힌 경우에만 스스로 한 번 되살린다.
        # MyCobot 컨트롤러는 관절 하나 때문에 오류를 걸고 팔 전체를 거부하는데,
        # 그 해제는 토크를 끊지 않으므로 사람을 기다릴 이유가 없다.
        report = _recover_hardware(force=True)
        state.note("스스로 복구하고 한 번 다시 시도합니다")
        answer = _run(targets, velocity, label, verdict, _retried=True)
        answer["auto_recovery"] = report
        return answer

    # 어댑터가 "목표에 닿지 않았다"고 하면 성공이라고 말하지 않는다.
    # 명령을 받았다는 것과 로봇이 움직였다는 것은 다르다 — MyCobot이 서보 하나
    # 때문에 팔 동작을 거부하면서도 명령은 정상 접수하던 일이 실제로 있었다.
    arm = sent.get("arm") or {}
    # 멈춰 선 것과 몇 도 못 미친 것은 다르다. 뒤엣것은 막지 않는다 — 사람이
    # 이미 해보고 쓰던 자세가 2.2도 차이로 '미도달'이 되어 실행이 끊겼다(실측).
    if isinstance(arm, dict) and arm.get("settled") is False and arm.get("near_enough"):
        worst = max((arm.get("errors_deg") or {}).values(), default=0.0)
        state.note(f"목표에 {worst:.1f}도 못 미쳤지만 그 자리로 봅니다")
        _note_result(True)
        _recovery["failed_in_a_row"] = 0
        return {"success": True, "verdict": verdict, "actual_hardware_called": physical, "simulated": not physical,
                "targets": targets, "present": present,
                "warning": f"목표와 {worst:.1f}도 차이",
                "errors_deg": arm.get("errors_deg", {})}

    if isinstance(arm, dict) and arm.get("settled") is False:
        _note_result(False)
        if _retried:
            _recovery["failed_in_a_row"] += 1
        state.note("목표 미도달 — 로봇이 명령을 받고도 움직이지 않았습니다", "stop")
        return {"success": False, "verdict": "TARGET_NOT_REACHED",
                "blocked_reasons": [
                    "로봇이 명령을 받았지만 목표에 도달하지 않았습니다."
                    + (" 되살리기를 여러 번 해봤지만 효과가 없습니다 — 로봇 전원과"
                       " 서보 연결을 확인하세요. 화면의 '정지 해제'를 누르면 다시 시도합니다."
                       if _recovery["failed_in_a_row"] >= AUTO_RECOVER_STRIKES
                       else " '정지 해제'로 복구해 보고, 그래도 같으면 서보 연결을 확인하세요")],
                "error": "목표 미도달",
                "actual_hardware_called": physical, "simulated": not physical, "targets": targets, "present": present,
                "errors_deg": arm.get("errors_deg", {})}

    _note_result(True)
    _recovery["failed_in_a_row"] = 0
    return {"success": True, "verdict": verdict, "actual_hardware_called": physical, "simulated": not physical,
            "targets": targets, "present": present}


def _check_all(targets: dict[str, Any], velocity: int | None) -> int:
    _refresh_files()
    speed = safety.DEFAULT_VELOCITY
    for joint, target in targets.items():
        speed = safety.check_move(state, int(joint), int(target), CONFIG["limits"], velocity)
    return speed


@app.post("/api/move-to")
def move_to(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    joint = str(payload.get("joint_id") or "")
    target = int(payload.get("target_ticks") or payload.get("target") or 0)
    if not joint:
        return {"success": False, "error": "관절 번호가 없습니다", "actual_hardware_called": False}
    try:
        velocity = _check_all({joint: target}, _velocity_for(payload))
    except safety.SafetyBlocked as exc:
        return _blocked(exc)
    if CONFIG.get("adapter") is None:
        return _no_hardware()
    answer = _run({joint: target}, velocity, "move_to", "MOVED")
    answer["target"] = target
    return answer


@app.post("/api/jog")
def jog(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """미세 이동 — 지금 위치에서 얼마만큼. 목표는 런타임이 계산한다."""
    joint = str(payload.get("joint_id") or "")
    delta = int(payload.get("delta_ticks") or payload.get("delta") or 0)
    if not joint:
        return {"success": False, "error": "관절 번호가 없습니다", "actual_hardware_called": False}
    adapter = CONFIG.get("adapter")
    if adapter is None:
        return _no_hardware()
    try:
        present = _steady_reading(joint)
    except HardwareConnectionLostError as exc:
        state.latch_disconnect(str(exc))
        return {"success": False, "verdict": "DISCONNECTED", "error": str(exc),
                "blocked_reasons": [str(exc)], "actual_hardware_called": False}
    except UnsteadyReading as exc:
        state.note(f"읽은 값이 흔들림: {exc}", "stop")
        return {"success": False, "verdict": "BLOCKED_UNSTEADY_READING",
                "blocked_reasons": [str(exc)], "error": str(exc),
                "actual_hardware_called": False}
    except Exception as exc:                      # noqa: BLE001 — 500은 화면에서 "접속 끊김"이 된다
        state.note(f"지금 위치를 읽지 못했습니다: {exc}", "stop")
        return {"success": False, "verdict": "BLOCKED_READ_FAILED",
                "blocked_reasons": [f"지금 위치를 읽지 못해 미세 이동을 시작할 수 없습니다: {exc}"],
                "error": str(exc), "actual_hardware_called": False}
    if joint not in present:
        return {"success": False, "error": f"올바르지 않은 관절 번호입니다: {joint}",
                "present": present, "actual_hardware_called": False}
    # 0~360으로 도는 값은 한 바퀴를 넘어가도 그대로 이어져야 한다.
    # 이 처리가 없으면 1.49도에서 -4도를 누를 때 -2.51이 되어 범위 밖으로 막힌다.
    target = _to_display(joint, int(present[joint]) + delta)
    try:
        velocity = _check_all({joint: target}, _velocity_for(payload))
    except safety.SafetyBlocked as exc:
        answer = _blocked(exc)
        answer.update({"present": present, "target": target})
        return answer
    answer = _run({joint: target}, velocity, "jog", "MOVED")
    answer["target"] = target
    return answer


@app.post("/api/execute-actual")
def execute_actual(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """자세 하나를 실행한다. 목표값은 콘솔이 준다 — 런타임은 판정하고 보낸다."""
    targets = payload.get("targets") or {}
    if not targets:
        return {"success": False, "verdict": "NO_TARGETS",
                "blocked_reasons": ["보낼 관절 목표가 없습니다"],
                "error": "보낼 관절 목표가 없습니다", "actual_hardware_called": False}

    # 사람이 지금 자리에 있는지 — 화면이 확인한 항목을 그대로 받는다
    inputs = payload.get("safety_inputs") or {}
    missing = [name for name in ("operator_present", "workspace_clear",
                                 "manual_stop_available", "estop_ready")
               if not inputs.get(name)]
    if inputs.get("human_nearby"):
        missing.append("human_nearby")
    if missing:
        return {"success": False, "verdict": "BLOCKED_SAFETY_PRECHECK_FAILED",
                "blocked_reasons": [f"운영자 확인 항목이 채워지지 않았습니다: {', '.join(missing)}"],
                "actual_hardware_called": False}
    if not payload.get("issue_token", True):
        return {"success": False, "verdict": "BLOCKED_TOKEN_NOT_ISSUED",
                "blocked_reasons": ["issue_token=false: 운영자 최종 확인이 필요합니다."],
                "actual_hardware_called": False}

    try:
        velocity = _check_all(targets, _velocity_for(payload))
    except safety.SafetyBlocked as exc:
        return _blocked(exc)
    if CONFIG.get("adapter") is None:
        return _no_hardware()
    answer = _run(targets, velocity, str(payload.get("skill_id") or "execute"),
                  "ACTUAL_MOTION_EXECUTED_ONCE")
    if answer.get("success"):
        state.note(f"실행 완료: 관절 {len(targets)}개")
    return answer


# ── 설정·복구 ───────────────────────────────────────────────────
@app.get("/api/safety-limits")
def safety_limits() -> dict:
    _refresh_files()
    """화면이 저장한 모양 그대로 + 로봇 단위로 옮긴 범위.

    화면은 두 가지를 다 쓴다. 편집기는 사람이 적은 도(°) 값을, 미세 이동 눈금은
    로봇 단위 범위를 읽는다.
    """
    return {**CONFIG["limits_raw"],
            "joint_tick_limits": {k: list(v) for k, v in CONFIG["limits"].items()},
            "robot_model": (CONFIG["descriptor"].get("runtime_model")
                            or CONFIG.get("module") or ""),
            "max_velocity": safety.MAX_VELOCITY}


@app.post("/api/save-safety-limits")
def save_safety_limits(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    raw = payload.get("limits") if isinstance(payload.get("limits"), dict) else payload
    raw = {k: v for k, v in raw.items()
           if k not in ("robot_model", "device", "operator", "max_velocity")}
    if not raw:
        return {"success": False, "error": "저장할 안전 범위가 없습니다"}
    CONFIG["limits_raw"] = raw
    CONFIG["limits"] = _normalize_limits(raw)
    _save_limits_file()
    state.note("안전 범위 변경")
    return {"success": True, "message": "안전 가이드라인 범위 설정이 저장되었습니다.",
            "warnings": [], "limits": CONFIG["limits_raw"]}


@app.post("/api/recover-robot-usb")
def recover_robot_usb(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """장치가 빠졌다 돌아왔을 때 다시 연다. 읽기만으로 확인한다."""
    adapter = CONFIG.get("adapter")
    if adapter is None:
        return {"success": False, "error": "시늉 모드에서는 복구할 것이 없습니다"}
    detail = _recover_hardware(may_reopen_link=True)   # 사람이 누른 복구다
    if detail.get("hold_error"):
        return {"success": False, "error": detail["hold_error"],
                "effective_device": CONFIG["device"], "detail": detail}
    state.disconnect_latched = False
    state.disconnect_reason = ""
    state.note("장치 복구 확인")
    return {"success": True, "effective_device": CONFIG["device"],
            "detail": detail, "present": detail.get("present", {})}


# ── 세우기 ──────────────────────────────────────────────────────
def _module_path(module_id: str) -> Path:
    return Path(CONFIG["modules_dir"]) / f"{module_id}.json"


def _load_descriptor(module_id: str) -> dict[str, Any]:
    path = _module_path(module_id)
    if not path.exists():
        raise FileNotFoundError(f"부품 기술서를 찾지 못했습니다: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_hand(module_id: str) -> int | None:
    """이 팔에 꽂히는 손을 찾아 관절 번호를 얻는다."""
    for path in sorted(Path(CONFIG["modules_dir"]).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("module_class") != "hand":
            continue
        if str(data.get("mount", "")).split(".")[0] == module_id:
            return (data.get("command") or {}).get("joint")
    return None


def _load_eye(explicit_id: str = "") -> tuple[str | None, dict[str, Any], str]:
    """이 런타임이 쓸 눈을 정한다. (부품 ID, 기술서, 못 정한 이유)

    눈은 팔이 아니라 몸통(core)에 꽂힌다 — 손처럼 팔 이름으로 찾을 수 없다.
    그래서 **여럿이면 고르지 않는다.** 하나뿐일 때만 그것으로 본다.
    카메라를 잘못 골라 엉뚱한 방향을 보며 팔을 움직이는 것보다, 어느 눈인지
    밝히라고 하는 편이 낫다.
    """
    eyes: list[dict[str, Any]] = []
    for path in sorted(Path(CONFIG["modules_dir"]).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("module_class") == "eye":
            eyes.append(data)
    if explicit_id:
        for data in eyes:
            if data.get("module_id") == explicit_id:
                return explicit_id, data, ""
        return None, {}, f"눈 부품 기술서를 찾지 못했습니다: {explicit_id}"
    if not eyes:
        return None, {}, "눈(카메라) 부품 기술서가 없습니다"
    if len(eyes) > 1:
        names = ", ".join(str(d.get("module_id")) for d in eyes)
        return None, {}, f"눈이 여럿입니다({names}) — --eye로 어느 것인지 밝혀 주세요"
    return str(eyes[0].get("module_id")), eyes[0], ""


def _limits_file() -> Path:
    return Path(CONFIG["limits_path"])


def _save_limits_file() -> None:
    path = _limits_file()
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(CONFIG["limits_raw"], ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def build(module_id: str, device: str, limits_path: str = "", *,
          modules_dir: str = "", simulate: bool = False,
          eye: str = "", eye_device: str = "", state_path: str = "") -> None:
    """런타임을 이 부품에 맞게 세운다. 실물이 없으면 시늉 모드로 뜬다."""
    _read_cache.update({"at": 0.0, "value": {}})   # 다른 로봇의 값을 물려받지 않는다
    _TRACKING["session"] = None
    root = Path(__file__).resolve().parents[3]
    CONFIG["modules_dir"] = modules_dir or str(root / "install" / "modules")
    CONFIG["module"] = module_id
    CONFIG["device"] = device
    CONFIG["descriptor"] = _load_descriptor(module_id)
    CONFIG["hand_joint"] = _load_hand(module_id)
    CONFIG["limits_path"] = limits_path or str(root / "data" / f"safety_limits_{module_id}.json")

    # 막는 상태(정지·단선·일시정지·부재)를 파일에 잇는다. 이게 없으면 정지를
    # 걸어 둔 채 런타임이 죽었다 살아날 때 래치가 풀린 채로 태어난다 —
    # 사람이 풀지 않았는데 풀리는 길이다(safety.py 머리말).
    CONFIG["state_path"] = state_path or str(root / "data" / f"safety_state_{module_id}.json")
    inherited = state.bind_storage(CONFIG["state_path"])
    blocking = state.blocking_summary()
    if blocking:
        state.note("이전 상태를 이어받았습니다 — " + " · ".join(blocking)
                   + ". 풀려면 사람이 해제해야 합니다", "stop")
    elif inherited:
        state.note("이전 상태를 이어받았습니다 — 막는 것 없음")

    # 눈은 **여기서 열지 않는다.** 카메라는 추적이 시작될 때만 열린다 —
    # 계속 붙들고 있으면 다른 프로그램이 같은 카메라를 못 쓰고, 쓰지도 않는
    # 장치를 잡고 있게 된다.
    eye_id, eye_descriptor, refusal = _load_eye(eye)
    CONFIG["eye"] = eye_id
    CONFIG["eye_descriptor"] = eye_descriptor
    CONFIG["eye_refusal"] = refusal
    CONFIG["eye_device"] = eye_device or (eye_descriptor.get("device") or {}).get(
        "windows" if os.name == "nt" else "linux", "")

    raw: dict[str, Any] = {}
    if _limits_file().exists():
        raw = json.loads(_limits_file().read_text(encoding="utf-8"))
    CONFIG["limits_raw"] = raw
    CONFIG["limits"] = _normalize_limits(raw)

    def _simulate(reason: str) -> None:
        CONFIG["adapter"] = None
        CONFIG["simulate_reason"] = reason
        state.note(f"시늉 모드 ({module_id}) — {reason}. 실물에 아무것도 보내지 않습니다")

    # Explicit simulation must never open the descriptor's physical adapter.
    # **어댑터 이름을 문자열로 비교하지 않는다.** `_adapter_class()`에서 걷어낸
    # 문자열 훑기가 여기서 되살아나 있었다 — 두 번째 시뮬레이터(Gazebo 등)를
    # 붙이면 시늉으로 알아보지 못하고 `adapter=None`으로 조용히 내려갔다.
    # 기술서가 자기가 시늉인지 밝힌다.
    descriptor = CONFIG["descriptor"]
    is_demo = bool(descriptor.get("simulated")) or \
        descriptor.get("runtime_adapter") == "simulated_arm_adapter:SimulatedArmAdapter"
    if simulate or is_demo:
        from .hardware.simulated_arm_adapter import SimulatedArmAdapter
        descriptor = dict(CONFIG["descriptor"])
        descriptor["hand"] = {"command": {"joint": CONFIG["hand_joint"]}}
        CONFIG["adapter"] = SimulatedArmAdapter(descriptor=descriptor)
        CONFIG["simulate_reason"] = "가상 팔 시뮬레이션 — 실물에 명령을 보내지 않습니다"
        CONFIG["device_stamp"] = _device_stamp()
        state.note(CONFIG["simulate_reason"])
        return
    if not device:
        _simulate("장치 이름이 없습니다")
        return

    # 기술서에서 꺼둔 축은 어댑터에도 알려야 한다. MyCobot은 제외 축이 있으면
    # 관절별 명령으로 바꿔 보낸다 — 이걸 빠뜨리면 꺼둔 축의 각도까지 함께
    # 실려 나가 SDK가 통째로 거절한다(J4가 180°에 있어 실제로 그랬다).
    #
    # **로봇이 없다고 런타임이 죽지 않는다.** 처음 받은 사람은 대개 로봇이 없거나
    # 포트 이름이 다르다. 그때 프로세스가 죽어버리면 화면조차 못 본다. 시늉 모드로
    # 내려가되 **왜 그랬는지 그대로 올린다** — 조용히 시늉하는 것이 제일 나쁘다.
    try:
        cls = _adapter_class(module_id)
        adapter = _make_adapter(cls, device, CONFIG["descriptor"])
        adapter.__enter__()
    except Exception as exc:                    # noqa: BLE001 — 어떤 실패든 화면은 떠야 한다
        _simulate(f"{device}에 연결하지 못했습니다 ({type(exc).__name__}: {exc})")
        return
    CONFIG["adapter"] = adapter
    CONFIG["simulate_reason"] = ""
    CONFIG["device_stamp"] = _device_stamp()
    state.note(f"로봇 연결 ({module_id} @ {device})")
    _refresh_attestation()          # 붙자마자 무엇이 응답하는지 본다


def main() -> int:
    parser = argparse.ArgumentParser(description="한글 로봇 런타임")
    parser.add_argument("--module", required=True,
                        help="부품 ID — install/modules의 기술서 파일 이름")
    parser.add_argument("--device", default="", help="장치 이름 (예: /dev/ttyUSB0, COM3)")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--limits", default="", help="안전 범위 JSON 파일")
    parser.add_argument("--modules", default="", help="부품 기술서 폴더")
    parser.add_argument("--simulate", action="store_true", help="실물 없이 띄운다")
    parser.add_argument("--eye", default="",
                        help="눈 부품 ID — 눈이 여럿일 때만 필요하다")
    parser.add_argument("--eye-device", default="",
                        help="카메라 장치 (예: /dev/video0). 없으면 기술서의 값을 쓴다")
    args = parser.parse_args()

    build(args.module, args.device, args.limits,
          modules_dir=args.modules, simulate=args.simulate,
          eye=args.eye, eye_device=args.eye_device)

    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
