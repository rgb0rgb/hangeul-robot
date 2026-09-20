"""부품별 응답 — 등록된 것과 실제로 응답하는 것을 가른다 (2026-09-20).

사용자 보고: **그리퍼를 제거해도 있는 것으로 인식했다**(MyCobot).
원인은 능력 상태가 로봇 단위 한 값(`_default`)으로만 정해졌기 때문이다.
연결돼 있으면 전부 AVAILABLE, 끊기면 전부 UNAVAILABLE이었다.

여기서 지키는 것은 **정직성**이다.

    · 근거가 있는 만큼만 나눈다. 없으면 없다고 말한다(UNVERIFIABLE).
    · 같은 관측에는 같은 답을 낸다. 전자부가 똑같이 응답하는데 화면이
      달라진다면 그것은 감지가 아니라 **없는 증거를 지어낸 것**이다.
    · 전부 조용한 것은 "손이 없다"가 아니라 "포트·전원이 문제다"이다.

**응답 확인은 기계적 장착의 증거가 아니다.** 집게만 떼고 전자부가 남으면
응답은 그대로다. 그 경우는 소프트웨어가 가를 수 없고, 가르는 척해서도 안 된다.
"""
from __future__ import annotations

import pytest

from hangeul_console import capability as cap
from hangeul_console import module as module_mod
from hangeul_console import configuration
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def omx_config():
    mods, problems = module_mod.load_all(ROOT / "install" / "modules")
    assert not problems, problems
    return configuration.build("t", "t", mods, ["core_a", "arm_omx", "hand_omx"])


def _states(config, parts, health=None):
    store = cap.CapabilityStore()
    rows = store.snapshot(config, health or {"_default": "AVAILABLE"}, parts)
    return {r.capability_id: r for r in rows}


def test_a_silent_hand_only_takes_down_hand_capabilities(omx_config):
    """손만 응답이 없으면 손 능력만 내려간다. 팔은 그대로다."""
    parts = {"arm": {"responding": True, "evidence": "ping"},
             "hand": {"responding": False, "evidence": "ping"}}
    rows = _states(omx_config, parts)

    assert rows["hand.open"].attestation == "NOT_RESPONDING"
    assert rows["hand.open"].health == "UNAVAILABLE"
    assert rows["hand.open"].reason, "막아놓고 이유를 안 적었습니다"

    assert rows["motion.move_pose"].attestation == "RESPONDING"
    assert rows["motion.move_pose"].health == "AVAILABLE"


def test_everything_silent_is_not_read_as_a_missing_part(omx_config):
    """전부 조용하면 부품별로 나누지 않는다 — 그것은 버스·전원 쪽 사실이다."""
    parts = {"arm": {"responding": False, "evidence": "ping", "all_silent": True,
                     "reason": "어느 관절도 응답하지 않습니다"},
             "hand": {"responding": False, "evidence": "ping", "all_silent": True,
                      "reason": "어느 관절도 응답하지 않습니다"}}
    rows = _states(omx_config, parts, {"_default": "UNAVAILABLE",
                                       "_reason": "연결 없음"})
    for cid in ("motion.move_pose", "hand.open"):
        assert rows[cid].attestation == "UNVERIFIABLE", (
            f"{cid}: 전부 조용한데 그 부품이 없다고 단정했습니다")


def test_no_way_to_ask_means_unverifiable_not_normal(omx_config):
    """**수단이 없으면 모른다.** 조용히 정상으로 바꾸지 않는다 (MyCobot 손)."""
    parts = {"arm": {"responding": True, "evidence": "controller"},
             "hand": {"responding": None, "evidence": "none",
                      "reason": "이 로봇은 손이 붙어 있는지 확인할 수단이 없습니다"}}
    rows = _states(omx_config, parts)

    assert rows["hand.open"].attestation == "UNVERIFIABLE"
    assert "확인할 수단이 없습니다" in rows["hand.open"].attestation_reason
    # 확인 불가에 실행을 아주 막으면 제품이 안 된다 — 막지 않되 모른다고 적는다
    assert rows["hand.open"].health == "AVAILABLE"


