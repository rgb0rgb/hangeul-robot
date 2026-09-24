"""상태점검(시운전)과 주행거리계 — 사전 A/S (2026-09-21).

지금까지는 **사후 A/S**였다. 실행해 본다 → 실패한다 → 왜인지 찾는다.
그때는 팔이 이미 움직인 뒤다.

상태점검은 쓰기 전에 **조금 움직여 보고** 부품별로 말해 준다.
작게 한 번(10%), 조금 크게 한 번(50%). 작은 쪽에서 이상하면 큰 쪽은 하지 않는다.

**이건 로봇을 움직이는 일이다.** 그래서 이 시험이 가장 먼저 보는 것은
점검 단추가 안전 게이트를 우회하는 뒷문이 되지 않는가이다.
"""
from __future__ import annotations

import pytest

from hangeul_runtime import safety, server


class _FakeArm:
    """넘어온 명령을 받아 적는 가짜 팔. 실물 대신이 아니라 기록계다."""

    evidence_kind = "physical"

    def __init__(self, fail_joint: str = "", fail_at_pct: int = 0):
        self.pos = {"11": 2048, "12": 2048, "13": 2048, "14": 2048, "15": 1800}
        self.moves: list[dict] = []
        self.fail_joint = fail_joint
        self.fail_at_pct = fail_at_pct

    def read_joint_positions(self):
        return dict(self.pos)

    def read_temperatures(self):
        return {"11": 41.0, "12": 40.0, "13": 39.5, "14": 42.0}

    def _maybe_fail(self, label):
        if self.fail_joint and f"_{self.fail_at_pct}" in label:
            raise RuntimeError("서보가 응답하지 않습니다")

    def move_joints(self, targets, *, velocity, acceleration, label,
                    bypass_temperature_check=False, temperature_limits_c=None,
                    velocity_per_joint=None):
        if self.fail_joint and self.fail_joint in targets:
            self._maybe_fail(label)
        self.moves.append({"targets": dict(targets), "label": label})
        self.pos.update({str(k): int(v) for k, v in targets.items()})
        return {"success": True, "settled": True, "errors_deg": {}}

    def move_gripper(self, target, *, velocity, acceleration, label,
                     bypass_temperature_check=False, temperature_limit_c=None):
        self.moves.append({"targets": {"15": int(target)}, "label": label})
        self.pos["15"] = int(target)
        return {"success": True}


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch):
    """명령 사이의 뜸은 실물에 필요한 것이다. 시험에서는 기다릴 이유가 없다."""
    monkeypatch.setattr(server, "_pace", lambda *a, **k: None)


@pytest.fixture
def arm(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "state", safety.SafetyState())
    server.build("arm_omx", "", simulate=True,
                 state_path=str(tmp_path / "s.json"),
                 usage_path=str(tmp_path / "u.json"))
    fake = _FakeArm()
    server.CONFIG["adapter"] = fake
    server.CONFIG["simulate_reason"] = ""
    server._read_cache.update({"at": 0.0, "value": {}})
    return fake


def _go(**extra):
    return server.self_check({"operator": "운영자", "confirmed": True,
                              "workspace_clear": True, **extra})


# ── 뒷문이 아닌가 ───────────────────────────────────────────────
def test_it_will_not_start_without_someone_watching(arm):
    assert server.self_check({})["verdict"] == "BLOCKED_NO_OPERATOR"
    assert server.self_check({"operator": "나", "confirmed": True})["verdict"] \
        == "BLOCKED_WORKSPACE_UNCONFIRMED"


def test_a_latched_stop_blocks_the_check_too(arm):
    """**점검이 안전 게이트를 우회하면 안 된다.** 기존 실행과 같은 문으로 나간다."""
    server.state.latch_estop("시험")
    answer = _go()
    ran = [s for s in answer["joints"].values() if s.get("state") == "정상"]
    assert not ran, "정지가 걸렸는데 시운전이 돌았습니다"
    assert not arm.moves, "정지가 걸렸는데 로봇에 명령이 나갔습니다"


def test_a_stop_during_the_check_ends_it(arm, monkeypatch):
    calls = {"n": 0}
    original = server._self_check_joint

    def stop_after_first(joint, pct, operator):
        calls["n"] += 1
        if calls["n"] == 1:
            server.state.latch_estop("점검 중 정지")
        return original(joint, pct, operator)

    monkeypatch.setattr(server, "_self_check_joint", stop_after_first)
    answer = _go()
    assert answer["stopped"], "점검 도중 정지가 걸렸는데 계속 돌았습니다"


# ── 각본 ────────────────────────────────────────────────────────
def test_it_moves_small_then_a_bit_bigger(arm):
    answer = _go()
    pcts = [s["percent"] for s in answer["steps"] if s.get("joint") == "11"]
    assert pcts[:2] == list(server.SELF_CHECK_STEPS), f"작게→조금 크게가 아닙니다: {pcts}"


