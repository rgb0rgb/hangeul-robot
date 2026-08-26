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
    @abstractmethod
    def from_resolved(cls, profile: dict[str, Any], instance: dict[str, Any]) -> "RobotArmAdapter":
        """옛 dexter 매니페스트(profile/instance)로 어댑터를 구성한다. **지금은 쓰이지 않는다.**

        주의 — 이 메서드의 인자는 옛 저장소의 스키마(instance["connection"]
        ["device_default"] 등)이고, 지금 쓰는 부품 기술서와 모양이 다르다.
        현재 런타임(server.py)은 이 메서드를 호출하지 않고 `_make_adapter()`가
        기술서를 보고 **어댑터가 받겠다고 선언한 인자만** 생성자로 넘긴다.

        옛 문서 문자열은 "서버는 이 메서드 하나만 호출한다"고 적고 있었는데
        사실이 아니었다(xArm 반증 시험 20260817에서 확인). 새 어댑터를 쓸 때
        이 메서드에 의존하지 않는다 — 남겨 둔 것은 옛 호출부 호환 때문이다.
        """
        raise NotImplementedError

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
        """팔 관절(그리퍼 제외)을 targets로 동시 이동."""
        raise NotImplementedError

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
