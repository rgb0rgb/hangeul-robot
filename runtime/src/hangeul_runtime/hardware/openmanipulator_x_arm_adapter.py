"""OpenManipulator-X 어댑터 (ROBOTIS Dynamixel Protocol 2.0).

Dexter 프로젝트에서 실기로 검증된 저수준 프로토콜 로직(레지스터 읽기/쓰기 재시도,
하드웨어 오류 플래그 감지, 관절별 과열/과전류 감시, 정착 대기, 그리퍼 stall
감지)을 그대로 포팅했다. Dexter의 특정 스킬/작업 스키마에 묶여 있던 사전정의
동작(예: "J11을 +90도만 움직이는 스킬")은 포팅하지 않았다 — 그건 이 어댑터
계약과 무관한 상위 제품 로직이다.

이 어댑터는 고정된 5개 ID(11~14 팔, 15 그리퍼)를 전제한다 — ID 자동탐색이나
baud sweep은 하지 않는다.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import serial
from dynamixel_sdk import COMM_SUCCESS, GroupSyncWrite, PacketHandler, PortHandler

from hangeul_runtime.abstraction.robot_arm_adapter import (
    RobotArmAdapter,
    effective_velocity,
)
from hangeul_runtime.hardware_errors import HardwareConnectionLostError, InFlightSafetyViolationError

PROTOCOL_VERSION = 2.0
BAUD = 1_000_000
ARM_IDS = [11, 12, 13, 14]
GRIPPER_ID = 15
EXPECTED_IDS = (11, 12, 13, 14, 15)
SAFE_BASIC_POSE = {11: 2048, 12: 1150, 13: 2650, 14: 2048}

DEFAULT_TEMPERATURE_LIMIT_C = 70.0

ADDR_TORQUE_ENABLE = 64
ADDR_HARDWARE_ERROR = 70
ADDR_MIN_POSITION_LIMIT = 52
ADDR_MAX_POSITION_LIMIT = 48
ADDR_PROFILE_ACCELERATION = 108
ADDR_PROFILE_VELOCITY = 112
ADDR_GOAL_POSITION = 116
ADDR_MOVING = 122
ADDR_PRESENT_CURRENT = 126
ADDR_PRESENT_VELOCITY = 128
ADDR_PRESENT_POSITION = 132
ADDR_PRESENT_INPUT_VOLTAGE = 144
ADDR_PRESENT_TEMPERATURE = 146

TICKS_PER_DEGREE = 4096.0 / 360.0
POSITION_TOLERANCE_TICKS = 45
MAX_STAGED_TEMPERATURE_C = 70
MAX_STAGED_ABS_CURRENT_RAW = 250
# J13(팔꿈치)은 자중 정적 부하가 커서 다른 관절보다 낮은 상시 한계를 쓴다. 짧은
# 순간(141~150)은 정상 프로파일 동작 중에도 나올 수 있어 허용하되, 그보다 크거나
# 141 이상이 3연속이면 차단한다.
J13_STRICT_CURRENT_LIMIT_RAW = 140
J13_TRANSIENT_CURRENT_LIMIT_RAW = 150
J13_OVERCURRENT_CONSECUTIVE_SAMPLES = 3

# 통신 잡음으로 깨진 값(예: 전류 30682)을 실제 위험으로 오인하지 않기 위한
# "물리적으로 불가능한" 영역 — 안전 임계값 자체를 낮추는 게 아니라 이 영역만
# 재확인한다.
IMPLAUSIBLE_CURRENT_RAW = 2000
IMPLAUSIBLE_TEMPERATURE_C = 120
IMPLAUSIBLE_PRESENT_POSITION_ABS = 1_000_000

MIN_STAGED_INPUT_VOLTAGE_RAW = 90
MAX_STAGED_INPUT_VOLTAGE_RAW = 150
DYNAMIXEL_PACKET_ERROR_ALERT = 0x80
DYNAMIXEL_HARDWARE_ERROR_FLAGS = {
    1: "input_voltage",
    4: "overheating",
    8: "motor_encoder",
    16: "electrical_shock",
    32: "overload",
}

GRIPPER_ALLOWED_WRITE_ADDRS: frozenset = frozenset({
    ADDR_TORQUE_ENABLE,
    ADDR_PROFILE_ACCELERATION,
    ADDR_PROFILE_VELOCITY,
    ADDR_GOAL_POSITION,
})
# 물리 절대 상한(캘리브레이션 아님) — 운영 정책값은 인스턴스 설정/안전범위
# 파일에서 관리한다. 이 값은 그 정책이 어떻든 절대 넘지 않는 최종 방어선이다.
GRIPPER_HW_TICKS_MIN_SAFETY = 270
GRIPPER_HW_TICKS_MAX_SAFETY = 3000
GRIPPER_GOAL_POSITION_TOLERANCE = 25
GRIPPER_CURRENT_STALL_THRESHOLD = 150
GRIPPER_SETTLE_TIMEOUT_S = 4.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_device_string(device: str) -> None:
    """장치 문자열의 기본적인 안전성만 확인한다.

    Dexter 원본의 "정확히 이 하나의 물리 동글" 화이트리스트(USB 벤더/제품 ID
    대조)는 포팅하지 않았다 — 그건 Dexter 자신의 재고 관리에 묶인 정책이라 Beom의
    일반 어댑터 계약과 무관하다. 대신 자동탐색/브루트포스 표현을 막는 최소한의
    형식 검사만 유지한다.
    """
    value = device.strip()
    if not value:
        raise LimitedAdapterError("device 문자열이 필요합니다")
    if any(token in value for token in ("*", "?", ",", " ", "[", "]")):
        raise LimitedAdapterError("자동 탐색/브루트포스 표현식은 허용하지 않습니다")


class LimitedAdapterError(RuntimeError):
    """제한된 하드웨어 어댑터의 게이트 실패."""


def _decode_hardware_error_flags(value: int | None) -> list[str]:
    if value is None:
        return []
    return [name for bit, name in DYNAMIXEL_HARDWARE_ERROR_FLAGS.items() if int(value) & bit]


def classify_joint_current_limit(
    dxl_id: int,
    current: int | None,
    consecutive_over_strict: int = 0,
    limits: dict[str, Any] | None = None,
) -> tuple[bool, int, int]:
    """(차단여부, 다음_연속카운트, 보고된_한계)를 반환.

    **한계값은 부품 기술서가 정한다**(current_limits). 코드에 박아 두면 팔마다
    다른 값을 줄 수 없고, 값 하나 바꾸는 데 코드를 고쳐야 한다.

    J13은 정적 부하를 가장 많이 받는데 한계가 140으로 **가장 낮게** 잡혀 있었다.
    그래서 정상 자세에서도 141~150이 나와 3연속이면 긴급 정지가 걸렸다
    (실측 2026-08-19: 144에서 차단). 방향이 거꾸로였다.

    strict를 넘은 것이 연속으로 이어지면 차단하고, transient를 넘으면 그 자리에서
    차단한다. 순간의 튐과 계속되는 과부하를 가른다.
    """
    limits = limits or {}
    default = int(limits.get("default_raw", MAX_STAGED_ABS_CURRENT_RAW))
    per_joint = (limits.get("per_joint_raw") or {}).get(str(dxl_id)) or {}
    strict = int(per_joint.get("strict", default))
    transient = int(per_joint.get("transient", strict))
    samples = int(limits.get("consecutive_samples", J13_OVERCURRENT_CONSECUTIVE_SAMPLES))

    if current is None:
        return False, 0, strict

    abs_current = abs(int(current))
    if abs_current > transient:
        return True, consecutive_over_strict + 1, transient
    if abs_current > strict:
        next_count = consecutive_over_strict + 1
        return next_count >= samples, next_count, strict
    return False, 0, strict


@dataclass
class LimitedWriteAuditEntry:
    sdk_call: str
    dxl_id: int | None = None
    address: int | None = None
    value: int | None = None
    completed: bool = False
    communication_result: int | None = None
    packet_error: int | None = None
    blocked_reason: str | None = None
    timestamp: str = field(default_factory=now_iso)


class OpenManipulatorXArmAdapter(RobotArmAdapter):
    """RobotArmAdapter 계약을 직접 구현하는 OpenManipulator-X 어댑터."""

    robot_model = "openmanipulator_x"

    def __init__(self, device: str, descriptor: dict[str, Any] | None = None) -> None:
        _validate_device_string(device)
        self.device = device
        # 전류 한계는 기술서가 들고 있다. 없으면 예전 값 그대로 간다.
        self.current_limits = dict((descriptor or {}).get("current_limits") or {})
        self.joint_names = [str(jid) for jid in ARM_IDS]
        self.gripper_joint_name = str(GRIPPER_ID)
        self.port: Any | None = None
        self.packet: Any | None = None
        self.audit: list[LimitedWriteAuditEntry] = []

    @classmethod
    def from_resolved(cls, profile: dict[str, Any], instance: dict[str, Any]) -> "OpenManipulatorXArmAdapter":
        import os as _os

        connection = instance.get("connection") or {}
        device = connection.get("device_default")
        env_name = connection.get("device_env")
        if env_name:
            device = _os.environ.get(env_name, device)
        return cls(device=device)

    def _record(self, sdk_call: str, dxl_id: int | None = None, address: int | None = None, value: int | None = None) -> LimitedWriteAuditEntry:
        entry = LimitedWriteAuditEntry(sdk_call=sdk_call, dxl_id=dxl_id, address=address, value=value)
        self.audit.append(entry)
        return entry

    # ── 연결 ────────────────────────────────────────────────────
    # 포트 상호배제는 robot_session.open_robot()이 device_lock_key로 소유한다
    # (§설계문서 robot_session.py 표준 진입점) — 여기서 다시 같은 키로 자체
    # 잠그면 같은 프로세스 내 flock 재진입 불허 규칙에 걸려 매번
    # HardwarePortBusyError로 스스로를 막아버린다(실기 확인, 2026-08-13:
    # OMX는 등록 이후 모든 하드웨어 호출이 이 이중 잠금으로 항상 실패했다).
    def open(self) -> None:
        self.port = PortHandler(self.device)
        self.packet = PacketHandler(PROTOCOL_VERSION)
        open_entry = self._record("openPort")
        try:
            opened = self.port.openPort()
        except (OSError, serial.SerialException) as e:
            raise HardwareConnectionLostError(f"포트 열기 실패: {e}")
        open_entry.completed = bool(opened)
        if not open_entry.completed:
            open_entry.blocked_reason = "port_open_failed"
            raise HardwareConnectionLostError(f"고정 장치 {self.device} 열기 실패")
        baud_entry = self._record("setBaudRate")
        try:
            baud_set = self.port.setBaudRate(BAUD)
        except (OSError, serial.SerialException) as e:
            raise HardwareConnectionLostError(f"baud rate 설정 실패: {e}")
        baud_entry.completed = bool(baud_set)
        if not baud_entry.completed:
            baud_entry.blocked_reason = "baud_set_failed"
            raise HardwareConnectionLostError(f"고정 baud {BAUD} 설정 실패")

    def close(self) -> None:
        if self.port is None:
            return
        entry = self._record("closePort")
        try:
            self.port.closePort()
            entry.completed = True
        finally:
            self.port = None
            self.packet = None

    def __enter__(self) -> "OpenManipulatorXArmAdapter":
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def _require_open(self) -> None:
        if self.port is None or self.packet is None:
            raise LimitedAdapterError("어댑터가 열려 있지 않습니다")

    # ── 저수준 레지스터 I/O (재시도 포함) ───────────────────────
    def ping(self, dxl_id: int) -> dict[str, Any]:
        self._require_open()
        if dxl_id not in EXPECTED_IDS:
            raise LimitedAdapterError("고정 11-15 집합 밖의 ID")
        entry = self._record("ping", dxl_id=dxl_id)
        try:
            model, comm, err = self.packet.ping(self.port, dxl_id)
        except (OSError, serial.SerialException) as e:
            raise HardwareConnectionLostError(f"Ping 실패: {e}")
        entry.completed = True
        entry.communication_result = comm
        entry.packet_error = err
        if comm != COMM_SUCCESS:
            raise HardwareConnectionLostError(f"ID {dxl_id} ping 실패, comm={comm}")
        return {"id": dxl_id, "responded": comm == COMM_SUCCESS and err == 0, "model_number": model if comm == COMM_SUCCESS and err == 0 else None}

    def read_reg(self, dxl_id: int, addr: int, length: int, *, signed: bool = False, tries: int = 5) -> int | None:
        self._require_open()
        if dxl_id not in EXPECTED_IDS:
            raise LimitedAdapterError("고정 11-15 집합 밖의 ID")
        method = {1: "read1ByteTxRx", 2: "read2ByteTxRx", 4: "read4ByteTxRx"}[length]
        entry = self._record(method, dxl_id=dxl_id, address=addr)
        last_comm = COMM_SUCCESS
        last_packet_error = 0
        last_raw: Optional[int] = None
        last_error: Optional[str] = None
        for _ in range(tries):
            try:
                raw, comm, err = getattr(self.packet, method)(self.port, dxl_id, addr)
            except (OSError, serial.SerialException) as e:
                raise HardwareConnectionLostError(f"레지스터 읽기 실패: {e}")
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                time.sleep(0.04)
                continue
            entry.communication_result = comm
            entry.packet_error = err
            last_comm = comm
            last_packet_error = err
            last_raw = int(raw)
            if comm == COMM_SUCCESS and err == 0:
                entry.completed = True
                value = int(raw)
                if signed and length == 2:
                    value &= 0xFFFF
                    return value - 0x10000 if value & 0x8000 else value
                if signed and length == 4:
                    value &= 0xFFFFFFFF
                    return value - 0x100000000 if value & 0x80000000 else value
                return value
            if comm == COMM_SUCCESS and addr == ADDR_HARDWARE_ERROR and (err & DYNAMIXEL_PACKET_ERROR_ALERT):
                entry.completed = True
                return int(raw)
            time.sleep(0.04)
        detail = f"레지스터 읽기 재시도 후 실패: comm={last_comm}, packet_error={last_packet_error}"
        if last_packet_error & DYNAMIXEL_PACKET_ERROR_ALERT:
            detail += " (hardware_alert)"
            # 어떤 레지스터를 읽으려다 실패했든, 얼럿 비트가 섰다는 건 이
            # dxl_id의 하드웨어 오류 상태 레지스터가 0이 아니라는 뜻이다.
            # 실패한 레지스터가 ADDR_HARDWARE_ERROR 자신이 아니었다면(가장 흔한
            # 경우 — 예: 위치를 읽으려다 실패), 어떤 오류인지 알려주지 않고
            # "hardware_alert"라고만 뜨면 운영자가 원인을 알 길이 없다. 별도로
            # 한 번 더 읽어 디코딩한다(이 보조 읽기 자체가 실패해도 무시 —
            # 원래 오류를 가리지 않는다).
            hw_err_raw = last_raw if addr == ADDR_HARDWARE_ERROR else None
            if hw_err_raw is None:
                try:
                    hw_err_raw = self.read_reg(dxl_id, ADDR_HARDWARE_ERROR, 1)
                except Exception:
                    hw_err_raw = None
            if hw_err_raw is not None:
                flags = _decode_hardware_error_flags(hw_err_raw)
                detail += f", hardware_error={hw_err_raw}" + (f" flags={flags}" if flags else "")
        raise HardwareConnectionLostError(detail + (f", last_error={last_error}" if last_error else ""))

    def recover_from_fault(self) -> dict[str, Any]:
        """오류 상태 레지스터(ADDR_HARDWARE_ERROR)가 0이 아닌 관절을 REBOOT
        인스트럭션으로 재초기화한다 (RobotArmAdapter 선택 훅 구현).

        Dynamixel Protocol 2.0에서 REBOOT은 서보의 로직/오류 상태를
        재초기화하는 표준 절차다(목표 위치나 캘리브레이션은 잃지 않는다) —
        재시도만으로는 풀리지 않는 하드웨어 오류 래치(과부하/과열/전압/
        엔코더/충격)에 이 방법을 쓴다. `write_reg()`의 관절 화이트리스트
        (팔 11-14, 그리퍼 쓰기 불가)와 무관하게 그리퍼(15)를 포함한 모든
        관절에 시도한다 — REBOOT은 목표위치 쓰기가 아니라 별도의 유지보수
        인스트럭션이기 때문이다.

        실기 검증 참고: 이 세션에서는 개발 환경의 하드웨어 연결이 끊겨
        REBOOT 자체를 실제 서보에 대고 검증하지 못했다 — pymycobot이 아닌
        dynamixel_sdk의 표준 절차를 그대로 따른 것이며, 로직 단위테스트만
        통과했다. 실기에서 최초 발생 시 결과를 확인해야 한다.
        """
        self._require_open()
        report: dict[str, Any] = {}
        for dxl_id in EXPECTED_IDS:
            entry: dict[str, Any] = {"hardware_error_before": None, "rebooted": False, "hardware_error_after": None}
            try:
                entry["hardware_error_before"] = self.read_reg(dxl_id, ADDR_HARDWARE_ERROR, 1)
            except Exception as e:  # noqa: BLE001 — 진단 목적, 한 관절 실패가 나머지를 막으면 안 된다
                entry["read_before_error"] = f"{type(e).__name__}: {e}"
                report[dxl_id] = entry
                continue
            if not entry["hardware_error_before"]:
                report[dxl_id] = entry
                continue
            try:
                comm, err = self.packet.reboot(self.port, dxl_id)
                entry["rebooted"] = comm == COMM_SUCCESS
                entry["reboot_comm"] = comm
                entry["reboot_packet_error"] = err
            except Exception as e:  # noqa: BLE001
                entry["reboot_error"] = f"{type(e).__name__}: {e}"
            time.sleep(0.3)  # 재부팅 후 서보가 다시 응답하기까지 여유를 준다
            try:
                entry["hardware_error_after"] = self.read_reg(dxl_id, ADDR_HARDWARE_ERROR, 1)
            except Exception as e:  # noqa: BLE001
                entry["read_after_error"] = f"{type(e).__name__}: {e}"
            report[dxl_id] = entry
        return report

    def write_reg(self, dxl_id: int, addr: int, length: int, value: int, *, tries: int = 3) -> bool:
        self._require_open()
        if dxl_id not in ARM_IDS:
            raise LimitedAdapterError("제한 어댑터 쓰기는 팔 ID 11-14만 허용합니다")
        if addr not in {ADDR_TORQUE_ENABLE, ADDR_PROFILE_ACCELERATION, ADDR_PROFILE_VELOCITY, ADDR_GOAL_POSITION}:
            raise LimitedAdapterError("허용 목록에 없는 쓰기 레지스터")
        method = {1: "write1ByteTxRx", 4: "write4ByteTxRx"}[length]
        entry = self._record(method, dxl_id=dxl_id, address=addr, value=int(value))
        last_comm = COMM_SUCCESS
        last_error: Optional[str] = None
        for _ in range(tries):
            try:
                comm, err = getattr(self.packet, method)(self.port, dxl_id, addr, int(value) & (0xFF if length == 1 else 0xFFFFFFFF))
            except (OSError, serial.SerialException) as e:
                raise HardwareConnectionLostError(f"레지스터 쓰기 실패: {e}")
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                time.sleep(0.04)
                continue
            entry.communication_result = comm
            entry.packet_error = err
            last_comm = comm
            if comm == COMM_SUCCESS and err == 0:
                entry.completed = True
                return True
            time.sleep(0.04)
        raise HardwareConnectionLostError(
            f"레지스터 쓰기 재시도 후 실패: comm={last_comm}" + (f", last_error={last_error}" if last_error else "")
        )

    def _read_plausible(
        self,
        dxl_id: int,
        addr: int,
        length: int,
        *,
        signed: bool,
        implausible_abs_max: float,
        retries: int = 2,
    ) -> Optional[int]:
        """물리적으로 불가능한 값(예: 전류 30682)이면 통신 잡음으로 의심해 재확인."""
        value = self.read_reg(dxl_id, addr, length, signed=signed)
        attempt = 0
        while value is not None and abs(value) > implausible_abs_max and attempt < retries:
            time.sleep(0.05)
            value = self.read_reg(dxl_id, addr, length, signed=signed)
            attempt += 1
        return value

    def _read_present_position_plausible(self, dxl_id: int, *, retries: int = 5) -> Optional[int]:
        value = self.read_reg(dxl_id, ADDR_PRESENT_POSITION, 4, signed=True)
        attempt = 0
        while value is not None and abs(int(value)) > IMPLAUSIBLE_PRESENT_POSITION_ABS and attempt < retries:
            time.sleep(0.05)
            value = self.read_reg(dxl_id, ADDR_PRESENT_POSITION, 4, signed=True)
            attempt += 1
        if value is not None and abs(int(value)) > IMPLAUSIBLE_PRESENT_POSITION_ABS:
            raise HardwareConnectionLostError(f"J{dxl_id} 위치 읽기값이 물리적으로 불가능함: {value}")
        return value

    # ── RobotArmAdapter 계약 ────────────────────────────────────
    def component(self, dxl_id: int) -> dict[str, Any]:
        position = self._read_present_position_plausible(dxl_id)
        return {
            "id": dxl_id,
            "position": position,
            "position_error": (
                abs(position - SAFE_BASIC_POSE[dxl_id])
                if position is not None and dxl_id in SAFE_BASIC_POSE else None
            ),
            "moving": self.read_reg(dxl_id, ADDR_MOVING, 1),
            "hardware_error": self.read_reg(dxl_id, ADDR_HARDWARE_ERROR, 1),
            "present_current": self._read_plausible(dxl_id, ADDR_PRESENT_CURRENT, 2, signed=True, implausible_abs_max=IMPLAUSIBLE_CURRENT_RAW),
            "present_velocity": self.read_reg(dxl_id, ADDR_PRESENT_VELOCITY, 4, signed=True),
            "present_input_voltage": self.read_reg(dxl_id, ADDR_PRESENT_INPUT_VOLTAGE, 2),
            "temperature_c": self._read_plausible(dxl_id, ADDR_PRESENT_TEMPERATURE, 1, signed=False, implausible_abs_max=IMPLAUSIBLE_TEMPERATURE_C),
            "torque_enable": self.read_reg(dxl_id, ADDR_TORQUE_ENABLE, 1),
        }

    def snapshot(self, label: str) -> dict[str, Any]:
        return {
            "source": "beom_openmanipulator_x_adapter",
            "label": label,
            "read_at": now_iso(),
            "robot_model": self.robot_model,
            "servo_ids": list(EXPECTED_IDS),
            "hardware_read": True,
            "components": [self.component(dxl_id) for dxl_id in EXPECTED_IDS],
        }

    def attest_parts(self) -> dict[str, dict[str, Any]]:
        """ID별 ping이 있으므로 **팔과 손을 따로 말할 수 있다.**

        버스가 통째로 죽은 것과 부품 하나가 사라진 것은 다르다. 전부 무응답이면
        그것은 포트·전원 문제이지 "손이 없다"가 아니다 — 원인을 단정하지 않고
        **관측한 사실만** 올린다. 넓게 막는 판단은 호출부가 한다.
        """
        pings = {}
        for dxl_id in EXPECTED_IDS:
            try:
                pings[dxl_id] = bool(self.ping(dxl_id).get("responded"))
            except Exception:                      # noqa: BLE001 — 무응답도 사실이다
                pings[dxl_id] = False
        arm_ok = [pings.get(i, False) for i in ARM_IDS]
        hand_ok = pings.get(GRIPPER_ID, False)
        none_responded = not any(pings.values())
        detail = {str(k): v for k, v in pings.items()}
        if none_responded:
            reason = "어느 관절도 응답하지 않습니다 — 포트·전원·배선을 먼저 봅니다"
            return {"arm": {"responding": False, "evidence": "ping",
                            "reason": reason, "detail": detail, "all_silent": True},
                    "hand": {"responding": False, "evidence": "ping",
                             "reason": reason, "detail": detail, "all_silent": True}}
        return {
            "arm": {"responding": all(arm_ok), "evidence": "ping", "detail": detail},
            "hand": {"responding": hand_ok, "evidence": "ping",
                     "detail": {str(GRIPPER_ID): hand_ok}},
        }

    def preflight(self) -> dict[str, Any]:
        pings = [self.ping(dxl_id) for dxl_id in EXPECTED_IDS]
        snapshot = self.snapshot("hardware_preflight")
        hardware_errors = [
            item for item in snapshot["components"]
            if item.get("hardware_error") not in (0, None)
        ]
        return {
            "pings": pings,
            "all_expected_ids_responded": all(item["responded"] for item in pings),
            "hardware_errors": hardware_errors,
            "passed": all(item["responded"] for item in pings) and not hardware_errors,
            "snapshot": snapshot,
        }

    def read_joint_positions(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for jid in [*ARM_IDS, GRIPPER_ID]:
            val = self.read_reg(jid, ADDR_PRESENT_POSITION, 4, signed=True)
            if val is not None:
                out[str(jid)] = val
        return out

    def clamp(self, joint_name: str, target: int) -> int:
        dxl_id = int(joint_name)
        if dxl_id == GRIPPER_ID:
            return max(GRIPPER_HW_TICKS_MIN_SAFETY, min(GRIPPER_HW_TICKS_MAX_SAFETY, int(target)))
        lo = self.read_reg(dxl_id, ADDR_MIN_POSITION_LIMIT, 4)
        hi = self.read_reg(dxl_id, ADDR_MAX_POSITION_LIMIT, 4)
        if lo is None or hi is None:
            raise LimitedAdapterError(f"id_{dxl_id}_limit_unreadable")
        return max(int(lo) + 10, min(int(hi) - 10, int(target)))

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
        """지정한 팔 관절(그리퍼 제외)을 동시에 목표로 이동.

        bypass_temperature_check: ESTOP/pause-hold의 "지금 위치를 목표로 다시
        써서 그 자리에 고정" 호출에만 True를 넘긴다 — 새 동작이 아니라 정지
        의도이기 때문이다. 하드웨어 오류 플래그/전류초과/끼임 감지는 이 경우에도
        그대로 유지된다. 일반 동작 호출은 이 플래그를 절대 넘기지 않는다.
        """
        self._require_open()
        int_targets = {int(name): val for name, val in targets.items()}
        temperature_limits_c = (
            {int(name): val for name, val in temperature_limits_c.items()}
            if temperature_limits_c is not None else {}
        )
        velocity_per_joint = (
            {int(name): val for name, val in velocity_per_joint.items()}
            if velocity_per_joint is not None else {}
        )
        if any(dxl_id not in ARM_IDS for dxl_id in int_targets):
            raise LimitedAdapterError("move_joints 목표에 팔 ID가 아닌 항목이 있음")
        clamped = {dxl_id: self.clamp(str(dxl_id), target) for dxl_id, target in int_targets.items()}
        before = {dxl_id: self._read_present_position_plausible(dxl_id) for dxl_id in clamped}
        for dxl_id in clamped:
            self.write_reg(dxl_id, ADDR_TORQUE_ENABLE, 1, 1)
            self.write_reg(dxl_id, ADDR_PROFILE_ACCELERATION, 4, acceleration)
            # 관절별 값은 **상한이지 덮어쓰기가 아니다.** 전에는 per-joint 값이
            # 있으면 요청 속도를 통째로 갈아치웠다 — 제한이 40인데 10으로 천천히
            # 가라고 해도 40으로 갔다. 느리게 가라는 요청을 빠르게 바꾸는 것은
            # 안전 설정이 할 일이 아니다.
            capped = effective_velocity(velocity, velocity_per_joint.get(dxl_id))
            self.write_reg(dxl_id, ADDR_PROFILE_VELOCITY, 4, capped)

        entry = self._record("GroupSyncWrite", address=ADDR_GOAL_POSITION)
        comm = None
        last_error: Optional[str] = None
        for _ in range(3):
            gw = GroupSyncWrite(self.port, self.packet, ADDR_GOAL_POSITION, 4)
            for dxl_id, target in clamped.items():
                value = int(target) & 0xFFFFFFFF
                if not gw.addParam(dxl_id, [value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF, (value >> 24) & 0xFF]):
                    entry.blocked_reason = f"addParam failed for id {dxl_id}"
                    raise LimitedAdapterError(entry.blocked_reason)
            try:
                comm = gw.txPacket()
            except (OSError, serial.SerialException) as e:
                raise HardwareConnectionLostError(f"GroupSyncWrite 실패: {e}")
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                gw.clearParam()
                time.sleep(0.04)
                continue
            gw.clearParam()
            if comm == COMM_SUCCESS:
                break
            time.sleep(0.04)
        entry.completed = comm == COMM_SUCCESS
        entry.communication_result = comm
        if comm != COMM_SUCCESS:
            raise HardwareConnectionLostError(
                f"GroupSyncWrite 재시도 후 실패: comm={comm}" + (f", last_error={last_error}" if last_error else "")
            )

        final = dict(before)
        position_history: dict[int, list[int]] = {dxl_id: [] for dxl_id in clamped}
        overcurrent_counts = {dxl_id: 0 for dxl_id in clamped}
        deadline = time.time() + 12
        while time.time() < deadline:
            settled = True
            for dxl_id, target in clamped.items():
                pos = self._read_present_position_plausible(dxl_id)
                moving = self.read_reg(dxl_id, ADDR_MOVING, 1)
                final[dxl_id] = pos
                if pos is None:
                    settled = False
                    continue

                hw_err = self.read_reg(dxl_id, ADDR_HARDWARE_ERROR, 1)
                if hw_err not in (0, None):
                    flags = _decode_hardware_error_flags(hw_err)
                    suffix = f" flags={flags}" if flags else ""
                    raise InFlightSafetyViolationError(f"J{dxl_id} 하드웨어 오류 플래그 발생 ({hw_err}){suffix}")

                temp = self._read_plausible(dxl_id, ADDR_PRESENT_TEMPERATURE, 1, signed=False, implausible_abs_max=IMPLAUSIBLE_TEMPERATURE_C)
                temp_limit = temperature_limits_c.get(dxl_id, DEFAULT_TEMPERATURE_LIMIT_C)
                if not bypass_temperature_check and temp is not None and temp > temp_limit:
                    raise InFlightSafetyViolationError(f"J{dxl_id} 온도 {temp}C가 한계 {temp_limit}C 초과")

                current = self._read_plausible(dxl_id, ADDR_PRESENT_CURRENT, 2, signed=True, implausible_abs_max=IMPLAUSIBLE_CURRENT_RAW)
                blocked_current, next_count, reported_limit = classify_joint_current_limit(
                    dxl_id, current, overcurrent_counts.get(dxl_id, 0), self.current_limits
                )
                overcurrent_counts[dxl_id] = next_count
                if current is not None and blocked_current:
                    raise InFlightSafetyViolationError(f"J{dxl_id} 전류 {abs(int(current))}가 한계 {reported_limit} 초과")

                position_history[dxl_id].append(pos)
                if len(position_history[dxl_id]) > 3:
                    position_history[dxl_id].pop(0)
                if len(position_history[dxl_id]) == 3 and abs(pos - target) > 100:
                    readings = position_history[dxl_id]
                    if max(readings) - min(readings) <= 5:
                        raise InFlightSafetyViolationError(f"J{dxl_id} 끼임/정지 의심 (pos={pos}, target={target}, history={readings})")

                if moving != 0 or abs(pos - target) > POSITION_TOLERANCE_TICKS:
                    settled = False
            if settled:
                break
            time.sleep(0.1)
        settled = all(
            pos is not None and abs(pos - clamped[dxl_id]) <= POSITION_TOLERANCE_TICKS
            for dxl_id, pos in final.items()
        )
        return {
            # success는 반드시 명시한다 — 서버 라우팅이 {"success": True, **result}로
            # 감싸므로, 이 키가 없으면 목표 미도달(settled=False)이어도 상위 API가
            # 성공으로 보고한다(Codex 검증 20260812 발견).
            "success": settled,
            "label": label,
            "targets": clamped,
            "initial": before,
            "final": final,
            "sent": comm == COMM_SUCCESS,
            "settled": settled,
        }

    def gripper_write_reg(self, addr: int, length: int, value: int) -> bool:
        self._require_open()
        if addr not in GRIPPER_ALLOWED_WRITE_ADDRS:
            raise LimitedAdapterError(f"그리퍼 쓰기 주소 {addr}는 허용 목록에 없음")
        if addr == ADDR_GOAL_POSITION:
            val = int(value)
            if not (GRIPPER_HW_TICKS_MIN_SAFETY <= val <= GRIPPER_HW_TICKS_MAX_SAFETY):
                raise LimitedAdapterError(
                    f"그리퍼 목표 {val}이 안전범위 [{GRIPPER_HW_TICKS_MIN_SAFETY}, {GRIPPER_HW_TICKS_MAX_SAFETY}] 밖입니다"
                )
        method = {1: "write1ByteTxRx", 4: "write4ByteTxRx"}[length]
        entry = self._record(method, dxl_id=GRIPPER_ID, address=addr, value=int(value))
        try:
            comm, err = getattr(self.packet, method)(
                self.port, GRIPPER_ID, addr, int(value) & (0xFF if length == 1 else 0xFFFFFFFF),
            )
        except (OSError, serial.SerialException) as e:
            raise HardwareConnectionLostError(f"그리퍼 레지스터 쓰기 실패: {e}")
        entry.communication_result = comm
        entry.packet_error = err
        entry.completed = comm == COMM_SUCCESS and err == 0
        if comm != COMM_SUCCESS:
            raise HardwareConnectionLostError(f"그리퍼 레지스터 쓰기 실패, comm={comm}")
        return entry.completed

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
        """J15를 target으로 이동. 정지 판정에는 접촉 stall 감지를 쓴다 — 하드
        스톱에 닿아도 재시도하지 않고 즉시 종료한다(그리퍼는 팔과 달리 접촉이
        정상 동작의 일부다)."""
        self._require_open()
        clamped = max(GRIPPER_HW_TICKS_MIN_SAFETY, min(GRIPPER_HW_TICKS_MAX_SAFETY, int(target)))
        position_clamped = clamped != int(target)

        before_pos = self.read_reg(GRIPPER_ID, ADDR_PRESENT_POSITION, 4, signed=True)
        before_current = self.read_reg(GRIPPER_ID, ADDR_PRESENT_CURRENT, 2, signed=True)

        self.gripper_write_reg(ADDR_TORQUE_ENABLE, 1, 1)
        self.gripper_write_reg(ADDR_PROFILE_ACCELERATION, 4, acceleration)
        self.gripper_write_reg(ADDR_PROFILE_VELOCITY, 4, velocity)
        self.gripper_write_reg(ADDR_GOAL_POSITION, 4, clamped)

        start_t = time.time()
        deadline = start_t + GRIPPER_SETTLE_TIMEOUT_S
        final_pos = before_pos
        final_current = before_current
        stall_detected = False
        settled = False

        while time.time() < deadline:
            pos = self.read_reg(GRIPPER_ID, ADDR_PRESENT_POSITION, 4, signed=True)
            moving = self.read_reg(GRIPPER_ID, ADDR_MOVING, 1)
            current = self._read_plausible(GRIPPER_ID, ADDR_PRESENT_CURRENT, 2, signed=True, implausible_abs_max=IMPLAUSIBLE_CURRENT_RAW)
            if pos is not None:
                final_pos = pos
            if current is not None:
                final_current = current
                if abs(int(current)) >= GRIPPER_CURRENT_STALL_THRESHOLD:
                    stall_detected = True

            hw_err = self.read_reg(GRIPPER_ID, ADDR_HARDWARE_ERROR, 1)
            if hw_err not in (0, None):
                raise InFlightSafetyViolationError(f"그리퍼 J15 하드웨어 오류 플래그 발생 ({hw_err})")

            temp = self._read_plausible(GRIPPER_ID, ADDR_PRESENT_TEMPERATURE, 1, signed=False, implausible_abs_max=IMPLAUSIBLE_TEMPERATURE_C)
            grip_temp_limit = temperature_limit_c if temperature_limit_c is not None else DEFAULT_TEMPERATURE_LIMIT_C
            if not bypass_temperature_check and temp is not None and temp > grip_temp_limit:
                raise InFlightSafetyViolationError(f"그리퍼 J15 온도 {temp}C가 한계 {grip_temp_limit}C 초과")

            if stall_detected:
                curr_pos = self.read_reg(GRIPPER_ID, ADDR_PRESENT_POSITION, 4, signed=True)
                if curr_pos is not None:
                    try:
                        self.gripper_write_reg(ADDR_GOAL_POSITION, 4, curr_pos)
                    except Exception:
                        pass
                break
            if pos is not None and moving == 0 and abs(pos - clamped) <= GRIPPER_GOAL_POSITION_TOLERANCE:
                settled = True
                break
            time.sleep(0.1)

        if not stall_detected and not settled:
            pos = self.read_reg(GRIPPER_ID, ADDR_PRESENT_POSITION, 4, signed=True)
            if pos is not None:
                final_pos = pos
                settled = abs(pos - clamped) <= GRIPPER_GOAL_POSITION_TOLERANCE

        return {
            "success": settled or stall_detected,
            "label": label,
            "target_ticks": clamped,
            "requested_ticks": int(target),
            "position_clamped": position_clamped,
            "before_position": before_pos,
            "before_current": before_current,
            "final_position": final_pos,
            "final_current": final_current,
            "settled": settled,
            "stall_detected": stall_detected,
            "duration_ms": int((time.time() - start_t) * 1000),
            "position_error": abs(final_pos - clamped) if final_pos is not None else None,
        }

    @property
    def raw_audit(self) -> list[dict[str, Any]]:
        return [asdict(entry) for entry in self.audit]


__all__ = ["OpenManipulatorXArmAdapter", "ARM_IDS", "GRIPPER_ID", "EXPECTED_IDS", "SAFE_BASIC_POSE"]