def test_a_bad_small_step_skips_the_bigger_one(tmp_path, monkeypatch):
    """작은 쪽에서 이미 이상하면 큰 쪽으로 키우지 않는다."""
    monkeypatch.setattr(server, "state", safety.SafetyState())
    server.build("arm_omx", "", simulate=True,
                 state_path=str(tmp_path / "s.json"), usage_path=str(tmp_path / "u.json"))
    server.CONFIG["adapter"] = _FakeArm(fail_joint="11", fail_at_pct=10)
    server.CONFIG["simulate_reason"] = ""
    server._read_cache.update({"at": 0.0, "value": {}})

    answer = _go()
    pcts = [s["percent"] for s in answer["steps"] if s.get("joint") == "11"]
    assert server.SELF_CHECK_STEPS[1] not in pcts, "작은 쪽이 실패했는데 더 크게 움직였습니다"
    assert answer["joints"]["11"]["state"] == "이상"


def test_it_puts_the_arm_back(arm):
    """점검이 로봇을 다른 자리에 두고 끝나면 안 된다."""
    before = dict(arm.pos)
    _go()
    for joint in ("11", "12", "13", "14"):
        assert arm.pos[joint] == before[joint], f"관절 {joint}이 제자리로 안 왔습니다"


def test_every_arm_joint_is_checked(arm):
    answer = _go()
    for joint in ("11", "12", "13", "14"):
        assert joint in answer["joints"], f"관절 {joint}을 건너뛰었습니다"


# ── 움직임 폭 — 이게 제일 중요하다 ─────────────────────────────
def test_nothing_moves_more_than_half_the_range(arm):
    """**어떤 경우에도 범위의 50%를 넘지 않는다.**

    실물에서 넘겼다(2026-09-21). 두 군데였다 — 손이 완전히 닫혔다 완전히
    열렸고(100%), 팔은 범위의 절반이라 고정대면 180도였다. 시운전은
    살펴보는 것이지 운동시키는 것이 아니다.

    설명이나 상수가 아니라 **SDK에 실제로 넘어간 값**을 잰다.
    """
    start = dict(arm.pos)
    _go()

    limits = server.CONFIG["limits"]
    worst = []
    for move in arm.moves:
        for joint, target in move["targets"].items():
            band = limits.get(str(joint))
            if not band:
                continue
            span = int(band[1]) - int(band[0])
            moved = abs(int(target) - int(start[str(joint)]))
            worst.append((str(joint), moved, span, move["label"]))

    assert worst, "아무것도 안 움직였습니다 — 시험이 헛돌고 있습니다"
    over = [w for w in worst if w[1] > w[2] * server.SELF_CHECK_MAX_PERCENT / 100 + 1]
    assert not over, (
        f"범위의 {server.SELF_CHECK_MAX_PERCENT}%를 넘겨 움직였습니다: "
        + ", ".join(f"{j} {m}틱/{s}틱({l})" for j, m, s, l in over))


def test_the_hand_is_not_slammed_shut_and_open(arm):
    """손을 끝까지 밀어붙이지 않는다 — 물린 것이 있으면 부순다."""
    _go()
    hand = server._hand_joint_id()
    band = server.CONFIG["limits"][hand]
    low, high = int(band[0]), int(band[1])
    sent = [int(m["targets"][hand]) for m in arm.moves if hand in m["targets"]]
    assert sent, "손을 점검하지 않았습니다"
    assert low not in sent, "손을 끝까지 닫았습니다"
    assert high not in sent, "손을 끝까지 열었습니다"


def test_the_cap_is_in_one_place(arm):
    """호출부마다 각자 셈하면 언젠가 한 곳이 넘긴다. 실제로 그랬다."""
    cap = server.SELF_CHECK_MAX_PERCENT
    assert server._self_check_amount(1000, 90, 10000, 10000, degrees=False) == cap * 10, \
        f"90%를 달라고 해도 {cap}%까지만 나가야 합니다"
    assert server._self_check_amount(1000, 10, 10000, 10000, degrees=False) == 100
    assert server._self_check_amount(1000, cap, 20, 30, degrees=False) == 30, \
        "여유가 없으면 갈 수 있는 만큼만"


def test_no_joint_swings_more_than_the_degree_ceiling(arm):
    """**비율만으로는 모자란다.** 고정대는 50%가 180도다.

    시운전에 팔이 반 바퀴 도는 것은 살펴보는 것이 아니다.
    """
    start = dict(arm.pos)
    _go()

    unit = server.CONFIG["descriptor"].get("unit") or {}
    per = float(unit.get("per_degree") or 1)
    hand = server._hand_joint_id()
    over = []
    for move in arm.moves:
        for joint, target in move["targets"].items():
            if str(joint) == hand:
                continue                      # 손은 도(°)가 뜻이 없다
            moved_deg = abs(int(target) - int(start[str(joint)])) / per
            if moved_deg > server.SELF_CHECK_MAX_DEGREES + 0.5:
                over.append((str(joint), round(moved_deg, 1), move["label"]))
    assert not over, ("각도 상한을 넘겼습니다: "
                      + ", ".join(f"{j} {d}도({l})" for j, d, l in over))