def test_an_empty_parts_map_is_read_as_unverifiable(omx_config):
    """런타임이 부품별로 말할 수단이 없으면 전부 확인 불가다."""
    rows = _states(omx_config, {})
    assert rows["hand.open"].attestation == "UNVERIFIABLE"
    assert rows["motion.move_pose"].attestation == "UNVERIFIABLE"


def test_the_same_observation_gives_the_same_answer(omx_config):
    """**정직성 기준.** 기구만 떼도 전자부는 똑같이 응답한다.

    그 경우 소프트웨어가 볼 수 있는 것은 정상과 **완전히 같다.**
    그런데도 답이 달라진다면 어딘가에서 없는 증거를 지어내고 있는 것이다.
    """
    observed = {"arm": {"responding": True, "evidence": "ping"},
                "hand": {"responding": True, "evidence": "ping"}}
    normal = _states(omx_config, dict(observed))
    gripper_unbolted = _states(omx_config, dict(observed))   # 관측은 같다

    for cid in normal:
        assert normal[cid].to_dict() == gripper_unbolted[cid].to_dict(), (
            f"{cid}: 같은 관측인데 다른 답을 냅니다")
    # 그리고 그 답은 "장착을 확인했다"가 아니다
    assert normal["hand.open"].attestation == "RESPONDING"
    assert normal["hand.open"].attestation != "ATTACHED"


def test_a_silent_hand_blocks_a_task_that_needs_it(omx_config):
    """화면만 바뀌면 소용없다 — 실행 경로에서 실제로 막히는가."""
    from hangeul_console import task as task_mod

    parts = {"arm": {"responding": True, "evidence": "ping"},
             "hand": {"responding": False, "evidence": "ping"}}
    store = cap.CapabilityStore()
    states = store.snapshot(omx_config, {"_default": "AVAILABLE"}, parts)

    steps = [{"kind": "pose", "label": "A", "targets": {"11": 2048}},
             {"kind": "hand_close"}]
    answer = task_mod.check_runnable(steps, omx_config, states)
    assert answer["runnable"] is False, "손이 응답하지 않는데 실행을 허락했습니다"
    assert any("hand" in b or "손" in b for b in answer["blockers"]), answer["blockers"]


# ── 어댑터가 실제로 무엇을 말하는가 ──────────────────────────────
def test_mycobot_says_it_cannot_speak_for_the_hand():
    """MyCobot preflight 경로에는 그리퍼를 묻는 수단이 없다 — 그렇게 말해야 한다."""
    from hangeul_runtime.hardware.mycobot_280_m5_adapter import MyCobot280M5Adapter

    class _SDK:
        def is_controller_connected(self): return 1
        def get_angles(self): return [0.0] * 6

    with MyCobot280M5Adapter(device="fake", sdk=_SDK()) as arm:
        parts = arm.attest_parts()
    assert parts["arm"]["responding"] is True
    assert parts["hand"]["responding"] is None, (
        "확인할 수단이 없는데 손이 있다/없다고 단정했습니다")
    assert parts["hand"]["reason"]


def test_omx_can_speak_for_arm_and_hand_separately():
    from hangeul_runtime.hardware import openmanipulator_x_arm_adapter as omx

    class _Adapter(omx.OpenManipulatorXArmAdapter):
        silent: set = set()

        def ping(self, dxl_id):
            return {"responded": dxl_id not in self.silent}

    arm = _Adapter(device="fake")
    arm.silent = {omx.GRIPPER_ID}
    parts = arm.attest_parts()
    assert parts["arm"]["responding"] is True
    assert parts["hand"]["responding"] is False

    arm.silent = set(omx.EXPECTED_IDS)
    quiet = arm.attest_parts()
    assert quiet["arm"]["all_silent"] is True, "전부 조용한 것을 손 문제로 읽습니다"
