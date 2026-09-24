"""로봇 무관 팔 어댑터 인터페이스.

관절 개수는 로봇마다 다르므로 고정하지 않는다 — 각 어댑터가 자신의
joint_names를 스스로 선언하고, 인터페이스는 "관절 이름 -> 정수 목표값"
딕셔너리만 다룬다. 실제 통신 프로토콜(Dynamixel/시리얼/소켓 등)은 각
구현체 내부로 감춘다.

안전범위 최종 방어선은 항상 이 인터페이스의 clamp()다. 매니페스트/인스턴스
설정이 잘못되어도 구현체의 clamp()가 실측범위를 넘지 않게 막아야 한다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


def effective_velocity(requested: int, limit: int | None) -> int:
    """이 관절에 실제로 쓸 속도. **한계는 상한이지 덮어쓰기가 아니다.**

        effective_velocity(10, 50) == 10     느리게 가라면 느리게 간다
        effective_velocity(200, 50) == 50    한계를 넘겨 달라면 한계까지만
        effective_velocity(10, None) == 10   한계가 없으면 요청대로

    돌려주는 값은 항상 1 이상이다 — 0은 "움직이지 않는다"가 아니라 SDK마다
    다른 뜻(대개 최고 속도)이라 그대로 내보내면 안 된다.
    """
    value = int(requested)
    if limit is not None:
        value = min(value, int(limit))
    return max(1, value)


def batch_velocity(requested: int, velocity_per_joint: dict[str, int] | None,
                   joints: "list[str] | tuple[str, ...]") -> int:
    """배치 명령 하나에 속도 하나만 실리는 SDK를 위한 값.

    xArm의 `set_servo_angle(speed=...)`처럼 여러 관절을 한 번에 보내면서 속도는
    하나만 받는 SDK가 있다. 그때는 **가장 엄한 한계를 따른다** — 관절 하나라도
    한계를 넘기면 그 한계는 없는 것이 되기 때문이다.

    (2026-09-20: xArm 어댑터는 velocity_per_joint를 받아놓고 쓰지 않았다.
    관절별 한계를 걸어도 아무 일도 일어나지 않았다.)
    """
    per_joint = velocity_per_joint or {}
    speeds = [effective_velocity(requested, per_joint.get(name)) for name in joints]
    return min(speeds) if speeds else effective_velocity(requested, None)


class RobotArmAdapter(ABC):
    """모든 로봇팔 어댑터가 구현해야 하는 최소 공통 인터페이스.

    구현체는 __init__에서 self.joint_names(list[str])와
    self.gripper_joint_name(str | None)을 반드시 설정해야 한다.
    """

    robot_model: str = ""
    joint_names: list[str] = []
    gripper_joint_name: str | None = None
    # 이 개체에서 제외된 관절(예: MyCobot J4 고장). 비워두면 전부 정상.
    # freeze_in_place()가 이 집합을 반드시 걷어내야 한다 — 안 그러면 ESTOP 자체가
    # move_joints()의 제외관절 방어에 걸려 실패한다(Codex 검증 20260812 발견).
    excluded_joints: set[str] = set()

    @classmethod
    def from_resolved(cls, profile: dict[str, Any], instance: dict[str, Any]) -> "RobotArmAdapter":
        """옛 dexter 매니페스트(profile/instance)로 어댑터를 구성한다. **지금은 쓰이지 않는다.**

        2026-09-20 ROS 2 반증 시험에서 걸렸다. 이 메서드는 **abstract였다** —
        즉 새 어댑터를 쓰는 사람은 아래 설명이 "쓰이지 않는다"고 말하는
        메서드를 반드시 구현해야 했다. 쓰지 않는 것을 강제하는 계약은 계약이
        아니라 통행세다. abstract를 뗐고, 안 만든 어댑터는 불렀을 때만 막힌다.

        주의 — 이 메서드의 인자는 옛 저장소의 스키마(instance["connection"]
        ["device_default"] 등)이고, 지금 쓰는 부품 기술서와 모양이 다르다.
        현재 런타임(server.py)은 이 메서드를 호출하지 않고 `_make_adapter()`가
        기술서를 보고 **어댑터가 받겠다고 선언한 인자만** 생성자로 넘긴다.

        옛 문서 문자열은 "서버는 이 메서드 하나만 호출한다"고 적고 있었는데
        사실이 아니었다(xArm 반증 시험 20260817에서 확인). 새 어댑터를 쓸 때
        이 메서드에 의존하지 않는다 — 남겨 둔 것은 옛 호출부 호환 때문이다.
        """
        raise NotImplementedError(
            f"{cls.__name__}은(는) 옛 매니페스트 경로를 지원하지 않습니다. "
            f"부품 기술서와 runtime_adapter로 붙입니다")

    @abstractmethod
    def __enter__(self) -> "RobotArmAdapter":
        raise NotImplementedError

    @abstractmethod
    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_joint_positions(self) -> dict[str, int]:
        """모든 관절(+그리퍼 있으면 포함)의 현재 위치를 {joint_name: raw_position}로 반환."""
        raise NotImplementedError

    @abstractmethod
    def clamp(self, joint_name: str, target: int) -> int:
        """해당 관절의 안전 범위로 target을 잘라 반환. 최종 안전 방어선."""
        raise NotImplementedError

    @abstractmethod
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
        """팔 관절(그리퍼 제외)을 targets로 동시 이동.

        **velocity_per_joint는 상한이지 덮어쓰기가 아니다.**

        전에는 이 뜻이 어디에도 적혀 있지 않았고, 그래서 두 어댑터가 반대로
        갔다(2026-09-20 확인). OMX는 `min()`으로 상한을 지켰고, MyCobot은
        관절별 값이 있으면 요청값을 갈아치웠다 — 출하 기본값이 전 관절 50이라
        "느리게 가라"(10)가 50으로 나갔다. **계약이 뜻을 정하지 않았으므로
        두 구현 다 "맞았다."**

        지켜야 할 불변식은 속도의 **같음이 아니라 덮어쓰지 않음**이다.

            SDK에 실제로 넘어간 값 ≤ 요청값
            SDK에 실제로 넘어간 값 ≤ 한계값

        서로 다른 SDK에 같은 숫자를 넣었다고 물리 속도가 같아야 하는 것은
        아니다(MyCobot 1~100 눈금 · OMX Dynamixel 프로파일 속도 · ROS 2 rad/s).
        **장치 사이의 숫자를 직접 비교하지 않는다.** 각 어댑터가 자기 눈금
        안에서 위 두 부등식을 지키면 된다.

        구현은 `effective_velocity()`를 거쳐 값을 정한다. 직접 계산하면
        언젠가 또 갈린다.

        적용 범위: 양수 원시 속도 요청. 0·음수·지원 범위 밖 입력의 처리는
        각 어댑터가 자기 SDK 규칙으로 정하고 응답에 밝힌다.

        **확인할 수 없는 것은 응답에 밝힌다.**

        `temperature_limits_c`는 운영자가 정한 값이 내려오는 자리다. 온도를
        읽을 수단이 없는 로봇이 이 인자를 조용히 버리면, 사람은 한계를 걸어
        두고 걸린 줄 안다 — 걸어도 아무 일이 일어나지 않는데도.
        (2026-09-24 전수조사: 세 어댑터가 그러고 있었다. 속도에서 겪은 것과
        같은 모양이다 — 인자를 받아놓고 쓰지 않는 것.)

        확인하지 못하면 응답에 이렇게 적는다.

            {"temperature_check_supported": False, ...}

        적어 두면 호출부와 화면이 "이 로봇은 온도를 못 본다"고 말할 수 있다.
        조용히 버리면 아무도 모른다.
        """
        raise NotImplementedError

    def attest_parts(self) -> dict[str, dict[str, Any]]:
        """지금 어떤 부품이 응답하는가. **말할 수 있는 것만 말한다.**

        돌려주는 것은 부품 종류(`arm` · `hand` · …)별로 이렇다.

            {"arm":  {"responding": True,  "evidence": "ping", "detail": {...}},
             "hand": {"responding": None,  "evidence": "none",
                      "reason": "이 로봇에는 손 응답을 확인할 수단이 없습니다"}}

            responding=True   그 부품에서 응답을 얻었다
            responding=False  응답을 얻지 못했다
            responding=None   **확인할 수단이 없다** — 모른다는 뜻이지 정상이 아니다

        `None`을 조용히 `True`로 바꾸지 않는다. 로봇마다 말할 수 있는 범위가
        다르고(OMX는 ID별 ping이 있고 MyCobot은 손에 그런 수단이 없다),
        없는 근거를 있는 척하면 화면이 거짓말을 한다.

        **이것은 통신 응답이지 기계적 장착의 증거가 아니다.** 집게만 떼고
        전자부가 남아 있으면 `responding=True`가 그대로 나온다. 장착은
        별도 수단(장착 스위치 등)이나 운영자 점검으로만 확인된다.

        기본값은 빈 사전 — "부품별로 말할 수단이 없다"는 뜻이다. 호출부는
        이것을 전부 `None`으로 읽는다.
        """
        return {}

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    def preflight(self) -> dict[str, Any]:
        raise NotImplementedError

    def recover_from_fault(self) -> dict[str, Any]:
        """하드웨어 오류 래치를 풀 수 있으면 시도한다 (선택 구현).

        일부 로봇(예: Dynamixel 기반 OMX)은 과부하/과열 등을 감지하면 서보
        내부에 오류 래치를 걸고, 통신 자체는 살아있어도 정상 읽기/쓰기를
        계속 거부한다 — 재시도만으로는 안 풀린다. 이런 래치가 있는 로봇의
        어댑터는 이 메서드를 오버라이드해 실제로 푸는 절차(예: REBOOT
        인스트럭션)를 구현해야 한다. 기본 구현(아무 것도 안 함)은 그런
        래치 개념이 없는 로봇(예: MyCobot)에 그대로 쓰인다.
        """
        return {"attempted": False}

    def auto_calibrate(self) -> dict[str, Any]:
        """관절 한계값 결정론적 자동 탐색 (선택 구현).

        작은 스텝으로 밀며 read-back/오류코드/과전류를 감시하고 안전하게
        후퇴하며 한계를 기록하는 루틴이어야 한다. 언어모델(SLLM)은 이
        메서드를 트리거만 하고, 판단(밀기/후퇴/기록)에는 개입하지 않는다.
        모델 매니페스트의 calibration.auto_calibratable이 true인 로봇만
        이 메서드를 실제로 호출한다.
        """
        raise NotImplementedError("이 로봇은 자동 캘리브레이션을 지원하지 않는다")

    def freeze_in_place(
        self,
        *,
        arm_velocity: int,
        arm_acceleration: int,
        gripper_velocity: int,
        gripper_acceleration: int,
        label: str,
    ) -> dict[str, Any]:
        """현재 위치를 읽어 그 자리에서 고정한다 (estop/pause-hold/재시작 안전고정 공용).

        read_joint_positions + clamp + move_joints(+move_gripper) 조합으로
        구현되는 범용 동작이라 로봇별 재정의가 거의 필요 없다.

        excluded_joints에 있는 관절은 목표에서 반드시 제외한다 — ESTOP은 어떤
        상태에서도 실패하면 안 되는데, 제외 관절을 그대로 넣으면 move_joints()
        자신의 제외관절 방어에 걸려 ESTOP 호출 전체가 예외로 실패한다.

        위치 읽기 자체가 하드웨어 오류 래치(예: OMX 과부하 알림) 때문에 실패하면,
        재시도 전에 recover_from_fault()를 한 번 시도해 래치를 풀고 다시
        읽는다 — 그래도 안 되면 원래 예외를 그대로 전달한다(할 수 있는
        만큼만 했다는 뜻이지, 물리적으로 응답 불가능한 상태까지 성공으로
        꾸미지 않는다).
        """
        fault_recovery: dict[str, Any] | None = None
        try:
            present = self.read_joint_positions()
        except Exception:
            try:
                fault_recovery = self.recover_from_fault()
            except Exception as recovery_exc:  # noqa: BLE001 — 복구 시도 자체의 실패도 ESTOP을 막으면 안 된다
                fault_recovery = {"attempted": True, "error": f"{type(recovery_exc).__name__}: {recovery_exc}"}
            present = self.read_joint_positions()
        result: dict[str, Any] = {"present_positions": present}
        if fault_recovery is not None:
            result["fault_recovery"] = fault_recovery

        arm_targets = {
            name: present[name] for name in self.joint_names
            if name in present and name not in self.excluded_joints
        }
        if arm_targets:
            clamped = {name: self.clamp(name, val) for name, val in arm_targets.items()}
            result["arm_move"] = self.move_joints(
                clamped,
                velocity=arm_velocity,
                acceleration=arm_acceleration,
                label=label,
                bypass_temperature_check=True,
            )

        if self.gripper_joint_name and self.gripper_joint_name in present:
            result["gripper_move"] = self.move_gripper(
                present[self.gripper_joint_name],
                velocity=gripper_velocity,
                acceleration=gripper_acceleration,
                label=label,
                bypass_temperature_check=True,
            )
        return result