def test_small_first_then_bigger_is_still_true(arm):
    """상한을 걸었다고 **두 걸음이 같아지면 안 된다.** 각본이 사라진다."""
    start = dict(arm.pos)
    _go()
    per = float((server.CONFIG["descriptor"].get("unit") or {}).get("per_degree") or 1)
    small_pct, big_pct = server.SELF_CHECK_STEPS
    first = next(m for m in arm.moves if m["label"].endswith(f"_{small_pct}"))
    big = next(m for m in arm.moves if m["label"].endswith(f"_{big_pct}"))
    joint = list(first["targets"])[0]
    small_deg = abs(int(first["targets"][joint]) - int(start[joint])) / per
    big_deg = abs(int(big["targets"][joint]) - int(start[joint])) / per
    assert big_deg > small_deg * 1.5, \
        f"작은 걸음 {small_deg}도, 큰 걸음 {big_deg}도 — 차이가 없습니다"


def test_a_silent_joint_is_not_pushed_at_all(tmp_path, monkeypatch):
    """**이상이 있으면 아예 움직이지 않는다.**

    고장 난 관절을 억지로 밀어 보는 것은 점검이 아니라 고장을 키우는 일이다.
    """
    monkeypatch.setattr(server, "_pace", lambda *a, **k: None)
    monkeypatch.setattr(server, "state", safety.SafetyState())
    server.build("arm_omx", "", simulate=True,
                 state_path=str(tmp_path / "s.json"), usage_path=str(tmp_path / "u.json"))

    fake = _FakeArm()

    def attest():
        return {"arm": {"responding": False, "evidence": "ping",
                        "detail": {"11": True, "12": False, "13": True, "14": True}},
                "hand": {"responding": True, "evidence": "ping"}}

    fake.attest_parts = attest
    server.CONFIG["adapter"] = fake
    server.CONFIG["simulate_reason"] = ""
    server._read_cache.update({"at": 0.0, "value": {}})

    answer = _go()
    assert answer["joints"]["12"]["state"] == "이상"
    assert answer["joints"]["12"]["moved"] is False
    touched = [m for m in fake.moves if "12" in m["targets"]]
    assert not touched, "응답하지 않는 관절에 명령을 보냈습니다"
    # 나머지는 정상대로 본다
    assert answer["joints"]["11"]["state"] == "정상"


# ── 사람에게 하는 말 ────────────────────────────────────────────
def test_the_verdict_is_in_plain_words(arm):
    answer = _go()
    for row in answer["joints"].values():
        assert row["state"] in ("정상", "이상", "확인 불가"), row


def test_the_hand_result_does_not_claim_more_than_it_knows(arm):
    """집게가 붙어 있는지는 이 점검만으로 단정하지 않는다 — 걸림·마모도 비슷하다."""
    answer = _go()
    hand = answer["joints"].get("15") or {}
    assert "단정하지 않습니다" in (hand.get("note") or "")


# ── 주행거리계 ──────────────────────────────────────────────────
def test_moving_adds_to_the_odometer(arm):
    _go()
    usage = server.get_usage()
    assert usage["move_count"] > 0, "움직였는데 한 줄도 안 쌓였습니다"
    assert usage["has_history"]
    assert usage["busiest_joint"], "제일 많이 쓴 관절을 모릅니다"


def test_an_empty_odometer_says_so_instead_of_showing_zero(tmp_path, monkeypatch):
    """**없는 것은 없다고 말한다.** 0으로 꾸미면 새 로봇과 안 쓴 로봇이 같아 보인다."""
    monkeypatch.setattr(server, "state", safety.SafetyState())
    server.build("arm_omx", "", simulate=True,
                 state_path=str(tmp_path / "s.json"), usage_path=str(tmp_path / "u.json"))
    usage = server.get_usage()
    assert usage["has_history"] is False
    assert usage["busiest_joint"] == ""


def test_the_odometer_survives_a_restart(arm, tmp_path):
    _go()
    before = server.get_usage()["move_count"]
    from hangeul_runtime.usage_log import UsageLog

    again = UsageLog(server.CONFIG["usage_path"]).summary()
    assert again["move_count"] == before, "껐다 켜면 주행거리가 사라집니다"


def test_the_check_is_remembered(arm):
    _go()
    assert server.get_usage()["last_self_check_at"], "점검한 기록이 남지 않습니다"
