"""MyCobot 280-M5 어댑터.

M5 컨트롤러는 ``pymycobot.MyCobot280``로 115200 baud 시리얼을 쓴다. Dexter
프로젝트에서 실기로 검증된 로직을 그대로 포팅했다 — 관절 단위는 millidegree로
유지해 정수 목표값 파이프라인을 그대로 쓴다.

모듈 import 시점에는 SDK를 불러오지 않는다 — pymycobot이나 실물 로봇이 없는
환경에서도 이 모듈을 임포트해 테스트할 수 있다.

excluded_joints는 환경변수가 아니라 인스턴스 설정(§설계문서 2-2)에서 주입한다 —
"이 개체만의 결함"이 모델 전체 속성으로 굳어버리는 것을 막기 위함이다.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any, Callable, TypeVar

from hangeul_runtime.abstraction.robot_arm_adapter import (
    RobotArmAdapter,
    effective_velocity,
)
from hangeul_runtime.hardware_errors import HardwareConnectionLostError

MYCOBOT_280_M5_BAUD = 115200
# 모델 매니페스트(install/profiles/mycobot_280_m5_profile.json)의 id_policy가
# "mycobot_joint_ids"로 선언한 값과 반드시 일치해야 한다 — arm_joint_names는
# ["1".."6"], gripper.name은 "7"이다(§설계문서 §2-1). 과거 "joint_1"/"gripper"
# 내부 표기를 그대로 두면 /api/robot-joints가 약속한 id로 /api/jog·/api/move-to·
# /api/read-pose를 호출했을 때 전부 "알 수 없는 관절"로 실패한다 — OMX 어댑터
# (joint_names=["11".."14"], gripper="15")는 이미 매니페스트와 일치해 정상 동작
# 하는데 MyCobot만 어긋나 있었다(실기 확인, 2026-08-13).
MYCOBOT_ARM_JOINTS = tuple(str(i) for i in range(1, 7))
MYCOBOT_GRIPPER = "7"
# 실측 안전 동작범위 (Dexter 프로젝트 MyCobot 280-M5 실기 검증 결과).
MYCOBOT_MEASURED_LIMITS_DEG: dict[str, tuple[float, float]] = {
    "1": (-84.0, 84.0),
    "2": (-120.0, 120.0),
    "3": (-150.0, 120.0),
    "4": (-150.0, 120.0),
    "5": (-155.0, 120.0),
    "6": (-168.0, 168.0),
}
GRIPPER_MIN = 0
GRIPPER_MAX = 100
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_S = 0.15
MYCOBOT_SETTLE_TIMEOUT_S = 8.0
# M5 read-back은 정착 후에도 0.几도씩 흔들린다 — ±1도가 실측으로 확인된 유효
# 허용창이다(±0.5도로 두면 실제로 정상 이동한 것도 실패로 보고됨).
MYCOBOT_SETTLE_TOLERANCE_DEG = 1.0
MYCOBOT_SETTLE_POLL_S = 0.25
# 움직이지 않는 로봇에 8초 동안 물어보면 컨트롤러가 견디지 못한다.
# 이만큼 기다렸는데 조금도 가까워지지 않으면 그만 묻는다.
MYCOBOT_NO_PROGRESS_S = 2.0
MYCOBOT_PROGRESS_EPS_DEG = 0.2
MYCOBOT_DEVICE_ENV = "BEOM_MYCOBOT_DEVICE"

T = TypeVar("T")


def _millideg(value: float) -> int:
    return int(round(float(value) * 1000.0))


def _degree(value: int) -> float:
    return float(value) / 1000.0


class MyCobot280M5Adapter(RobotArmAdapter):
    """보수적인 각도 기반 목표값을 쓰는 구체 어댑터."""

    robot_model = "mycobot_280_m5"

    def __init__(
        self,
        device: str | None = None,
        *,
        baud: int = MYCOBOT_280_M5_BAUD,
        excluded_joint_ids: list[str] | None = None,
        sdk: Any | None = None,
        transport: str = "serial",
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
        retry_delay_s: float = DEFAULT_RETRY_DELAY_S,
        descriptor: dict[str, Any] | None = None,
    ) -> None:
        self.device = device or os.environ.get(MYCOBOT_DEVICE_ENV, "/dev/ttyUSB0")
        self.baud = int(baud)
        self._sdk = sdk
        self.transport = transport
        self._mc: Any | None = None
        self.joint_names = list(MYCOBOT_ARM_JOINTS)
        self.gripper_joint_name = MYCOBOT_GRIPPER
        self.retry_attempts = max(1, int(retry_attempts))
        self.retry_delay_s = max(0.0, float(retry_delay_s))
        # 인스턴스 설정의 excluded_joints(예: ["4"])는 이미 매니페스트 id 그대로다.
        self.excluded_joints = set(excluded_joint_ids or [])
        self.exclude_j4 = "4" in self.excluded_joints
        # 도달 판정은 **부품 기술서가 정한다.** 코드에 1.0도를 박아 두었더니
        # 목표 50.00에 실제 52.20으로 선 팔이 '미도달'이 됐다(실측 로그).
        # M5 서보는 백래시가 있어 그 정도는 늘 남는다.
        settle = (descriptor or {}).get("settle") or {}
        self.settle_tolerance_deg = float(settle.get("tolerance_deg",
                                                     MYCOBOT_SETTLE_TOLERANCE_DEG))
        # 허용치 밖이지만 이만큼 안이면 '갔다'고 본다 — 사람이 이미 검증한
        # 자세를 몇 도 차이로 막지 않기 위해서다. 0이면 이 완화를 쓰지 않는다.
        self.near_enough_deg = float(settle.get("near_enough_deg", 0.0))

    @classmethod
    def from_resolved(cls, profile: dict[str, Any], instance: dict[str, Any]) -> "MyCobot280M5Adapter":
        connection = instance.get("connection") or {}
        device = connection.get("device_default")
        env_name = connection.get("device_env")
        if env_name:
            device = os.environ.get(env_name, device)
        return cls(
            device=device,
            transport=str(connection.get("transport") or "serial"),
            excluded_joint_ids=instance.get("excluded_joints") or [],
        )

    @staticmethod
    @contextmanager
    def _port_open_without_reset():
        """포트를 열 때 DTR을 올리지 않는다 — **이게 없으면 M5가 재부팅된다.**

        M5는 ESP32다. 리눅스에서 CDC-ACM 포트를 열면 기본으로 DTR이 올라가고,
        ESP32는 그것을 리셋 신호로 받는다. 그 순간 토크가 끊기고 **팔이 떨어진다.**
        런타임을 띄우거나 다시 띄울 때마다 팔이 죽던 이유가 이것이다.

        pymycobot은 rts만 내리고 dtr은 건드리지 않는다(mycobot280.py). 그래서
        포트를 여는 그 자리에서 dtr을 내려 준다. 아두이노 IDE가 하는 것과 같다.
        """
        try:
            import serial
        except Exception:
            yield
            return
        original = serial.Serial.open

        def open_without_reset(self):
            try:
                self.dtr = False        # 열기 전에 내려 두면 열 때 올라가지 않는다
            except Exception:
                pass
            return original(self)

        serial.Serial.open = open_without_reset
        try:
            yield
        finally:
            serial.Serial.open = original

    def __enter__(self) -> "MyCobot280M5Adapter":
        if self._mc is None:
            if self._sdk is not None:
                self._mc = self._sdk
            else:
                try:
                    if self.transport == "socket":
                        from pymycobot import MyCobot280Socket as MyCobot280  # type: ignore
                    else:
                        from pymycobot import MyCobot280  # type: ignore
                except Exception as exc:
                    raise RuntimeError(
                        "pymycobot이 설치되어 있지 않습니다; MyCobot 의존성을 먼저 설치하세요"
                    ) from exc
                with self._port_open_without_reset():
                    self._mc = (MyCobot280(self.device, self.baud)
                                if self.transport != "socket" else MyCobot280(self.device))
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._mc = None

    @property
    def mc(self) -> Any:
        if self._mc is None:
            raise RuntimeError("MyCobot280M5Adapter는 컨텍스트 매니저로 써야 합니다")
        return self._mc

    def _with_retry(
        self,
        fn: Callable[[], T],
        *,
        is_valid: Callable[[T], bool] = lambda _result: True,
    ) -> T:
        """SDK 호출을 몇 번 재시도한다.

        불안정한 USB 패스스루가 정상 세션 중에도 가끔 읽기/쓰기 하나를 놓칠 수
        있다 — 짧은 재시도로 이를 흡수해 가짜 실패를 호출부에 그대로 노출하지
        않는다.
        """
        last_exc: Exception | None = None
        last_result: T | None = None
        for attempt in range(self.retry_attempts):
            try:
                result = fn()
            except Exception as exc:
                last_exc = exc
                last_result = None
            else:
                last_exc = None
                last_result = result
                if is_valid(result):
                    return result
            if attempt < self.retry_attempts - 1 and self.retry_delay_s:
                time.sleep(self.retry_delay_s)
        if last_exc is not None:
            raise last_exc
        return last_result  # type: ignore[return-value]

    def _read_angles(self) -> list[float]:
        """관절 각도를 읽는다. 답이 없으면 **통신이 멎은 것으로 올린다.**

        pymycobot은 답 프레임을 못 받으면 값 대신 ``-1`` 하나를 돌려준다. 이것을
        "예상치 못한 값"으로 올리면 서버가 500으로 떨어지고, 화면에는 이유 없이
        "접속이 끊겼다"만 남는다 — 진짜 이유(로봇이 답하지 않는다)가 사라진다.
        OMX 어댑터는 통신 실패를 처음부터 HardwareConnectionLostError로 올리고
        있었고 MyCobot만 빠져 있었다. 같은 말로 맞춘다.

        이렇게 올리면 미세 이동·자세 실행·자세 읽기가 모두 이미 있는 단선 처리
        (사유 표시 → 되살리기 → 사람 확인 후 해제)를 그대로 탄다.
        """
        angles = self._with_retry(
            self.mc.get_angles,
            is_valid=lambda a: isinstance(a, (list, tuple)) and len(a) >= 6,
        )
        if not isinstance(angles, (list, tuple)) or len(angles) < 6:
            raise HardwareConnectionLostError(
                f"로봇이 관절 값을 돌려주지 않습니다 (응답 {angles!r}). "
                "로봇 전원, USB 연결, M5 화면이 실행 상태인지 확인하세요")
        return list(angles)

    def read_joint_positions(self) -> dict[str, int]:
        angles = self._read_angles()
        result = {name: _millideg(angles[i]) for i, name in enumerate(self.joint_names)}
        try:
            gripper = self._with_retry(
                self.mc.get_gripper_value,
                is_valid=lambda g: isinstance(g, (int, float)),
            )
        except Exception:
            gripper = None
        if isinstance(gripper, (int, float)):
            result[MYCOBOT_GRIPPER] = int(round(float(gripper)))
        return result

    def clamp(self, joint_name: str, target: int) -> int:
        if joint_name == MYCOBOT_GRIPPER:
            return max(GRIPPER_MIN, min(GRIPPER_MAX, int(target)))
        if joint_name not in self.joint_names:
            raise KeyError(f"알 수 없는 MyCobot 관절: {joint_name}")
        min_deg, max_deg = MYCOBOT_MEASURED_LIMITS_DEG[joint_name]
        return _millideg(max(min_deg, min(max_deg, _degree(int(target)))))

    def _speed(self, velocity: int) -> int:
        return max(1, min(100, int(velocity)))

    def read_temperatures(self) -> dict[str, float]:
        getter = getattr(self.mc, "get_servo_temps", None)
        if not callable(getter):
            return {}
        values = getter()
        if not isinstance(values, (list, tuple)):
            return {}
        return {
            str(i): float(value)
            for i, value in enumerate(values[:6], start=1)
            if isinstance(value, (int, float))
        }

    def _check_temperature_limits(self, limits: dict[str, float] | None) -> None:
        if not limits:
            return
        temperatures = self.read_temperatures()
        for name, temperature in temperatures.items():
            limit = limits.get(name)
            if limit is not None and temperature > float(limit):
                raise RuntimeError(f"{name} 온도 {temperature:g}C가 한계 {float(limit):g}C를 초과함")

    def _near_enough(self, errors: dict[str, float], targets: dict[str, int]) -> bool:
        """허용치는 넘었지만 '갔다'고 볼 만한가.

        멈춰 선 것과 몇 도 못 미친 것은 다르다. 앞엣것은 막아야 하고 뒤엣것은
        막을 이유가 없다 — 사람이 이미 해보고 쓰던 자세다.
        """
        if self.near_enough_deg <= 0 or len(errors) != len(targets):
            return False
        return all(error <= self.near_enough_deg for error in errors.values())

    def _wait_for_joint_targets(
        self,
        targets: dict[str, int],
        *,
        timeout_s: float = MYCOBOT_SETTLE_TIMEOUT_S,
    ) -> dict[str, Any]:
        """컨트롤러 read-back이 요청한 각도에 도달할 때까지 대기.

        send_angle은 비동기 명령이다 — 호출 직후 즉시 성공 처리하면 실제로는
        다른 각도에 머물러 있는데도 이동 완료로 보고하는 문제가 생긴다.
        """
        started = time.monotonic()
        deadline = started + max(0.0, float(timeout_s))
        last: dict[str, int] = {}
        best: float | None = None          # 지금까지 가장 가까웠던 거리
        best_at = started
        while True:
            last = self.read_joint_positions()
            errors = {
                name: abs(_degree(last.get(name, 0)) - _degree(target))
                for name, target in targets.items()
                if name in last
            }
            if len(errors) == len(targets) and all(
                error <= self.settle_tolerance_deg for error in errors.values()
            ):
                return {"settled": True, "actual_positions": last, "errors_deg": errors}

            now = time.monotonic()
            worst = max(errors.values()) if errors else float("inf")
            if best is None or worst < best - MYCOBOT_PROGRESS_EPS_DEG:
                best, best_at = worst, now
            elif now - best_at >= MYCOBOT_NO_PROGRESS_S:
                # 조금도 가까워지지 않는다 — 더 물어봐야 답은 같고 통신만 막힌다
                return {"settled": False, "actual_positions": last, "errors_deg": errors,
                        "near_enough": self._near_enough(errors, targets),
                        "gave_up": "no_progress"}
            if now >= deadline:
                return {"settled": False, "actual_positions": last, "errors_deg": errors,
                        "near_enough": self._near_enough(errors, targets)}
            time.sleep(MYCOBOT_SETTLE_POLL_S)

    def move_joints(
        self,
        targets: dict[str, int],
        *,
        velocity: int,
        acceleration: int,
        label: str,
        bypass_temperature_check: bool = False,
        temperature_limits_c: dict[str, float] | None = None,
        velocity_per_joint: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        del acceleration, label, bypass_temperature_check
        self._check_temperature_limits(temperature_limits_c)
        current = self.read_joint_positions()
        excluded_requested = self.excluded_joints & set(targets)
        if excluded_requested:
            raise ValueError(
                f"{sorted(excluded_requested)}는 이 개체에서 제외된 관절입니다 — 목표값 불허"
            )
        # 어댑터가 최종 안전 방어선이다 — 매니페스트/인스턴스 설정이 잘못되어도
        # 모든 호출자(저장된 카드/직접 API 호출 포함)가 실측범위로 클램프된다.
        normalized_targets: dict[str, int] = {}
        for name, target in targets.items():
            normalized_targets[name] = self.clamp(name, int(target))
        targets = normalized_targets
        speed = self._speed(velocity)
        velocity_per_joint = velocity_per_joint or {}
        # pymycobot의 send_angles(angles, speed)는 배치 이동 전체에 속도 하나만
        # 받는다 — 여러 관절에 서로 다른 속도를 진짜로 적용하는 유일한 방법은
        # 관절별 send_angle(id, degree, speed) 호출이다. 관절 제외 상태이거나
        # 관절별 속도가 실제로 다르게 지정된 경우에만 이 더 느린 경로를 쓴다
        # (검증 보고서 20260812: velocity_per_joint를 받으면서도 실제로는
        # 단일 velocity만 쓰던 버그).
        # **관절별 값은 상한이지 덮어쓰기가 아니다** (2026-09-20).
        # 전에는 여기서 관절별 값을 그대로 썼다. 출하 기본값이 전 관절 50이라
        # "느리게 가라"(10)가 50으로 나갔다 — 요청보다 빠르게 가는 일이
        # 안전 설정 때문에 일어났다. 계약이 뜻을 안 정해 OMX와 반대로 갔던
        # 자리이고, 이제 계약(effective_velocity)이 정한다.
        per_joint_speeds = {
            name: self._speed(effective_velocity(velocity, velocity_per_joint.get(name)))
            for name in targets
        }
        needs_per_joint_calls = bool(self.excluded_joints) or len(set(per_joint_speeds.values())) > 1
        if needs_per_joint_calls:
            # send_angle은 요청된 정상 관절만 주소를 지정한다. send_angles를 쓰면
            # 제외된 관절 채널까지 포함되므로 쓰지 않는다.
            send_angle = getattr(self.mc, "send_angle", None)
            if not callable(send_angle):
                raise RuntimeError("관절 제외 상태이거나 관절별 속도가 다른 경우 pymycobot.send_angle이 필요합니다")
            for name, target in targets.items():
                if name not in self.joint_names:
                    raise KeyError(f"알 수 없는 MyCobot 관절: {name}")
                joint_id = self.joint_names.index(name) + 1
                joint_speed = per_joint_speeds[name]
                self._with_retry(
                    lambda joint_id=joint_id, target=target, joint_speed=joint_speed: send_angle(
                        joint_id, _degree(target), joint_speed
                    )
                )
            verification = self._wait_for_joint_targets(targets)
            return {
                "success": bool(verification["settled"]),
                "settled": bool(verification["settled"]),
                "actual_positions": verification["actual_positions"],
                "errors_deg": verification["errors_deg"],
                "velocity_per_joint": per_joint_speeds,
                "excluded_joints": sorted(self.excluded_joints),
            }
        # per_joint_speeds가 전부 같으면(§needs_per_joint_calls가 False가 되는
        # 경우) 그 공통값을 배치 속도로 쓴다 — 요청측이 velocity_per_joint로
        # 지정한 값이 기본 velocity와 달라도 실제로 반영되게 한다.
        batch_speed = next(iter(per_joint_speeds.values()), speed) if per_joint_speeds else speed
        angles = [_degree(targets.get(name, current[name])) for name in self.joint_names]
        self._with_retry(lambda: self.mc.send_angles(angles, batch_speed))
        verification = self._wait_for_joint_targets(targets)
        return {
            "success": bool(verification["settled"]),
            "settled": bool(verification["settled"]),
            "actual_positions": verification["actual_positions"],
            "errors_deg": verification["errors_deg"],
            "angles_deg": angles,
            "velocity": batch_speed,
        }

    def move_gripper(
        self,
        target: int,
        *,
        velocity: int,
        acceleration: int,
        label: str,
        bypass_temperature_check: bool = False,
        temperature_limit_c: float | None = None,
    ) -> dict[str, Any]:
        """그리퍼를 target으로 이동.

        temperature_limit_c는 인자로 받지만 실제로 검사하지 않는다 —
        pymycobot의 이 M5 컨트롤러 계열에는 그리퍼 개별 온도를 읽는 API가
        없다(get_servo_temps()는 팔 6관절만 반환, 확인됨). 검사할 수 없는데
        검사한 것처럼 보이면 호출자를 오도하므로, 응답에
        temperature_check_supported: False를 명시한다 — 조용히 무시하지
        않는다(검증 보고서 20260812 지적).
        """
        del acceleration, label, bypass_temperature_check, temperature_limit_c
        value = self.clamp(MYCOBOT_GRIPPER, target)
        self._with_retry(lambda: self.mc.set_gripper_value(value, self._speed(velocity)))
        return {
            "success": True,
            "gripper": value,
            "velocity": self._speed(velocity),
            "temperature_check_supported": False,
        }

    def attest_parts(self) -> dict[str, dict[str, Any]]:
        """**팔은 말할 수 있고 손은 말할 수 없다.**

        이 컨트롤러가 주는 것은 컨트롤러 연결 여부와 팔 6관절 각도다.
        그리퍼에 대해 "붙어 있는가"를 묻는 수단이 preflight 경로에 없다
        (2026-09-20 확인). `get_gripper_value()`가 값을 돌려주기는 하지만,
        떼어낸 상태에서 무엇을 돌려주는지 **확인된 바 없다.** 확인되지 않은
        것을 근거로 쓰면 화면이 없는 사실을 말하게 된다.

        그래서 손은 `None`(확인 불가)으로 둔다. 실물 관측(정상·기구만 제거·
        전기적 분리·전원 차단)에서 어느 API가 무엇을 돌려주는지 기록한 뒤,
        가르는 수단이 있으면 그때 여기에 넣는다.
        """
        arm_ok: bool | None
        try:
            connected = self._with_retry(self.mc.is_controller_connected,
                                         is_valid=lambda c: c == 1)
            angles = self._with_retry(self.mc.get_angles,
                                      is_valid=lambda a: isinstance(a, (list, tuple))
                                      and len(a) >= 6)
            arm_ok = bool(connected == 1 and isinstance(angles, (list, tuple)))
        except Exception as exc:                   # noqa: BLE001
            arm_ok = False
            return {"arm": {"responding": False, "evidence": "controller",
                            "reason": f"{type(exc).__name__}: {exc}"},
                    "hand": {"responding": None, "evidence": "none",
                             "reason": "컨트롤러가 응답하지 않아 손도 알 수 없습니다"}}
        return {
            "arm": {"responding": arm_ok, "evidence": "controller",
                    "detail": {"controller_connected": connected}},
            "hand": {"responding": None, "evidence": "none",
                     "reason": "이 로봇은 손이 붙어 있는지 확인할 수단이 없습니다"},
        }

    def preflight(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "robot_model": self.robot_model,
            "device": self.device,
            "baud": self.baud,
            "read_only": True,
            "passed": False,
        }
        try:
            connected = self._with_retry(
                self.mc.is_controller_connected,
                is_valid=lambda c: c == 1,
            )
            result["controller_connected"] = connected
            angles = self._with_retry(
                self.mc.get_angles,
                is_valid=lambda a: isinstance(a, (list, tuple)) and len(a) >= 6,
            )
            if isinstance(angles, (list, tuple)):
                result["angles_deg"] = list(angles)
            else:
                result["angles_response"] = angles
                result["angles_read_ok"] = False
            allowed_errors = (0, None, 4) if self.exclude_j4 else (0, None)
            error = self._with_retry(
                self.mc.get_error_information,
                is_valid=lambda e: e in allowed_errors,
            )
            result["error_information"] = error
            j4_enabled = None
            if self.exclude_j4:
                j4_enabled_fn = getattr(self.mc, "is_servo_enable", None)
                j4_enabled = (
                    self._with_retry(
                        lambda: j4_enabled_fn(4),
                        is_valid=lambda value: value in (0, 1),
                    )
                    if callable(j4_enabled_fn)
                    else None
                )
                result["j4_servo_enabled"] = j4_enabled
                result["excluded_joints"] = sorted(self.excluded_joints)
            result["passed"] = (
                connected == 1
                and isinstance(angles, (list, tuple))
                and len(angles) >= 6
                and error in (0, None)
            ) or (
                self.exclude_j4
                and connected == 1
                and isinstance(angles, (list, tuple))
                and len(angles) >= 6
                and error == 4
                and j4_enabled == 0
            )
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    def recover_from_fault(self, *, may_reopen_link: bool = False) -> dict[str, Any]:
        """컨트롤러 오류를 지우고 서보를 다시 잡는다.

        MyCobot 컨트롤러는 관절 하나가 한계를 넘거나 응답하지 않으면 오류를
        걸고 **팔 전체 동작을 거부한다.** 그래서 복구는 두 가지를 본다.

            1. get_error_information() 오류 코드 지우기
            2. 서보가 실제로 잡혀 있는지 (응답 없는 서보는 여기서 드러난다)

        전선이 빠졌거나 서보가 죽은 것은 소프트웨어로 못 고친다 —
        어느 관절인지 정확히 알려주는 것까지가 여기 몫이다.

        **연결을 다시 여는 것은 여기서 가장 거친 수단이고, 기본값이 아니다.**
        포트를 열면 M5 컨트롤러가 DTR로 다시 부팅한다 — 그 순간 토크가 끊기고
        **팔이 떨어진다.** 오류 해제·서보 재장악·재개는 토크를 끊지 않으므로
        사람 없이 해도 되지만, 연결 다시 열기는 그렇지 않다. 그래서 부르는
        쪽이 명시적으로 허락할 때만 한다(may_reopen_link=True).
        """
        report: dict[str, Any] = {}
        # 컨트롤러가 -1만 돌려주면 통신이 멎은 것이다. 사람이 케이블을 다시 꽂는
        # 것과 같은 일을 해본다 — 연결을 닫고 다시 연다. 이미 통신이 죽었을 때만
        # 뜻이 있고, 살아 있는 팔에 하면 떨어뜨리는 짓이다.
        try:
            probe = self.mc.get_angles()
        except Exception:
            probe = None
        link_dead = not isinstance(probe, (list, tuple)) or len(probe) < 6
        if link_dead and not may_reopen_link:
            report["link_was_dead"] = True
            report["link_reopen_skipped"] = (
                "연결을 다시 열면 컨트롤러가 재부팅되어 팔이 떨어집니다 — "
                "사람이 확인한 뒤에만 합니다")
        if link_dead and may_reopen_link:
            report["link_was_dead"] = True
            self._mc = None
            time.sleep(1.0)
            try:
                self.__enter__()
                # 포트를 열면 M5 컨트롤러가 다시 부팅한다(DTR). 그동안은 -1만 온다 —
                # 한 번 읽어 보고 포기하면 살아 있는 로봇을 죽었다고 보고하게 된다.
                again = None
                for _ in range(6):
                    time.sleep(1.0)
                    try:
                        again = self.mc.get_angles()
                    except Exception:
                        again = None
                    if isinstance(again, (list, tuple)) and len(again) >= 6:
                        break
                report["link_after_reopen"] = again
                report["link_recovered"] = isinstance(again, (list, tuple)) and len(again) >= 6
            except Exception as exc:
                report["reopen_failed"] = f"{type(exc).__name__}: {exc}"
        try:
            report["error_information_before"] = self.mc.get_error_information()
        except Exception as exc:
            report["error_read_failed"] = f"{type(exc).__name__}: {exc}"
        clear = getattr(self.mc, "clear_error_information", None)
        if callable(clear):
            try:
                clear()
                time.sleep(0.5)
                report["error_information_after"] = self.mc.get_error_information()
            except Exception as exc:
                report["clear_failed"] = f"{type(exc).__name__}: {exc}"
        focus = getattr(self.mc, "focus_all_servos", None)
        if callable(focus):
            try:
                focus()
                time.sleep(0.5)
            except Exception as exc:
                report["focus_failed"] = f"{type(exc).__name__}: {exc}"
        # 정지(stop)의 짝은 재개(resume)다. 짝을 부르지 않으면 컨트롤러는
        # '멈춘 상태'로 남아 이후 모든 이동 명령을 조용히 무시한다 —
        # 긴급 정지를 누른 뒤 아무리 눌러도 안 움직이던 원인이 이것이다.
        resume = getattr(self.mc, "resume", None)
        if callable(resume):
            try:
                resume()
                time.sleep(0.3)
                report["resumed"] = True
            except Exception as exc:
                report["resume_failed"] = f"{type(exc).__name__}: {exc}"
        dead: list[str] = []
        for index, name in enumerate(self.joint_names, start=1):
            try:
                if not self.mc.is_servo_enable(index):
                    dead.append(name)
            except Exception:
                dead.append(name)
        report["servo_not_responding"] = dead
        if dead:
            report["hardware_note"] = (
                f"관절 {', '.join(dead)}의 서보가 응답하지 않습니다. "
                f"컨트롤러가 팔 동작 전체를 거부합니다 — 전선과 전원을 확인하세요")
        return report

    def stop(self) -> None:
        stop = getattr(self.mc, "stop", None)
        if callable(stop):
            stop()


__all__ = ["MyCobot280M5Adapter", "MYCOBOT_280_M5_BAUD", "MYCOBOT_ARM_JOINTS", "MYCOBOT_MEASURED_LIMITS_DEG"]
