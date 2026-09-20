"""실행값 호환성 — 무엇이 바뀌면 옛 값을 못 쓰는가 (2026-09-20).

두 가지가 빠져 있었다. 둘 다 재현으로 확인된 것이다.

    A.1  `unit.per_degree`를 바꿔도 구성 지문이 같았다.
         단위가 달라지면 같은 숫자가 다른 각도를 뜻하는데 옛 값이 그대로 실행됐다.

    A.2  작업 ID는 그대로 두고 자세 단계를 A에서 B로 바꿔도, 옛 단계 0의
         관절값이 새 단계 B에 붙고 `taught=True`가 나왔다.

원칙은 하나다 — **"자세를 잃지 않는다"와 "바로 실행해도 된다"는 다르다.**
근거가 없으면 원본은 보존하되 실행은 막고 확인을 요구한다.
표시 이름이 바뀐 것과 동작의 뜻이 바뀐 것은 가른다.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hangeul_console import configuration, module as module_mod
from hangeul_console.task import TaskStore, meaning_digest

ROOT = Path(__file__).resolve().parents[1]
STEP_A = [{"kind": "pose", "label": "A"}]
STEP_B = [{"kind": "pose", "label": "B", "targets_hint": "다른 자리"}]


@pytest.fixture
def mods():
    loaded, problems = module_mod.load_all(ROOT / "install" / "modules")
    assert not problems, problems
    return loaded


@pytest.fixture
def parts(mods):
    return ["core_a", "arm_omx", "hand_omx"]


def _config(mods, parts, **overrides):
    changed = dict(mods)
    for module_id, patch in overrides.items():
        changed[module_id] = replace(mods[module_id], **patch)
    return configuration.build("robot", "robot", changed, parts)


def _taught(mods, parts, steps=STEP_A):
    config = _config(mods, parts)
    store = TaskStore()
    store.save_meaning("job", label="원래 이름", steps=steps)
    store.save_realization("job", config, [{"index": 0, "targets": {"11": 2048}}],
                           operator="시험")
    return store, config


# ── A.1 단위·교정 ───────────────────────────────────────────────
def test_changing_the_unit_changes_the_fingerprint(mods, parts):
    """전에는 같았다 — `same fingerprint: True`."""
    base = _config(mods, parts)
    moved = _config(mods, parts,
                    arm_omx={"unit": {**mods["arm_omx"].unit, "per_degree": 12345}})
    assert base.fingerprint() != moved.fingerprint(), \
        "단위를 바꿨는데 지문이 그대로입니다 — 옛 값이 다른 각도로 실행됩니다"


def test_the_legacy_fingerprint_still_matches_so_migration_can_tell(mods, parts):
    """v1은 단위를 안 봤다. 그 사실을 알아볼 수 있어야 이행 판단이 된다."""
    base = _config(mods, parts)
    moved = _config(mods, parts,
                    arm_omx={"unit": {**mods["arm_omx"].unit, "per_degree": 12345}})
    assert base.legacy_fingerprint() == moved.legacy_fingerprint()


def test_a_value_saved_before_units_were_hashed_is_preserved_but_blocked(mods, parts):
    """옛 기록은 **버리지 않는다.** 다만 확인 전에는 쓰지 않는다."""
    store, config = _taught(mods, parts)
    record = store.realizations["robot::job"]
    record["configuration_fingerprint"] = config.legacy_fingerprint()   # v1로 저장됐던 것

    got = store.realization("job", config)
    assert got["verification"] == "COMPAT_CHECK_REQUIRED"
    assert got["step_targets"], "원본을 잃었습니다 — 보존해야 합니다"
    assert store.resolve("job", config)["taught"] is False, \
        "확인이 필요한 값을 바로 쓸 수 있다고 합니다"
    assert store.resolve("job", config)["steps"][0]["targets"] is None


# ── A.2 작업 정의 개정 ──────────────────────────────────────────
def test_editing_the_steps_does_not_reuse_the_old_joint_values(mods, parts):
    """전에는 새 단계 B에 옛 단계 0의 값이 붙고 taught=True가 나왔다."""
    store, config = _taught(mods, parts, STEP_A)
    store.save_meaning("job", label="원래 이름", steps=STEP_B)      # 단계를 바꾼다

    resolved = store.resolve("job", config)
    assert resolved["taught"] is False, "바뀐 단계에 옛 값을 그대로 씁니다"
    assert resolved["steps"][0]["targets"] is None
    assert store.realization("job", config)["verification"] == "NEEDS_RETEACH"


def test_renaming_a_task_is_not_a_change_of_meaning(mods, parts):
    """표시 이름만 바꾼 것으로 가르친 값을 버리지 않는다."""
    store, config = _taught(mods, parts, STEP_A)
    store.save_meaning("job", label="새 이름", icon="✨", steps=STEP_A)

    resolved = store.resolve("job", config)
    assert resolved["taught"] is True, "이름만 바꿨는데 다시 가르치라고 합니다"
    assert resolved["steps"][0]["targets"] == {"11": 2048}


def test_a_pose_step_name_is_part_of_the_meaning():
    """**자세 단계에서는 이름이 뜻이다.**

    발음은 단계 번호로만 맞춰지므로, "A로 간다"와 "B로 간다"를 가르는 것이
    이름뿐이다. 이름을 표시용으로 치우면 A의 관절값이 B에 조용히 실린다.
    """
    assert meaning_digest([{"kind": "pose", "label": "A"}]) != \
           meaning_digest([{"kind": "pose", "label": "B"}])


def test_a_name_on_a_nameless_step_is_not_the_meaning():
    """손 열기·닫기·대기는 하는 일이 이름과 무관하다."""
    assert meaning_digest([{"kind": "hand_open", "label": "손 열기"}]) == \
           meaning_digest([{"kind": "hand_open", "label": "집게 벌리기"}])


def test_the_kind_and_the_order_are_the_meaning():
    assert meaning_digest([{"kind": "pose"}]) != meaning_digest([{"kind": "hand_open"}])
    assert meaning_digest([{"kind": "pose"}, {"kind": "hand_open"}]) != \
           meaning_digest([{"kind": "hand_open"}, {"kind": "pose"}]), "순서도 뜻이다"


def test_a_record_with_no_meaning_digest_is_not_auto_approved(mods, parts):
    """뜻 해시가 없던 때의 기록을 현재 정의로 추정해 승인하지 않는다."""
    store, config = _taught(mods, parts, STEP_A)
    del store.realizations["robot::job"]["meaning_digest"]

    got = store.realization("job", config)
    assert got["verification"] == "COMPAT_CHECK_REQUIRED"
    assert got["step_targets"], "원본을 잃었습니다"


# ── 부품 교체는 그대로 무효 ─────────────────────────────────────
def test_swapping_a_part_still_revokes(mods, parts):
    store, config = _taught(mods, parts)
    other = _config(mods, ["core_a", "arm_mycobot", "hand_mycobot"])
    other.instance_id = config.instance_id
    assert store.realization("job", other)["verification"] == "REVOKED"


def test_the_meaning_itself_is_never_lost(mods, parts):
    """무엇이 바뀌든 **뜻은 남는다.** 다시 가르치면 된다."""
    store, config = _taught(mods, parts, STEP_A)
    store.save_meaning("job", label="원래 이름", steps=STEP_B)
    assert "job" in store.meanings
    assert store.resolve("job", config)["label"] == "원래 이름"


def test_the_legacy_value_is_byte_for_byte_what_v1_produced(mods, parts):
    """이행의 다리가 실제로 놓였는가.

    옛 코드(`1f8fb8c`)가 `core_a + arm_omx + hand_omx`에 대해 내던 값이다.
    이 값이 달라지면 사람이 저장해 둔 발음이 **COMPAT_CHECK_REQUIRED가 아니라
    REVOKED로 떨어진다** — 보존하고 묻는 대신 그냥 버리게 된다.
    """
    config = _config(mods, parts)
    assert config.legacy_fingerprint() == "sha256:6950eaa62bfed237"


def test_numeric_joint_ids_did_not_shift_when_names_became_possible(mods, parts):
    """관절 이름을 허용하면서 기존 숫자 지문이 움직이면 안 된다."""
    config = _config(mods, parts)
    assert all(isinstance(j, int) for j in config.arm().joint_ids()), \
        "숫자 관절이 문자열로 바뀌면 기존 지문이 전부 어긋납니다"
