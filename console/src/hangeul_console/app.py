"""한글 로봇 콘솔 — 기존 dexter_hangeul 화면을 그대로 쓰고, 내부만 새 구조로 바꾼다.

화면은 익숙한 것을 유지한다(대표 결정). 바뀐 것은 그 뒤다.

    이전                                    지금
    ────────────────────────────────────    ────────────────────────────────────
    web.py 2,700줄에 전부                   구성/자산/상태/실물이 각각 다른 모듈
    축 구성이 코드 조건문                    install/robots/*.json (데이터)
    낱말이 3개 트리 7개 파일에 흩어짐        terms.py 한 곳
    되는지 여부가 Boolean                    lifecycle/health/verification 3축
    자산·설정·런타임 상태가 한 폴더          셋을 분리 (백업 대상이 분명해짐)
    실물 호출이 곳곳에서                     runtime_link.py 하나만 통과

화면 계약은 그대로 지킨다. 화면 코드는 한 줄도 고치지 않는다.
"""
from __future__ import annotations

import json
import os
import shlex
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import (advisor, capability, configuration as cfg, module as module_mod,
               task as task_mod, terms)
from .device_lease import LeaseBook, LeaseError
from .instance_store import InstanceStore
from .registry import Registry, RegistryError
from .runtime_link import RuntimeLink

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WEB_DIR = PROJECT_ROOT / "console" / "web"
# 다시 시작할 때 쓰는 스크립트. 사람이 터미널에서 치는 것과 같은 것을 부른다 —
# 화면에서 한 재시작과 손으로 한 재시작이 다른 결과를 내면 안 된다.
RESTART_SCRIPT = PROJECT_ROOT / "run.sh"
MODULE_DIR = PROJECT_ROOT / "install" / "modules"
ROBOT_CONFIG_DIR = PROJECT_ROOT / "install" / "robots"
INSTANCE_DIR = PROJECT_ROOT / "data" / "instances"
CONSOLE_STATE = PROJECT_ROOT / "data" / "console_state.json"

app = FastAPI(title="Hangeul Robot Console")
registry = Registry(MODULE_DIR, ROBOT_CONFIG_DIR)
runtime = RuntimeLink()
capabilities = capability.CapabilityStore()
TASK_PATH = PROJECT_ROOT / "data" / "tasks.json"
leases = LeaseBook(PROJECT_ROOT / "data" / "leases")
CONSOLE_HOLDER = "console"


def _tasks() -> task_mod.TaskStore:
    if TASK_PATH.exists():
        try:
            return task_mod.TaskStore(json.loads(TASK_PATH.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return task_mod.TaskStore()


def _save_tasks(store: task_mod.TaskStore) -> None:
    TASK_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASK_PATH.write_text(json.dumps(store.to_dict(), ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")


def _capability_states(instance):
    health = runtime.health(instance)
    return (capabilities.visible(instance, health["capability_health"],
                                health.get("parts")), health)


# ── 콘솔 자체 상태 ──────────────────────────────────────────────
# 화면 상태 파일은 요청마다 읽고 쓴다(기록 한 줄마다도). 브라우저가 여러 창에서
# 물어보면 그 쓰기가 겹치는데, 통째로 덮어쓰기는 원자적이지 않아 반쯤 쓰인 파일이
# 남는다 — 실제로 그랬다. 그 뒤로 이 파일을 읽는 모든 요청이 500이 되어
# **로봇 목록이 통째로 사라졌다.** 기록 파일 하나 때문에 로봇이 사라지면 안 된다.
_CONSOLE_LOCK = threading.Lock()


def _console() -> dict[str, Any]:
    return _console_unlocked()


def _console_unlocked() -> dict[str, Any]:
    empty = {"selected": None, "mode": terms.MODE_USER, "log": [], "away_mode": False}
    if not CONSOLE_STATE.exists():
        return empty
    try:
        return json.loads(CONSOLE_STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        # 읽을 수 없으면 옆으로 치우고 빈 상태로 간다. 치워 두는 것은 나중에
        # 무슨 일이 있었는지 볼 수 있어야 하기 때문이다.
        try:
            CONSOLE_STATE.replace(CONSOLE_STATE.with_suffix(".broken.json"))
        except OSError:
            pass
        return empty


def _write_console(data: dict[str, Any]) -> None:
    CONSOLE_STATE.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp = CONSOLE_STATE.with_suffix(".writing.json")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, CONSOLE_STATE)


def _save_console(data: dict[str, Any]) -> None:
    """한 번에 통째로 바뀌게 쓴다. 반쯤 쓰인 파일을 남기지 않는다."""
    with _CONSOLE_LOCK:
        _write_console(data)


def _update_console(change) -> dict[str, Any]:
    """읽고-고치고-쓰는 것을 **하나로 묶는다.**

    이게 없으면 값이 조용히 되돌아간다. 화면은 3초마다 상태를 묻고 그때마다
    기록이 쌓이는데, 기록을 쓰는 쪽이 '고르기 전'에 읽은 상태를 들고 있다가
    나중에 저장하면 **방금 고른 로봇이 옛 값으로 덮인다.** 눌러도 선택이
    안 되는 것처럼 보인 이유가 이것이다 — 선택은 됐고 곧바로 되돌아갔다.
    """
    with _CONSOLE_LOCK:
        state = _console_unlocked()
        change(state)
        _write_console(state)
        return state


def _log(message: str, kind: str = "s-log-info") -> None:
    entry = {"ts": datetime.now().strftime("%H:%M:%S"), "message": message, "cls": kind}

    def add(state: dict[str, Any]) -> None:
        state.setdefault("log", []).insert(0, entry)
        del state["log"][80:]

    _update_console(add)


def _store(instance_id: str) -> InstanceStore:
    return InstanceStore(INSTANCE_DIR, instance_id)


def _family_of(instance_id: str) -> str:
    """이 로봇의 팔 계열. 동작 카드는 이 단위로 함께 쓴다."""
    try:
        instance = registry.get(instance_id)
    except RegistryError:
        return ""
    picked = str(_store(instance_id).runtime().get("attached_robot") or "").strip()
    if picked and picked in registry.modules and registry.modules[picked].module_class == "arm":
        return picked
    return instance.arm().module_id if instance.arm() else ""


def _poses(instance_id: str) -> InstanceStore:
    """동작 카드는 **같은 팔을 쓰는 로봇끼리 함께 쓴다.**

    자세는 몸이 같으면 통한다. 로봇마다 따로 두면, 로봇을 하나 더 만든 사람은
    가르친 것을 처음부터 다시 가르쳐야 한다 — 새로 만든 로봇의 동작 목록이
    비어 있어 아래 '동작 순서'에 넣을 카드가 하나도 없었다(사용자 보고).
    dexter_hangeul도 같은 계열끼리 공용 라이브러리로 다뤘다.

    처음 열 때, 이 계열 로봇들이 각자 갖고 있던 자세를 한 곳으로 모은다.
    """
    family = _family_of(instance_id)
    if not family:
        return _store(instance_id)
    shared = InstanceStore(INSTANCE_DIR, f"_family_{family}")
    doc = shared.poses()
    if not doc.get("merged"):
        merged = dict(doc.get("poses") or {})
        for other in registry.all():
            # 모을 때는 **그 로봇에 실제로 꽂힌 팔**로만 가른다. 사람이 화면에서
            # 바꾼 값으로 가르면 MyCobot 자세가 OMX 창고로 섞여 들어간다(실측).
            if not other.arm() or other.arm().module_id != family:
                continue
            for pose_id, pose in (_store(other.instance_id).poses().get("poses") or {}).items():
                merged.setdefault(pose_id, pose)
        shared.save_poses({**doc, "poses": merged, "merged": True})
    return shared


def _instance(instance_id: str):
    # 부품 기술서가 바뀌었으면 여기서 다시 읽는다 — 교체 즉시 다른 몸이 된다.
    if registry.refresh():
        _stamp_new_modules()
    try:
        return registry.get(instance_id)
    except RegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _stamp_legacy_poses() -> int:
    """옛 저장소에서 가져온 자세에는 '어떤 몸으로 가르쳤는지'가 없다.

    지금 몸을 기준선으로 한 번만 찍어 준다. 이 뒤로 부품이 바뀌면 그 자세는
    실행 전에 막힌다(BLOCKED_PART_CHANGED). 없는 값을 채우기만 하고
    이미 찍힌 값은 건드리지 않는다.
    """
    stamped = 0
    for instance in registry.all():
        store = _store(instance.instance_id)
        doc = _poses(instance.instance_id).poses()
        poses = doc.get("poses") or {}
        changed = False
        for pose in poses.values():
            if isinstance(pose, dict) and not pose.get("configuration_fingerprint"):
                pose["configuration_fingerprint"] = instance.fingerprint()
                pose.setdefault("verification", "UNVERIFIED")
                changed = True
                stamped += 1
        if changed:
            _poses(instance.instance_id).save_poses(doc)
    if stamped:
        _log(f"옛 자세 {stamped}건에 지금 구성을 기준선으로 기록했습니다", "s-log-info")
    return stamped


@app.on_event("startup")
def _on_startup() -> None:
    try:
        _stamp_legacy_poses()
    except Exception as exc:                    # 기준선 기록 실패가 기동을 막지는 않는다
        _log(f"자세 기준선 기록 실패: {exc}", "s-log-err")


def _stamp_new_modules() -> None:
    """기술서가 바뀐 뒤 새로 생긴 로봇의 자세만 기준선을 찍는다."""
    try:
        _stamp_legacy_poses()
    except Exception:
        pass


def _selected():
    if registry.refresh():
        _stamp_new_modules()
    state = _console()
    chosen = state.get("selected")
    if chosen and chosen in registry.configs:
        return registry.get(chosen)
    robots = registry.all()
    if not robots:
        raise HTTPException(status_code=404, detail="등록된 로봇이 없습니다")
    return robots[0]


# ── 화면 계약: 상태 ─────────────────────────────────────────────
def _robot_row(instance) -> dict[str, Any]:
    """기존 화면이 기대하는 로봇 행 형태."""
    store = _store(instance.instance_id)
    rt = store.runtime()
    sequence = store.sequence()
    health = runtime.health(instance)
    poses = _poses(instance.instance_id).poses().get("poses") or {}
    steps = []
    for step in sequence.get("steps") or []:
        pose_id = step.get("pose_id") or ""
        pose = poses.get(pose_id)
        steps.append({
            "step_id": step.get("step_id"),
            "pose_id": pose_id,
            "display_name_kr": (pose or {}).get("display_name_kr") or pose_id,
            "deleted": pose is None,
        })
    return {
        "robot_id": instance.instance_id,
        "display_name": instance.display_name,
        "enabled": True,
        "model": (instance.arm().module_id if instance.arm() else ""),
        "adapter": "runtime_link",
        # 화면의 '로봇 선택' 목록은 부품 종류(arm_omx 등)로 되어 있다.
        # **사람이 고른 값을 그대로 돌려준다.** 여기서 매번 다시 계산해 덮으면
        # 골라도 원래 값으로 되돌아간다. 한 번도 고른 적이 없을 때만 그 로봇의
        # 팔을 기본값으로 보인다.
        "attached_robot": (rt.get("attached_robot")
                           if "attached_robot" in rt
                           else (instance.arm().module_id if instance.arm() else None)),
        "selected_in_ui": _console().get("selected") == instance.instance_id,
        "sequence_name": sequence.get("sequence_name") or "",
        "step_count": len(sequence.get("steps") or []),
        "sequence_steps": steps,
        "run_state": rt.get("run_state") or "대기",
        "simple_state": rt.get("run_state") or "대기",
        # 화면은 이 값을 그대로 그린다. 낱말은 terms.py에만 있으므로 두 말을
        # 함께 보낸다 — 화면이 제 사전을 따로 두면 낱말이 둘이 된다(규칙 1).
        "simple_state_i18n": {
            "ko": terms.text(f"state.run.{rt.get('run_state') or '대기'}", "ko"),
            "en": terms.text(f"state.run.{rt.get('run_state') or '대기'}", "en"),
        },
        "last_result": rt.get("last_result") or "",
        "last_error": rt.get("last_error") or "",
        "multi_run": rt.get("multi_run") or {"state": "idle"},
        # 새 구조에서 추가된 것 — 화면은 무시해도 되지만 있으면 쓴다
        "connected": health["connected"],
        "simulated": bool(health.get("simulated")),
        "health_reason": health["reason"],
        "fingerprint": instance.fingerprint(),
        "modules": [m.to_dict() for m in instance.modules()],
    }


@app.get("/api/status")
def status() -> dict:
    state = _console()
    return {
        "ok": True,
        "robots": [_robot_row(i) for i in registry.all()],
        "selected_robot_id": state.get("selected") or (
            registry.all()[0].instance_id if registry.all() else None),
        "mode": state.get("mode", terms.MODE_USER),
        "problems": registry.problems,
        "hardware_execution": "DELEGATED_TO_RUNTIME",
    }


@app.get("/api/robots")
def list_robots() -> dict:
    """화면은 **selected_robot_id로 지금 고른 로봇을 안다.**

    이걸 안 주면 화면은 자기 나름의 기본값(robot_4가 있으면 robot_4, 없으면
    목록 첫 대)으로 되돌아간다. 그래서 다른 로봇을 눌러도 새로고침 뒤 늘
    같은 로봇이 골라진 것으로 보였다 — 선택이 안 되는 것처럼 보인 이유다.
    dexter_hangeul은 처음부터 이 값을 주고 있었다.
    """
    return {"ok": True, "selected_robot_id": _selected().instance_id,
            "robots": [_robot_row(i) for i in registry.all()]}


@app.post("/api/robots/{robot_id}/select")
def select_robot(robot_id: str) -> dict:
    instance = _instance(robot_id)
    _update_console(lambda state: state.__setitem__("selected", instance.instance_id))
    _log(f"{instance.display_name} 선택")
    return {"success": True, "robot_id": instance.instance_id,
            "display_name": instance.display_name}


@app.post("/api/robots/select-by-model")
def select_robot_by_model(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """화면의 로봇 종류 드롭다운이 콘솔의 선택을 바꾸도록. 이게 없으면 화면은
    OMX를 보고 있는데 콘솔은 MyCobot을 잡고 있어, OMX 화면에 MyCobot 알림이 뜬다."""
    model = str(payload.get("robot_model") or payload.get("model") or "")
    for instance in registry.all():
        if instance.runtime_model() == model:
            _update_console(lambda state: state.__setitem__("selected", instance.instance_id))
            _log(f"{instance.display_name} 선택 (종류: {model})")
            return {"success": True, "robot_id": instance.instance_id,
                    "display_name": instance.display_name, "robot_model": model}
    return {"success": False, "robot_model": model,
            "error": f"'{model}' 종류로 등록된 로봇이 없습니다"}


@app.post("/api/robots/{robot_id}/attach")
def attach_robot(robot_id: str, payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """화면의 '로봇 선택' 칸 — **화면이 고른 값을 그대로 담는다.**

    전에는 화면이 보낸 type을 통째로 무시하고, 그 로봇의 팔과 연결 상태로
    값을 다시 계산해 덮었다. 그래서 목록에서 무엇을 골라도 원래 값으로
    돌아왔다 — 선택이 안 되는 것처럼 보인 이유다.
    dexter_hangeul(web.py:498)이 하던 그대로 돌린다.
    """
    instance = _instance(robot_id)
    store = _store(robot_id)
    if (store.runtime().get("run_state") or "") == "실행":
        raise HTTPException(
            status_code=400,
            detail=f"{instance.display_name} 실행 중에는 연결을 변경할 수 없습니다. "
                   "일시 정지 또는 완료 후 변경하세요.")
    wanted = str(payload.get("type") or payload.get("attached_robot") or "").strip()
    if wanted in ("", "없음", "none", "None"):
        store.update_runtime(attached_robot=None)
        _log(f"{instance.display_name} 로봇 연결 해제 → 없음", "s-log-info")
        return {"success": True, "robot_id": robot_id, "attached_robot": None, "reason": ""}
    known = robot_types()["types"]
    if wanted not in known:
        raise HTTPException(status_code=400,
                            detail=f"알 수 없는 로봇 종류: {wanted} (있는 것: {', '.join(known)})")
    store.update_runtime(attached_robot=wanted)
    # 팔을 바꾸면 **부품 목록까지 바꾼다.** 주소만 옮기고 부품을 그대로 두면
    # 반은 MyCobot 반은 OMX인 로봇이 된다 — 화면은 J1~J6을 보이는데 명령은
    # OMX 런타임으로 나가고, 읽은 값이 뒤섞인다(실측: -430 vs 180080).
    # 부품을 바꾸면 다른 글자가 된다는 것이 이 제품의 규칙이다.
    path = ROBOT_CONFIG_DIR / f"{robot_id}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        hand = next((m.module_id for m in registry.modules.values()
                     if m.module_class == "hand"
                     and m.mount_parent == wanted), None)
        arm = registry.modules[wanted]
        modules = [x for x in (arm.mount_parent, wanted, hand) if x]
        url = _arm_runtime_url(wanted)
        if data.get("modules") != modules or (url and data.get("runtime_url") != url):
            data["modules"] = modules
            if url:
                data["runtime_url"] = url
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            registry.reload()
            instance = _instance(robot_id)
    health = runtime.health(instance)
    _log(f"{instance.display_name} 로봇 연결: {wanted}"
         + ("" if health["connected"] else f" — {health['reason']}"),
         "s-log-ok" if health["connected"] else "s-log-err")
    return {"success": True, "robot_id": robot_id, "attached_robot": wanted,
            "reason": "" if health["connected"] else health["reason"]}


@app.get("/api/robot-types")
def robot_types() -> dict:
    """붙일 수 있는 팔 — **사람이 읽는 이름을 함께 준다.**

    화면의 '로봇 선택' 칸은 이 목록을 그대로 보여준다. 이름을 안 주면
    거기에 arm_mycobot 같은 부품 번호가 뜬다 — 사람이 방금 지은 로봇
    이름과 달라 무엇을 고르는 칸인지 알 수 없다.
    """
    import json as _json
    seen: dict[str, str] = {}
    cards = []
    for module in sorted(registry.modules.values(), key=lambda m: m.module_id):
        if module.module_class != "arm":
            continue
        seen[module.module_id] = module.display_name or module.module_id
        raw = {}
        if module.source_path:
            try:
                raw = _json.loads(Path(module.source_path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
        evidence = raw.get("hardware_evidence") or {}
        hand = next((m.display_name for m in registry.modules.values()
                     if m.module_class == "hand" and m.mount_parent == module.module_id), "")
        cards.append({
            "part_id": module.module_id,
            "label": module.display_name or module.module_id,
            "model": module.runtime_model,
            "joint_count": len([j for j in module.joints if not j.get("disabled")]),
            "joint_total": len(module.joints),
            "hand": hand,
            "reach_mm": (module.limits or {}).get("reach_mm"),
            "payload_g": (module.limits or {}).get("payload_g"),
            "evidence": evidence.get("state") or "unknown",
            "evidence_ko": evidence.get("ko") or "",
            "evidence_en": evidence.get("en") or "",
        })
    return {"ok": True, "robot_types": sorted(seen), "types": sorted(seen),
            "type_labels": {k: seen[k] for k in sorted(seen)}, "cards": cards}


# ── 화면 계약: 관절·자세·순서 ───────────────────────────────────
def _attached_view(instance):
    """화면에 보일 몸 — **'로봇 선택' 칸에서 고른 팔이 먼저다.**

    dexter_hangeul도 같다: "The attached robot is authoritative"(web.py:88).
    이게 없으면 로봇1에 MyCobot을 골라도 아래 '자세 만들기'는 계속 옛 팔의
    관절을 보인다. 관절 수·번호·단위가 실제와 어긋난 채로 자세를 가르치게 된다.
    """
    picked = str(_store(instance.instance_id).runtime().get("attached_robot") or "").strip()
    current = instance.arm()
    if not picked or (current and picked == current.module_id) or picked not in registry.modules:
        return instance
    arm = registry.modules[picked]
    if arm.module_class != "arm":
        return instance
    hand = next((m.module_id for m in registry.modules.values()
                 if m.module_class == "hand" and m.mount_parent == arm.module_id), None)
    wanted = [x for x in (arm.mount_parent, arm.module_id, hand) if x]
    try:
        view = cfg.build(instance.instance_id, instance.display_name, registry.modules, wanted)
    except cfg.ConfigurationError:
        return instance
    # 런타임 주소는 그 로봇의 것을 그대로 쓴다. 새로 만든 구성에는 주소가 없어서
    # 이걸 빠뜨리면 안전 범위를 물으러 가다 터진다(실측).
    view.runtime_url_value = instance.runtime_url
    return view


@app.get("/api/robot-joints")
def robot_joints(instance_id: str = "") -> dict:
    """관절 목록. **표시 이름은 용어 소스에서만 나온다.**

    화면은 이 응답으로 단위를 정한다. `robot_family`가 로봇 종류와 다르면
    화면은 OMX인 줄 알고 틱으로 보여주고 ±50틱씩 움직이려 든다 —
    MyCobot에서는 그게 0.05°라 아무 일도 안 일어난다(실제로 그랬다).
    """
    chosen = _instance(instance_id) if instance_id else _selected()
    instance = _attached_view(chosen)
    view = instance.joint_view()
    hand_module = instance.hand()
    unit = instance.unit()
    model = instance.runtime_model() or (instance.arm().module_id if instance.arm() else "")

    # 로봇 단위의 관절 범위는 런타임(실물을 아는 쪽)이 답한다.
    limits = runtime.forward(instance, "/api/safety-limits", None, method="GET")
    bands = (limits or {}).get("joint_tick_limits") or {}

    def middle(joint_id: int, fallback: int) -> int:
        """가운데 값 = 그 단위의 0도 자리. 틱이면 2048, 밀리도면 0이다."""
        center = int(unit.get("center", fallback))
        band = bands.get(str(joint_id))
        if not band:
            return center
        low, high = int(band[0]), int(band[1])
        return max(low, min(high, center))

    arm = [{"id": str(j["joint_id"]), "joint_id": j["joint_id"], "role": "arm",
            "label_kr": j["label"], "label_en": terms.joint_label(i, lang="en"),
            "default_ticks": middle(j["joint_id"], 2048),
            # 꺼둔 관절도 자리를 지킨다. 빼면 뒤 관절 번호가 당겨져 실제 팔과 어긋난다.
            "excluded": bool(j.get("disabled")),
            "excluded_reason": j.get("reason", "")}
           for i, j in enumerate(v for v in view if v["role"] != "hand")]
    hand_view = [v for v in view if v["role"] == "hand"]
    gripper = None
    if hand_view:
        joint_id = hand_view[0]["joint_id"]
        gripper = {"id": str(joint_id), "joint_id": joint_id, "role": "gripper",
                   "label_kr": hand_view[0]["label"],
                   "label_en": terms.joint_label(0, is_hand=True, lang="en"),
                   "default_ticks": (hand_module.command or {}).get("open", 2048)}

    # 사람이 보는 단위는 부품 기술서가 정한다(도 ↔ 틱/밀리도).
    if unit.get("kind") == "millidegree":
        value_units = {"position": "degrees", "raw_position": "millidegrees",
                       "gripper": "percent", "jog_arm": "degrees", "jog_gripper": "percent"}
    else:
        value_units = {"position": "ticks", "raw_position": "ticks", "gripper": "ticks",
                       "jog_arm": "ticks", "jog_gripper": "ticks"}

    return {
        "robot_id": model,
        "robot_family": model,
        "instance_id": instance.instance_id,
        "robot_model": model,
        "device": instance.device_name(),
        "arm_joints": arm,
        "gripper_joint": gripper,
        "all_joints": arm + ([gripper] if gripper else []),
        "arm_joint_count": len(arm),
        "has_gripper": gripper is not None,
        "joint_tick_limits": bands,
        "value_units": value_units,
        "excluded_joints": [module_mod.normalize_joint_id(j["id"])
                            for j in (instance.arm().joints if instance.arm() else [])
                            if j.get("disabled")],
        # 관절 식별자는 **숫자일 수도 이름일 수도 있다.**
        "id_policy": "opaque_joint_ids",
        "supported_arm_joint_count": {"min": 3, "max": 8},
    }


@app.get("/api/simple-catalog")
def simple_catalog() -> dict:
    instance = _selected()
    return {
        "robot_id": instance.instance_id,
        "robot_model": instance.arm().module_id if instance.arm() else "",
        "robot_family": instance.arm().module_id if instance.arm() else "",
        "robot_label": instance.display_name,
        "movements": _poses(instance.instance_id).movements(),
        "source": "hangeul_robot.instance_store",
    }


VOLATILE_SEQUENCE_NAME = "(지정됨)"


def _step_to_skill_id(step: dict[str, Any]) -> str:
    if step.get("type") == "gripper" and step.get("action") == "open":
        return "pose_grip_open"
    if step.get("type") == "gripper" and step.get("action") == "close":
        return "pose_grip_close"
    return str(step.get("pose_id") or step.get("action") or step.get("step_id") or "")


def _skill_id_to_step(skill_id: Any, index: int) -> dict[str, Any]:
    raw = str(skill_id)
    step_id = f"step_{index:03d}"
    if raw == "pose_grip_open":
        return {"step_id": step_id, "type": "gripper", "action": "open"}
    if raw == "pose_grip_close":
        return {"step_id": step_id, "type": "gripper", "action": "close"}
    return {"step_id": step_id, "type": "pose", "pose_id": raw, "speed": "slow"}


@app.get("/api/sequences")
def sequences() -> dict:
    """저장 순서 묶음 전체 — **이름 → 동작 목록의 지도를 그대로 준다.**

    화면은 이 응답을 통째로 목록으로 쓴다(`state.savedSequences = data`).
    {"ok":..., "robot_id":..., "sequences":{...}}처럼 감싸서 주면 화면에
    ok · robot_id · sequences 라는 이름의 유령 순서 카드 세 개가 뜨고,
    진짜로 저장한 순서는 목록에 나타나지 않는다 — 실제로 그랬다.
    dexter_hangeul의 응답 모양이 정본이다.
    """
    instance = _selected()
    store = _store(instance.instance_id)
    result = {name: ids for name, ids in (store.library().get("sequences") or {}).items() if ids}
    # 라이브러리에 아직 없는 '지금 지정된 실행 순서'도 목록에서 보이게 한다.
    active = store.sequence()
    steps = active.get("steps") or []
    active_name = active.get("sequence_name")
    if steps and active_name and active_name != VOLATILE_SEQUENCE_NAME and active_name not in result:
        result[active_name] = [_step_to_skill_id(step) for step in steps]
    return result


@app.get("/api/hangeul/log")
def get_log() -> dict:
    return {"ok": True, "entries": _console().get("log", [])}


@app.post("/api/hangeul/log")
def append_log(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    _log(str(payload.get("message") or ""), str(payload.get("cls") or "s-log-info"))
    return {"ok": True}


# ── 화면 계약: 기능 신호등(새로 추가된 것) ──────────────────────
@app.get("/api/capabilities")
def get_capabilities(instance_id: str = "") -> dict:
    instance = _instance(instance_id) if instance_id else _selected()
    health = runtime.health(instance)
    return {
        "ok": True,
        "instance_id": instance.instance_id,
        "connected": health["connected"],
        "reason": health["reason"],
        "fingerprint": instance.fingerprint(),
        "modules": [m.to_dict() for m in instance.modules()],
        "capabilities": [c.to_dict() for c in
                         capabilities.visible(instance, health["capability_health"],
                                                 health.get("parts"))],
    }


@app.get("/api/terms")
def get_terms(lang: str = "ko", mode: str = terms.MODE_USER) -> dict:
    return {"lang": lang, "mode": mode, "terms": terms.bundle(lang, mode)}


# ── 화면 계약: 실물 (전부 런타임으로 넘긴다) ────────────────────
@app.get("/api/read-pose")
def read_pose(instance_id: str = "") -> dict:
    instance = _instance(instance_id) if instance_id else _selected()
    answer = runtime.read_pose(instance)
    # 화면은 점검 결과도 같이 읽는다. 못 읽었으면 못 읽었다고 적어 준다.
    answer.setdefault("hardware_preflight", {})
    answer.setdefault("present", {})
    return answer


@app.post("/api/execute-actual")
def execute_actual(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    return _execute_pose(_selected(), payload)


def _execute_pose(instance, payload: dict[str, Any], *, in_sequence: bool = False) -> dict:
    """자세 하나를 실행하는 유일한 길. 화면 버튼도, 순서 실행도 여기를 지난다.

    관문 순서: 부재 모드 → 능력 → 장치 임대 → 가르쳤나 → 부품 바뀌었나 → 런타임.
    """
    away = get_away_mode()
    if away["away_mode"]:
        reason = "야간 자동 시간대" if away["auto_active"] and not away["manual"] else "부재 모드"
        _log(f"실행 차단: {reason}", "s-log-err")
        return {"verdict": "BLOCKED_AWAY_MODE",
                "blocked_reasons": [f"{reason}라서 실행하지 않습니다"],
                "actual_hardware_called": False}
    skill_id = str(payload.get("skill_id") or "")

    # C6: 없는 능력은 런타임까지 가지 않는다
    states, health = _capability_states(instance)
    steps = [{"kind": "pose", "label": skill_id, "targets": ["stored"]}]
    gate = task_mod.check_runnable(steps, instance, states)
    if not gate["runnable"]:
        _log(f"{instance.display_name}: 실행 차단 — {gate['blockers'][0]}", "s-log-err")
        return {"verdict": "BLOCKED_CAPABILITY", "blocked_reasons": gate["blockers"],
                "actual_hardware_called": False}

    # C10: 장치에 쓰기 전에 임대를 받는다. 남이 쥐고 있으면 보내지 않는다.
    resource = instance.runtime_url or instance.instance_id
    try:
        lease = leases.acquire(resource, CONSOLE_HOLDER)
        leases.check_write(resource, CONSOLE_HOLDER, lease.generation)
    except LeaseError as exc:
        _log(f"{instance.display_name}: 실행 차단 — {exc}", "s-log-err")
        return {"verdict": "BLOCKED_DEVICE_BUSY", "blocked_reasons": [str(exc)],
                "actual_hardware_called": False}

    pose = (_poses(instance.instance_id).poses().get("poses") or {}).get(skill_id) or {}
    targets = payload.get("targets") or pose.get("targets") or {}
    if not targets:
        _log(f"{instance.display_name}: 실행 차단 — 이 로봇에 없는 자세({skill_id})", "s-log-err")
        return {"verdict": "BLOCKED_NOT_TAUGHT",
                "blocked_reasons": [f"이 로봇에서 가르치지 않은 자세입니다: {skill_id}"],
                "actual_hardware_called": False}

    # C5 검문소: 이 자세를 가르칠 때의 몸과 지금 몸이 같은가.
    # 손을 바꾸거나 축이 줄면 옛 관절값은 다른 곳을 가리킨다 — 다시 가르쳐야 한다.
    stamped = str(pose.get("configuration_fingerprint") or "")
    if stamped and stamped != instance.fingerprint():
        _log(f"{instance.display_name}: 실행 차단 — 부품이 바뀐 뒤 다시 가르치지 않은 자세"
             f"({skill_id})", "s-log-err")
        return {"verdict": "BLOCKED_PART_CHANGED",
                "blocked_reasons": [
                    "부품이 바뀐 뒤로 이 자세를 다시 가르치지 않았습니다. "
                    "로봇을 원하는 자세로 옮긴 뒤 '자세 저장'으로 다시 저장하세요"],
                "taught_with": stamped, "current_configuration": instance.fingerprint(),
                "actual_hardware_called": False}
    passthrough = {k: v for k, v in payload.items()
                   if k not in ("skill_id", "speed", "targets", "operator")}
    speed = str(payload.get("speed") or "slow")
    result = runtime.run(instance, skill_id, speed=speed, targets=targets, extra=passthrough)

    # 자세 카드의 주인은 콘솔이다. 런타임이 "그런 자세 모른다"고 막으면
    # 카드를 심어주고 한 번만 다시 시킨다 — 사람이 다시 가르칠 일은 아니다.
    verdict = str(result.get("verdict") or "")
    if any(k in verdict for k in runtime.UNKNOWN_TASK_VERDICTS):
        card = dict(pose)
        card.update({"skill_id": skill_id, "targets": targets})
        synced = runtime.sync_task(instance, card)
        if synced.get("success"):
            _log(f"{instance.display_name}: 자세 카드를 로봇에 전달했습니다 ({skill_id})",
                 "s-log-info")
            result = runtime.run(instance, skill_id, speed=speed,
                                 targets=targets, extra=passthrough)
        else:
            _log(f"{instance.display_name}: 자세 카드 전달 실패 — "
                 f"{synced.get('reason') or synced.get('error') or '이유 없음'}", "s-log-err")

    # 순서 실행 중에는 '대기'로 덮어쓰지 않는다 — 화면이 실행 중을 놓친다.
    if in_sequence:
        _store(instance.instance_id).update_runtime(last_result=result.get("verdict", ""))
    else:
        _store(instance.instance_id).update_runtime(
            last_result=result.get("verdict", ""), run_state="대기")
    _log(f"{instance.display_name}: {skill_id} → {result.get('verdict','응답 없음')}",
         "s-log-ok" if result.get("ok") else "s-log-err")
    return result.get("detail") or result


@app.post("/api/estop")
def estop(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """멈춤은 어떤 상태에서도 나간다. 대상이 없으면 전체."""
    targets = ([registry.get(payload["robot_id"])] if payload.get("robot_id")
               else registry.all())
    results = [{"robot_id": i.instance_id, **runtime.stop(i)} for i in targets]
    failed = [r for r in results if not r.get("stopped")]
    _log(f"긴급정지 요청: {len(results)}대", "s-log-err")
    # 한 대라도 못 멈췄으면 그대로 말한다. 조용히 성공이라고 하면 사람은
    # 멈춘 줄 알고 작업 공간에 들어간다.
    return {"success": True, "results": results, "error": "",
            "warning": ("" if not failed else
                        f"{len(failed)}대가 멈춤에 응답하지 않았습니다: "
                        + ", ".join(r["robot_id"] for r in failed))}


@app.post("/api/jog")
def jog(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    instance = _selected()
    return runtime.forward(instance, "/api/jog", payload)


@app.post("/api/move-to")
def move_to(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    instance = _selected()
    return runtime.forward(instance, "/api/move-to", payload)


@app.get("/api/safety-limits")
def safety_limits(instance_id: str = "") -> dict:
    instance = _instance(instance_id) if instance_id else _selected()
    return runtime.forward(instance, "/api/safety-limits", None, method="GET")


# ── 부재 모드 ───────────────────────────────────────────────────
def _schedule_active_now(schedule: dict[str, Any]) -> bool:
    """지금이 야간 자동 시간대인가. 자정을 넘어가는 구간(22:00~07:00)도 계산한다."""
    if not schedule.get("enabled"):
        return False
    start, end = schedule.get("start") or "", schedule.get("end") or ""
    if not start or not end:
        return False
    now = datetime.now().strftime("%H:%M")
    if start <= end:
        return start <= now < end
    return now >= start or now < end          # 자정을 넘는 구간


@app.get("/api/away-mode")
def get_away_mode() -> dict:
    """화면 계약: away_mode를 최상위에 둔다."""
    state = _console()
    schedule = state.get("away_schedule") or {}
    manual = bool(state.get("away_mode"))
    auto = _schedule_active_now(schedule)
    return {"success": True, "away_mode": manual or auto,
            "manual": manual, "auto_active": auto}


@app.post("/api/away-mode")
def set_away_mode(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    state = _update_console(lambda s: s.__setitem__("away_mode", bool(payload.get("away_mode"))))
    _log("부재 모드 " + ("켜짐 — 새 동작을 받지 않습니다" if state["away_mode"] else "꺼짐"),
         "s-log-err" if state["away_mode"] else "s-log-ok")
    # 로봇 런타임에도 알린다. 콘솔을 거치지 않는 실행도 막히도록.
    for instance in registry.all():
        runtime.forward(instance, "/api/away-mode", {"away_mode": state["away_mode"]})
    return {"success": True, "away_mode": state["away_mode"]}


@app.get("/api/task-list")
def task_list(instance_id: str = "") -> dict:
    """이 몸으로 할 수 있는 작업. 못 하는 것도 이유와 함께 보여준다."""
    instance = _instance(instance_id) if instance_id else _selected()
    store = _tasks()
    states, health = _capability_states(instance)
    out = []
    for meaning_id in store.meanings:
        resolved = store.resolve(meaning_id, instance)
        gate = task_mod.check_runnable(resolved["steps"], instance, states)
        out.append({**resolved, "runnable": gate["runnable"], "blockers": gate["blockers"]})
    return {"ok": True, "instance_id": instance.instance_id,
            "connected": health["connected"], "tasks": out}


@app.post("/api/task-save")
def task_save(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """작업의 **뜻**을 저장한다. 관절값은 여기 들어가지 않는다."""
    store = _tasks()
    try:
        record = store.save_meaning(
            str(payload.get("meaning_id") or ""),
            label=str(payload.get("label") or ""),
            steps=payload.get("steps") or [],
            icon=str(payload.get("icon") or "🤖"))
    except task_mod.TaskError as exc:
        return {"ok": False, "reason_code": exc.reason_code, "error": str(exc)}
    _save_tasks(store)
    _log(f"작업 저장: {record['label']}")
    return {"ok": True, "task": record}


@app.post("/api/task-teach")
def task_teach(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """이 몸에서의 **발음**(관절값)을 가르친다. 항상 미검증에서 시작한다."""
    instance = _instance(str(payload.get("instance_id") or "")) if payload.get("instance_id") else _selected()
    store = _tasks()
    try:
        record = store.save_realization(
            str(payload.get("meaning_id") or ""), instance,
            payload.get("step_targets") or [],
            operator=str(payload.get("operator") or "operator"))
    except task_mod.TaskError as exc:
        return {"ok": False, "reason_code": exc.reason_code, "error": str(exc)}
    _save_tasks(store)
    _log(f"{instance.display_name}에 가르침: {record['meaning_id']}", "s-log-ok")
    return {"ok": True, "realization": record}


# 화면은 이름을 name_kr/name_en으로 보내고, 런타임 계약과 저장 형식은
# display_name_kr/display_name_en을 쓴다. 한쪽만 읽으면 이름이 통째로 사라지고
# 카드에 POSE_1787108447 같은 번호만 남는다 — 실제로 그랬다. 둘 다 받는다.
def _pose_name(payload: dict[str, Any], *lang_keys: str) -> str:
    for key in lang_keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


@app.post("/api/save-pose")
def save_pose(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """가르친 자세 저장 — 이 구성에서의 발음이다."""
    instance = _selected()
    store = _poses(instance.instance_id)
    doc = store.poses()
    name_kr = _pose_name(payload, "name_kr", "display_name_kr")
    name_en = _pose_name(payload, "name_en", "display_name_en")
    if not name_kr and not name_en:
        # 이름 없는 카드는 만들지 않는다. 번호만 남은 카드는 사람이 못 읽는다.
        return {"success": False, "error": "동작 이름이 없습니다"}
    skill_id = str(payload.get("skill_id") or f"POSE_{int(datetime.now().timestamp())}")
    doc.setdefault("poses", {})[skill_id] = {
        "display_name_kr": name_kr or name_en,
        "display_name_en": name_en or name_kr,
        "description_kr": payload.get("description_kr") or "",
        "description_en": payload.get("description_en") or "",
        "targets": payload.get("targets") or {},
        "icon": payload.get("icon") or "🤖",
        "color": payload.get("color") or "#0ea5e9",
        "delay_sec": payload.get("delay_sec", 0.0),
        "motion_type": payload.get("motion_type") or "absolute",
        # 미세 이동으로 만든 자세는 그 단계까지 함께 남아야 다시 실행된다.
        # movements()는 이미 이 값을 읽고 있었는데 저장하는 쪽이 버리고 있었다.
        "micro_move_steps": payload.get("micro_move_steps") or [],
        "configuration_fingerprint": instance.fingerprint(),
        "verification": "UNVERIFIED",
    }
    store.save_poses(doc)
    _log(f"{instance.display_name}: 자세 저장 '{name_kr or name_en}'", "s-log-ok")
    return {"success": True, "skill_id": skill_id}


# 화면은 지울 것을 **주소줄**로 보낸다(`?skill_id=...`, 본문 없음). 본문에서만
# 찾으면 언제나 빈 이름으로 지우려 들어 아무것도 지워지지 않는다 — 화면에는
# 사유도 없는 "삭제 실패: "만 뜬다. 실제로 그랬다. 둘 다 본다.
@app.delete("/api/delete-pose")
@app.post("/api/delete-pose")
def delete_pose(skill_id: str = "",
                payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    instance = _selected()
    store = _poses(instance.instance_id)
    doc = store.poses()
    wanted = str(skill_id or payload.get("skill_id") or "").strip()
    if not wanted:
        return {"success": False, "error": "어떤 동작을 지울지 알 수 없습니다"}
    removed = doc.get("poses", {}).pop(wanted, None)
    if removed is None:
        return {"success": False, "error": f"그런 동작이 없습니다: {wanted}"}
    store.save_poses(doc)
    _log(f"{instance.display_name}: 동작 삭제 "
         f"'{removed.get('display_name_kr') or wanted}'", "s-log-info")
    return {"success": True, "robot_id": instance.instance_id, "skill_id": wanted}


@app.post("/api/save-sequence")
def save_sequence(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """순서 묶음 저장 — 라이브러리에 넣고, **그 로봇이 지금 실행할 순서로도 반영한다.**

    둘째가 없으면 저장은 됐는데 실행·다중 실행·순서 복사는 옛 순서를 계속 쓴다.
    dexter_hangeul이 하던 그대로다.
    """
    instance = _selected()
    store = _store(instance.instance_id)
    name = str(payload.get("name") or "").strip()
    ids = payload.get("skill_ids") or []
    if not name:
        return {"success": False, "error": "순서 이름이 필요합니다"}
    if not isinstance(ids, list) or not ids:
        return {"success": False, "error": "저장할 동작이 없습니다"}
    library = store.library()
    library["robot_id"] = instance.instance_id
    library.setdefault("sequences", {})[name] = list(ids)
    store.save_library(library)
    steps = [_skill_id_to_step(sid, i) for i, sid in enumerate(ids, 1)]
    store.save_sequence({"sequence_name": name, "steps": steps})
    _log(f"{instance.display_name}: 순서 저장 '{name}' {len(ids)}단계", "s-log-ok")
    return {"success": True, "robot_id": instance.instance_id, "name": name,
            "step_count": len(steps),
            "saved_sequence_count": len(library.get("sequences") or {})}


@app.post("/api/hangeul/assign-sequence")
def assign_sequence(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    instance = _instance(str(payload.get("robot_id") or "")) if payload.get("robot_id") else _selected()
    store = _store(instance.instance_id)
    ids = payload.get("skill_ids") or []
    if not ids:
        return {"success": False, "robot_id": instance.instance_id, "step_count": 0,
                "error": "지정할 동작이 없습니다"}
    store.save_sequence({"sequence_name": str(payload.get("name") or VOLATILE_SEQUENCE_NAME),
                         "steps": [_skill_id_to_step(sid, i) for i, sid in enumerate(ids, 1)]})
    _log(f"{instance.display_name}: 실행 순서 지정 {len(ids)}단계", "s-log-ok")
    return {"success": True, "robot_id": instance.instance_id,
            "step_count": len(ids), "error": ""}


@app.post("/api/hangeul/clear-sequence")
def clear_sequence(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    instance = _instance(str(payload.get("robot_id") or "")) if payload.get("robot_id") else _selected()
    store = _store(instance.instance_id)
    removed_steps = len(store.sequence().get("steps") or [])
    store.save_sequence({"sequence_name": "", "steps": []})
    # 화면은 default_pose_applied로 어떤 안내를 띄울지 고른다. 안 주면 늘 틀린
    # 쪽("아직 기본자세를 가르치지 않음")이 뜬다.
    poses = (_poses(instance.instance_id).poses().get("poses") or {})
    default_pose = next((sid for sid, pose in poses.items()
                         if "기본" in str(pose.get("display_name_kr") or "")), None)
    if default_pose:
        store.save_sequence({"sequence_name": "", "steps": [
            {"step_id": "step_001", "type": "pose", "pose_id": default_pose, "speed": "slow"}]})
    _log(f"{instance.display_name}: 실행 순서 지움 ({removed_steps}단계)", "s-log-info")
    return {"success": True, "robot_id": instance.instance_id, "error": "",
            "removed_steps": removed_steps, "default_pose_applied": bool(default_pose)}


@app.post("/api/advisor/suggest")
def advisor_suggest(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """도우미 — 지금 몸으로 가능한 것만 제안한다. 실행하지 않는다."""
    instance = _instance(str(payload.get("instance_id") or "")) if payload.get("instance_id") else _selected()
    states, _ = _capability_states(instance)
    return advisor.suggest(str(payload.get("query") or ""), instance, _tasks(), states)


@app.get("/api/leases")
def list_leases() -> dict:
    out = []
    for instance in registry.all():
        resource = instance.runtime_url or instance.instance_id
        lease = leases.read(resource)
        out.append({"instance_id": instance.instance_id, "resource": resource,
                    "lease": lease.to_dict() if lease else None})
    return {"ok": True, "leases": out}


# ── C11 나머지 화면 계약 ────────────────────────────────────────
def _require_module(instance, module_class: str, what: str):
    """관측 부품이 없으면 그 기능은 애초에 거절한다 (C12)."""
    if not instance.of_class(module_class):
        return {"success": False, "ok": False,
                "error": f"이 로봇에는 {what} 부품이 없습니다",
                "reason_code": "module_not_installed"}
    return None


# 화면의 '로봇 추가'는 부품 목록이 아니라 **로봇 종류 한 줄**을 보낸다
# (mycobot_280_m5 · omx). dexter_hangeul이 그렇게 받았기 때문이다. 부품 목록만
# 받으면 화면에서 추가할 방법이 없다 — 200을 돌려주고 아무것도 안 만들지 않아서
# 화면은 새로고침만 하고 로봇은 늘지 않았다. 종류를 부품 목록으로 옮겨 준다.
#
# 사람이 부르는 이름(omx, mycobot)은 **기술서의 model_aliases**가 들고 있다.
# 여기에 표로 적으면 로봇이 늘 때마다 콘솔을 고쳐야 한다 — 이 제품의 주장이 깨진다.
def _modules_for_model(model: str) -> list[str]:
    """로봇 종류 한 줄 → 꽂을 부품 목록. 기술서에서 찾는다(코드에 로봇 이름 없음)."""
    raw = model.strip()
    # 화면의 모델 격자와 '로봇 선택' 칸은 **부품 번호**(arm_mycobot)를 보낸다.
    # 사람이 적어 넣는 이름(mycobot, omx)도 그대로 받는다 — 두 길이 한 자리로 모인다.
    direct = registry.modules.get(raw)
    if direct is not None and direct.module_class == "arm":
        arm = direct
    else:
        wanted = raw.lower().removeprefix("mock_")
        arm = next((m for m in registry.modules.values()
                    if m.module_class == "arm"
                    and (m.runtime_model.lower() == wanted
                         or wanted in {a.lower() for a in m.model_aliases})), None)
    if arm is None:
        return []
    hand = next((m.module_id for m in registry.modules.values()
                 if m.module_class == "hand" and m.mount_parent == arm.module_id), None)
    return [x for x in (arm.mount_parent, arm.module_id, hand) if x]


def _arm_runtime_url(part_id: str) -> str:
    """그 팔의 런타임 주소 — **기술서에 적힌 그대로.**

    한때 여기서 '겹치지 않는 빈 포트'를 찾아 주었다. 겹침은 피했지만 그
    포트에는 아무도 없어서, 새로 만든 로봇은 전부 '런타임에 연결하지
    못했습니다'가 됐다. 같은 팔을 쓰는 로봇은 같은 런타임을 본다 —
    동시에 쓰지 못하게 막는 것은 장치 임대가 할 일이지 주소가 할 일이 아니다.
    """
    module = registry.modules.get(part_id)
    if module is None or module.module_class != "arm" or not module.source_path:
        return ""
    return str(json.loads(Path(module.source_path).read_text(encoding="utf-8"))
               .get("runtime_url") or "")


def _runtime_url_for(modules: list[str]) -> str:
    arm = next((m for m in modules
                if m in registry.modules and registry.modules[m].module_class == "arm"), "")
    return _arm_runtime_url(arm) if arm else ""


def _next_robot_number() -> int:
    """번호는 재사용하지 않는다 (dexter_hangeul과 같은 규칙).

    지운 로봇의 번호를 다시 쓰면 보관해 둔 옛 자산이 새 로봇에 붙는다.
    """
    numbers = [0]
    for source in (ROBOT_CONFIG_DIR, INSTANCE_DIR / "_removed"):
        if not source.exists():
            continue
        for path in source.glob("*.json"):
            tail = path.stem.rsplit("_", 1)[-1]
            if tail.isdigit():
                numbers.append(int(tail))
    return max(numbers) + 1


def _inherit_family_poses(instance_id: str, modules: list[str]) -> int:
    """같은 계열 로봇이 이미 가진 자세를 물려준다 (dexter_hangeul과 같은 동작).

    자세는 몸이 같으면 통한다. 새 로봇을 빈 화면으로 주면 사람은 처음부터
    다시 가르쳐야 한다. 계열이 다르면 물려주지 않는다 — 다른 몸의 발음이다.
    """
    arm = next((m for m in modules
                if m in registry.modules and registry.modules[m].module_class == "arm"), None)
    if not arm:
        return 0
    for other in registry.all():
        if other.instance_id == instance_id or not other.arm():
            continue
        if other.arm().module_id != arm:
            continue
        poses = _poses(other.instance_id).poses().get("poses") or {}
        if not poses:
            continue
        _poses(instance_id).save_poses(json.loads(json.dumps({"poses": poses})))
        return len(poses)
    return 0


@app.post("/api/robots/add")
def add_robot(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """로봇 추가 = 부품 목록을 적은 기술서 한 장을 만드는 것."""
    instance_id = str(payload.get("instance_id") or payload.get("robot_id") or "").strip()
    modules = payload.get("modules") or []
    model = str(payload.get("model") or payload.get("robot_model")
                or payload.get("robot_type") or payload.get("type") or "").strip()
    if not modules and model:
        modules = _modules_for_model(model)
        if not modules:
            known = sorted({m.module_id for m in registry.modules.values()
                            if m.module_class == "arm"})
            raise HTTPException(status_code=400,
                                detail=f"'{model}' 종류의 팔 기술서가 없습니다. "
                                       f"있는 종류: {', '.join(known)}")
    number = _next_robot_number()
    if not instance_id:
        instance_id = f"robot_{number}"
    if not modules:
        raise HTTPException(status_code=400, detail="로봇 종류나 부품 목록이 필요합니다")
    if instance_id in registry.configs:
        raise HTTPException(status_code=409, detail=f"이미 있는 로봇입니다: {instance_id}")
    unknown = [m for m in modules if m not in registry.modules]
    if unknown:
        raise HTTPException(status_code=400, detail=f"없는 부품: {', '.join(unknown)}")
    # 런타임 주소는 팔 기술서가 들고 있다 — 비워 두면 그 로봇은 아무 데도 닿지 않는다.
    runtime_url = str(payload.get("runtime_url") or "").strip() or _runtime_url_for(modules)
    # 이름을 안 적으면 '로봇N'. instance_id를 그대로 보여주면 사람이 읽을 수 없다.
    display_name = str(payload.get("display_name") or "").strip() or f"로봇{number}"
    ROBOT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = ROBOT_CONFIG_DIR / f"{instance_id}.json"
    path.write_text(json.dumps({
        "instance_id": instance_id,
        "display_name": display_name,
        "runtime_url": runtime_url,
        "modules": modules,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    registry.reload()
    # 만들었는데 목록에 없으면 화면에서는 '아무 일도 안 일어난 것'이 된다.
    # 조용히 두지 않는다 — 파일을 되돌리고 왜 못 넣었는지 그대로 말한다.
    if instance_id not in registry.configs:
        reason = "; ".join(p for p in registry.problems if p.startswith(f"{instance_id}:")) \
            or "알 수 없는 이유로 목록에 오르지 못했습니다"
        path.unlink(missing_ok=True)
        registry.reload()
        raise HTTPException(status_code=409, detail=reason)
    # 방금 만든 로봇을 곧바로 고른다. 이름을 지어 만들었는데 다른 로봇이
    # 골라진 채로 있으면, 이어서 가르치는 자세가 엉뚱한 로봇에 들어간다.
    _update_console(lambda state: state.__setitem__("selected", instance_id))
    inherited = _inherit_family_poses(instance_id, modules)
    _log(f"로봇 추가: {display_name} (부품 {len(modules)}개, 런타임 {runtime_url})"
         + (f" — 같은 계열 자세 {inherited}개 물려받음" if inherited else ""), "s-log-ok")
    return {"success": True, "robot_id": instance_id, "display_name": display_name,
            "model": model, "modules": modules, "runtime_url": runtime_url,
            "inherited_poses": inherited, "robot_family": modules[1] if len(modules) > 1 else "",
            "robot_count": len(registry.all()), "problems": registry.problems}


@app.delete("/api/robots/{robot_id}")
def delete_robot(robot_id: str) -> dict:
    """로봇 삭제 — 기술서만 지운다. **가르친 자산은 지우지 않는다.**"""
    path = ROBOT_CONFIG_DIR / f"{robot_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"없는 로봇: {robot_id}")
    archive = INSTANCE_DIR / "_removed"
    archive.mkdir(parents=True, exist_ok=True)
    path.rename(archive / f"{robot_id}.json")
    registry.reload()
    _log(f"로봇 삭제: {robot_id} (가르친 자산은 그대로 둡니다)", "s-log-info")
    return {"success": True, "robot_id": robot_id, "assets_kept": True}


@app.post("/api/robots/{robot_id}/rename")
def rename_robot(robot_id: str, payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    path = ROBOT_CONFIG_DIR / f"{robot_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"없는 로봇: {robot_id}")
    name = str(payload.get("display_name") or "").strip()
    if not name:
        return {"success": False, "error": "이름이 비어 있습니다"}
    data = json.loads(path.read_text(encoding="utf-8"))
    data["display_name"] = name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    registry.reload()
    return {"success": True, "robot_id": robot_id, "display_name": name}


# 눈·귀처럼 **덧붙이는 부품**만 여기서 꽂고 뺀다. 팔·손·몸통은 로봇의 정체라
# 바꾸면 다른 로봇이 된다 — 그건 로봇을 새로 만드는 일이고 /api/robots/add의 몫이다.
OPTIONAL_PART_CLASSES = ("eye", "ear")


@app.post("/api/robots/{robot_id}/parts")
def change_robot_parts(robot_id: str, payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """이미 있는 로봇에 부품을 꽂거나 뺀다.

    이 문이 없어서 눈을 단 로봇을 만들려면 JSON을 손으로 고쳐야 했다. 부품을
    꽂으면 능력이 생긴다는 것이 이 제품의 규칙인데, 꽂을 길이 없었다.

        {"attach": "eye_front"}   또는   {"detach": "eye_front"}
    """
    path = ROBOT_CONFIG_DIR / f"{robot_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"없는 로봇: {robot_id}")
    attach = str(payload.get("attach") or "").strip()
    detach = str(payload.get("detach") or "").strip()
    if bool(attach) == bool(detach):
        return {"success": False, "error": "attach 또는 detach 중 하나만 적어 주세요"}

    module_id = attach or detach
    part = registry.modules.get(module_id)
    if part is None:
        return {"success": False, "error": f"없는 부품입니다: {module_id}",
                "reason_code": "unknown_module"}
    if part.module_class not in OPTIONAL_PART_CLASSES:
        return {"success": False, "reason_code": "not_an_optional_part",
                "error": f"{module_id}는 덧붙이는 부품이 아닙니다 "
                         f"(여기서 다루는 것: {', '.join(OPTIONAL_PART_CLASSES)}). "
                         f"팔이나 손을 바꾸는 것은 다른 로봇을 만드는 일입니다"}

    data = json.loads(path.read_text(encoding="utf-8"))
    modules = list(data.get("modules") or [])
    before = registry.configs[robot_id].fingerprint() if robot_id in registry.configs else ""
    if attach:
        if module_id in modules:
            return {"success": True, "already": True, "modules": modules}
        modules.append(module_id)
    else:
        if module_id not in modules:
            return {"success": True, "already": True, "modules": modules}
        modules.remove(module_id)

    data["modules"] = modules
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    registry.reload()
    # 만들었는데 목록에 못 오르면 조용히 두지 않는다 — 되돌리고 이유를 말한다.
    if robot_id not in registry.configs:
        reason = "; ".join(p for p in registry.problems if p.startswith(f"{robot_id}:")) \
            or "부품을 꽂았더니 구성이 서지 않습니다"
        data["modules"] = [m for m in modules if m != module_id] if attach else modules + [module_id]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        registry.reload()
        return {"success": False, "error": reason, "reason_code": "configuration_failed"}

    after = registry.configs[robot_id].fingerprint()
    _log(f"{data.get('display_name') or robot_id}: {part.display_name or module_id}"
         + (" 꽂음" if attach else " 뺌"), "s-log-info")
    # 부품이 바뀌면 지문도 바뀐다. 옛 자세가 그대로 실행되지 않게 하는 자리다.
    return {"success": True, "robot_id": robot_id, "modules": modules,
            "fingerprint_before": before, "fingerprint": after,
            "fingerprint_changed": before != after}


@app.delete("/api/delete-sequence")
@app.post("/api/delete-sequence")
def delete_sequence(name: str = "",
                    payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """동작 삭제와 같은 이유로 주소줄과 본문을 둘 다 본다."""
    instance = _selected()
    store = _store(instance.instance_id)
    library = store.library()
    wanted = str(name or payload.get("name") or "").strip()
    if not wanted:
        return {"success": False, "error": "어떤 순서를 지울지 알 수 없습니다"}
    removed = library.get("sequences", {}).pop(wanted, None)
    library["robot_id"] = instance.instance_id
    store.save_library(library)
    removed_steps = len(removed) if removed is not None else 0
    # 지운 묶음이 지금 실행할 순서였다면 그것도 비운다 — 이름 없는 순서가
    # 남아 실행되는 일을 막는다(dexter_hangeul과 같은 처리).
    sequence = store.sequence()
    if sequence.get("sequence_name") == wanted:
        removed_steps = max(removed_steps, len(sequence.get("steps") or []))
        store.save_sequence({"sequence_name": "", "steps": []})
    elif removed is None:
        return {"success": False, "error": f"그런 순서가 없습니다: {wanted}"}
    _log(f"{instance.display_name}: 순서 삭제 '{wanted}' ({removed_steps}개 동작 제거)", "s-log-info")
    return {"success": True, "robot_id": instance.instance_id, "name": wanted,
            "removed_steps": removed_steps}


@app.post("/api/estop-reset")
def estop_reset(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """멈춤이 전체로 나갔으면 해제도 전체로 나간다 — 화면의 버튼이 하나이기 때문이다.
    한 대만 풀려면 robot_id를 준다."""
    robot_id = str(payload.get("robot_id") or "")
    targets = [_instance(robot_id)] if robot_id else registry.all()
    # 런타임은 '확실히 확인했다'는 표시를 요구한다. 사람이 누른 것만 여기 온다.
    body = dict(payload)
    body.setdefault("operator", "운영자")
    body["confirmed"] = True
    body.pop("robot_id", None)

    results = []
    for instance in targets:
        answer = runtime.forward(instance, "/api/estop-reset", body)
        ok = bool(answer.get("success"))
        results.append({"robot_id": instance.instance_id,
                        "robot_label": instance.display_name, **answer})
        if answer.get("verdict") == "RUNTIME_UNREACHABLE":
            _log(f"{instance.display_name}: 런타임이 떠 있지 않습니다 — 풀 정지가 없습니다",
                 "s-log-info")
            continue
        _log(f"{instance.display_name}: 정지 해제 "
             f"{'완료' if ok else '실패 — ' + str(answer.get('error') or answer.get('reason') or '')}",
             "s-log-ok" if ok else "s-log-err")

    # **안 떠 있는 로봇은 실패가 아니다.** 런타임이 없으면 정지가 걸릴 수도 없다.
    # 전에는 이것도 실패로 세어서, 로봇 다섯 대 중 세 대의 런타임이 안 떠 있으면
    # 나머지 두 대가 실제로 풀렸는데도 화면에는 "정지 해제 실패"만 떴다.
    # 사람은 로봇이 잠긴 줄 알고 다음으로 나아가지 못한다(2026-08-21 실측).
    absent = [r for r in results if r.get("verdict") == "RUNTIME_UNREACHABLE"]
    reached = [r for r in results if r.get("verdict") != "RUNTIME_UNREACHABLE"]
    failed = [r for r in reached if not r.get("success")]

    every = bool(reached) and not failed
    first = results[0] if len(results) == 1 else {}
    warning = ""
    if absent:
        warning = (f"{len(absent)}대는 런타임이 떠 있지 않아 건너뛰었습니다: "
                   + ", ".join(r.get("robot_label") or r["robot_id"] for r in absent))
    if not reached:
        return {**first, "success": False, "results": results, "warning": warning,
                "error": "정지를 풀 수 있는 로봇이 없습니다 — 런타임이 한 대도 떠 있지 않습니다"}
    return {**first, "success": every, "results": results, "warning": warning,
            "error": "" if every else
                     "정지를 풀지 못한 로봇: "
                     + ", ".join(r.get("robot_label") or r["robot_id"] for r in failed)}


@app.post("/api/pause-hold")
def pause_hold(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    targets = ([registry.get(payload["robot_id"])] if payload.get("robot_id")
               else registry.all())
    results = [{"robot_id": i.instance_id, **runtime.forward(i, "/api/pause-hold", payload)}
               for i in targets]
    failed = [r for r in results if r.get("success") is False]
    _log(f"일시정지 요청: {len(results)}대", "s-log-err")
    return {"success": True, "results": results, "error": "",
            "warning": ("" if not failed else
                        f"{len(failed)}대가 일시정지에 응답하지 않았습니다: "
                        + ", ".join(r["robot_id"] for r in failed))}


@app.post("/api/save-safety-limits")
def save_safety_limits(robot_model: str = "",
                       payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """화면은 어떤 로봇의 범위인지 주소줄로도 알려준다 — 받아서 그 로봇에 보낸다."""
    instance = _selected()
    if robot_model:
        instance = next((i for i in registry.all() if i.runtime_model() == robot_model), instance)
    return runtime.forward(instance, "/api/save-safety-limits", payload)


@app.post("/api/preview")
@app.post("/api/safety-precheck")
def preview(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """실행 전 점검 — 계산만 한다."""
    instance = _selected()
    states, health = _capability_states(instance)
    steps = [{"kind": "pose", "label": str(payload.get("skill_id") or ""), "targets": ["stored"]}]
    gate = task_mod.check_runnable(steps, instance, states)
    return {"ok": gate["runnable"], "verdict": "READY" if gate["runnable"] else "BLOCKED",
            "blocked_reasons": gate["blockers"], "connected": health["connected"],
            "actual_hardware_called": False}


@app.get("/api/security-log")
def security_log() -> dict:
    """콘솔이 남긴 기록 중 차단·정지만 추린다."""
    entries = [e for e in _console().get("log", []) if e.get("cls") == "s-log-err"]
    return {"ok": True, "events": entries, "count": len(entries)}


@app.post("/api/security-log/clear")
def clear_security_log(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """지우는 것도 기록으로 남긴다."""
    counted: dict[str, int] = {}

    def wipe(state: dict[str, Any]) -> None:
        counted["before"] = len(state.get("log", []))
        state["log"] = [{"ts": datetime.now().strftime("%H:%M:%S"),
                         "message": f"보안 기록 정리 ({counted['before']}건) — "
                                    f"요청자 {payload.get('operator') or '운영자'}",
                         "cls": "s-log-info"}]

    _update_console(wipe)
    before = counted.get("before", 0)
    return {"ok": True, "success": True, "cleared": before, "error": ""}


@app.get("/api/away-mode-schedule")
def get_away_schedule() -> dict:
    """화면 계약: enabled/start/end/active_now를 **최상위**에 둔다.
    (묶어서 내려보내면 화면이 읽지 못한다 — 실제로 그래서 동작하지 않았다.)"""
    schedule = _console().get("away_schedule") or {}
    return {"success": True,
            "enabled": bool(schedule.get("enabled")),
            "start": schedule.get("start") or "22:00",
            "end": schedule.get("end") or "07:00",
            "active_now": _schedule_active_now(schedule)}


@app.post("/api/away-mode-schedule")
def set_away_schedule(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    schedule = {"enabled": bool(payload.get("enabled")),
                "start": payload.get("start") or "22:00",
                "end": payload.get("end") or "07:00"}
    _update_console(lambda s: s.__setitem__("away_schedule", schedule))
    _log(f"야간 자동 부재 모드 {'켜짐' if schedule['enabled'] else '꺼짐'} "
         f"({schedule['start']}~{schedule['end']})", "s-log-ok")
    return {"success": True, **schedule, "active_now": _schedule_active_now(schedule)}


# ── 다중 실행 — 기본은 하나라도 준비 안 되면 시작하지 않는다 ────
# ── 여러 대 동시 실행 ───────────────────────────────────────────
# 상태 표시만 바꾸고 실제로는 아무것도 실행하지 않던 자리다. 화면에는 '실행 중'이
# 떴지만 로봇은 가만히 있었다. 여기서 실제로 순서를 돌린다.
_RUN_FLAGS: dict[str, dict[str, Any]] = {}
_RUN_LOCK = threading.Lock()


def _flags(robot_id: str) -> dict[str, Any]:
    with _RUN_LOCK:
        return _RUN_FLAGS.setdefault(robot_id, {"cancel": False, "paused": False})


def _seconds_until(start_at: str) -> float:
    """HH:MM까지 남은 시간. 지난 시각이면 0(즉시)."""
    if not start_at:
        return 0.0
    try:
        hour, minute = (int(x) for x in start_at.split(":", 1))
    except (TypeError, ValueError):
        return 0.0
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return max(0.0, (target - now).total_seconds())


def _run_sequence(robot_id: str, safety_inputs: dict[str, Any], start_at: str) -> None:
    """저장된 실행 순서를 한 단계씩 돌린다. 각 단계는 평소 실행과 같은 관문을 지난다."""
    flags = _flags(robot_id)
    store = _store(robot_id)
    instance = registry.get(robot_id)
    try:
        wait = _seconds_until(start_at)
        if wait > 0:
            store.update_runtime(run_state="예약", multi_run={"state": "scheduled",
                                                             "start_at": start_at})
            while wait > 0 and not flags["cancel"]:
                time.sleep(min(2.0, wait))
                wait = _seconds_until(start_at)
        if flags["cancel"]:
            store.update_runtime(run_state="취소", multi_run={"state": "취소"})
            return

        steps = (store.sequence().get("steps") or [])
        store.update_runtime(run_state="실행", multi_run={"state": "running"})
        _log(f"{instance.display_name}: 순서 실행 시작 ({len(steps)}단계)", "s-log-ok")

        for index, step in enumerate(steps, start=1):
            if flags["cancel"]:
                store.update_runtime(run_state="취소", multi_run={"state": "취소"})
                _log(f"{instance.display_name}: 순서 실행 취소 ({index - 1}/{len(steps)})",
                     "s-log-err")
                return
            while flags["paused"] and not flags["cancel"]:
                time.sleep(0.5)
            pose_id = str(step.get("pose_id") or "")
            answer = _execute_pose(instance, {"skill_id": pose_id,
                                              "safety_inputs": safety_inputs,
                                              "issue_token": True,
                                              "speed": step.get("speed") or "slow"},
                                   in_sequence=True)
            if "BLOCKED" in str(answer.get("verdict") or "") or answer.get("ok") is False:
                store.update_runtime(run_state="실패", multi_run={"state": "실패"},
                                     last_error=str(answer.get("verdict") or ""))
                _log(f"{instance.display_name}: {index}단계에서 멈춤 — "
                     f"{answer.get('verdict')}", "s-log-err")
                return
            delay = float(step.get("delay_sec") or 0)
            if delay > 0:
                time.sleep(min(delay, 30.0))

        store.update_runtime(run_state="완료", multi_run={"state": "완료"})
        _log(f"{instance.display_name}: 순서 실행 완료", "s-log-ok")
    except Exception as exc:                     # 스레드가 조용히 죽지 않게 한다
        store.update_runtime(run_state="실패", multi_run={"state": "실패"},
                             last_error=str(exc))
        _log(f"{robot_id}: 순서 실행 중 오류 — {exc}", "s-log-err")
    finally:
        with _RUN_LOCK:
            _RUN_FLAGS.pop(robot_id, None)


@app.post("/api/hangeul/multi-execute")
def multi_execute(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """화면이 체크한 로봇들의 저장된 순서를 실행한다. 예약 시각도 여기서 받는다."""
    entries = payload.get("robots") or [{"robot_id": rid} for rid in
                                        (payload.get("robot_ids") or [])]
    if not entries:
        return {"success": False, "runs": [], "blocked": [],
                "error": "실행할 로봇이 지정되지 않았습니다"}
    safety_inputs = payload.get("safety_inputs") or {}
    away = get_away_mode()
    if away["away_mode"]:
        return {"success": False, "runs": [], "blocked": [],
                "error": "부재 모드라서 실행하지 않습니다"}

    checked = []
    for entry in entries:
        robot_id = str(entry.get("robot_id") or "")
        instance = _instance(robot_id)
        states, _ = _capability_states(instance)
        steps = [{"kind": "pose", "label": s.get("pose_id"), "targets": ["stored"]}
                 for s in (_store(robot_id).sequence().get("steps") or [])]
        gate = task_mod.check_runnable(steps, instance, states) if steps else {
            "runnable": False, "blockers": ["실행 순서가 비어 있습니다"]}
        checked.append({"robot_id": robot_id, "display_name": instance.display_name,
                        "start_at": str(entry.get("start_at") or ""), **gate})

    not_ready = [c for c in checked if not c["runnable"]]
    if not_ready:
        reason = f"{not_ready[0]['display_name']}: {not_ready[0]['blockers'][0]}"
        _log(f"다중 실행 시작 안 함 — {reason}", "s-log-err")
        return {"success": False, "runs": [], "blocked": not_ready, "error": reason}

    runs = []
    for item in checked:
        robot_id = item["robot_id"]
        _flags(robot_id).update({"cancel": False, "paused": False})
        thread = threading.Thread(target=_run_sequence, daemon=True,
                                  args=(robot_id, safety_inputs, item["start_at"]))
        thread.start()
        runs.append({"robot_id": robot_id, "display_name": item["display_name"],
                     "start_at": item["start_at"],
                     "scheduled": bool(item["start_at"])})
    _log(f"다중 실행 접수: {len(runs)}대", "s-log-ok")
    return {"success": True, "runs": runs, "blocked": []}


ACTIVE_MULTI_STATES = ("running", "scheduled", "paused")


@app.post("/api/hangeul/multi-cancel")
def multi_cancel(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """진행·예약을 멈춘다. 무엇을 멈췄는지 화면이 셀 수 있게 목록으로 답한다."""
    cancelled = []
    for instance in registry.all():
        store = _store(instance.instance_id)
        state = (store.runtime().get("multi_run") or {}).get("state") or "idle"
        if state not in ACTIVE_MULTI_STATES:
            continue
        store.update_runtime(run_state="대기", multi_run={"state": "취소"})
        cancelled.append(instance.instance_id)
    _log(f"다중 실행 취소: {len(cancelled)}건",
         "s-log-info" if cancelled else "s-log-err")
    return {"success": True, "cancelled": cancelled}


@app.post("/api/hangeul/multi-reset")
def multi_reset(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """끝난 표시(완료/실패/취소)를 지운다. 진행·예약 중인 것은 그대로 둔다.

    **지난 결과 줄도 함께 지운다.** 상태만 '대기'로 돌리고 '마지막: 오류 /
    BLOCKED_...'를 남겨 두면, 초기화를 눌러도 화면에 옛 실패가 계속 붙어 있다 —
    사람은 방금 초기화한 로봇이 아직 실패 상태인 줄 안다.
    """
    cleared, kept_active, status_reset = [], [], []
    for instance in registry.all():
        store = _store(instance.instance_id)
        runtime_state = store.runtime()
        multi = (runtime_state.get("multi_run") or {}).get("state") or "idle"
        # 실행 중인 로봇은 건드리지 않는다 (dexter_hangeul web.py:2714와 같다).
        # 멈추려면 취소나 정지를 쓴다 — 초기화는 표시를 되돌리는 것이다.
        if multi in ACTIVE_MULTI_STATES or (runtime_state.get("run_state") or "") == "실행":
            kept_active.append(instance.instance_id)
            continue
        if multi != "idle":
            cleared.append(instance.instance_id)
        if (runtime_state.get("run_state") or "대기") != "대기":
            status_reset.append(instance.instance_id)
        elif runtime_state.get("last_result") or runtime_state.get("last_error"):
            status_reset.append(instance.instance_id)
        store.update_runtime(run_state="대기", multi_run={"state": "idle"},
                             last_result="", last_error="",
                             current_step_index=None)
        _log(f"{instance.display_name}: 상태 표시 초기화 (대기)", "s-log-info")
    _log(f"다중 실행 초기화: 표시 {len(cleared)}건, 상태 {len(status_reset)}건"
         + (f", 진행 중 {len(kept_active)}건 유지" if kept_active else ""),
         "s-log-info")
    return {"success": True, "cleared": cleared,
            "kept_active": kept_active, "status_reset": status_reset}


@app.post("/api/hangeul/multi-pause-hold")
def multi_pause(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    for instance in registry.all():
        _store(instance.instance_id).update_runtime(multi_run={"state": "paused"})
        runtime.forward(instance, "/api/pause-hold", {})
    _log("다중 실행 일시정지", "s-log-err")
    return {"success": True, "paused": True, "error": ""}


@app.post("/api/hangeul/multi-resume")
def multi_resume(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    if _console().get("away_mode"):
        return {"success": False, "error": "부재 모드에서는 재개하지 않습니다"}
    for instance in registry.all():
        _store(instance.instance_id).update_runtime(multi_run={"state": "running"})
    _log("다중 실행 재개", "s-log-ok")
    return {"success": True, "resumed": True, "error": ""}


# ── 관측 부품이 있어야 되는 것들 (C12) ──────────────────────────
@app.get("/api/server-camera-frame")
@app.post("/api/vision-training-capture")
@app.get("/api/vision-detect")
def vision_endpoints(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    instance = _selected()
    refusal = _require_module(instance, "eye", "눈(카메라)")
    if refusal:
        return refusal
    return runtime.forward(instance, "/api/server-camera-frame", None, method="GET")


def _tracking_unavailable() -> dict:
    return {"success": False, "ok": True, "available": False,
            "running": False, "process_running": False, "tracking": False,
            "follow": "unavailable", "event": None, "last": None,
            "detected_target_count": 0, "reason_code": "not_implemented",
            "error": "공개판에서는 물체·색상 추적을 제공하지 않습니다",
            "actual_hardware_called": False}


@app.get("/api/color-tracking-status")
@app.get("/api/target-tracking-status")
def target_tracking_status() -> dict:
    return _tracking_unavailable()


@app.post("/api/color-tracking/start")
@app.post("/api/color-tracking/stop")
@app.post("/api/target-tracking/start")
@app.post("/api/target-tracking/stop")
@app.post("/api/target-tracking/select")
@app.post("/api/target-tracking/clear")
@app.post("/api/target-tracking/follow")
def target_tracking_start(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    return _tracking_unavailable()


@app.get("/api/camera-stream")
def camera_stream():
    """런타임의 추적 화면을 브라우저로 그대로 흘린다.

    이 한 자리만 JSON이 아니다. 프레임을 통째로 담아 왕복하면 화면이 늦고,
    브라우저의 <img> 하나가 이걸 그냥 받는다.
    """
    from fastapi.responses import StreamingResponse

    instance = _selected()
    if _require_module(instance, "eye", "눈(카메라)"):
        raise HTTPException(status_code=404, detail="이 로봇에는 눈(카메라) 부품이 없습니다")
    url = instance.runtime_url.rstrip("/") + "/api/camera-stream"

    def relay():
        import urllib.request

        try:
            with urllib.request.urlopen(url, timeout=5.0) as upstream:
                while True:
                    chunk = upstream.read(8192)
                    if not chunk:
                        break
                    yield chunk
        except Exception:                       # noqa: BLE001 — 끊기면 화면이 다시 붙는다
            return

    return StreamingResponse(relay(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/voice-command")
@app.post("/api/voice-control")
@app.get("/api/server-voice-listen")
def voice_endpoints(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    instance = _selected()
    refusal = _require_module(instance, "ear", "귀(마이크)")
    if refusal:
        return refusal
    return {"ok": True, "observe_only": True}


# ── 도우미(화면 계약 이름 유지) ─────────────────────────────────
@app.get("/api/sllm/settings")
def advisor_settings() -> dict:
    store = _tasks()
    settings = _console().get("sllm") or {}
    return {
        "ok": True,
        "settings": {
            "enabled": bool(settings.get("enabled", True)),
            "search_sequences": bool(settings.get("search_sequences", True)),
            "min_score": float(settings.get("min_score", advisor.MIN_SCORE)),
            "max_candidates": int(settings.get("max_candidates", advisor.MAX_CANDIDATES)),
            "runtime": "deterministic",
        },
        # 화면의 뱃지·안내문이 읽는 이름들
        "retriever": "정확일치 → 별칭 → 낱말겹침",
        "sllm_runtime": "없음 (대기)",
        "runtime_note": f"저장된 할 일 {len(store.meanings)}개에서만 찾습니다. "
                        f"제안만 하고 실행하지 않습니다.",
        "execution_policy": {"propose_only": True, "raw_joint_generation": "FORBIDDEN"},
    }


@app.post("/api/sllm/settings")
def save_advisor_settings(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """도우미 설정 저장. 실행 권한은 어떤 설정으로도 켜지지 않는다."""
    state = _console()
    current = dict(state.get("sllm") or {})
    for key in ("enabled", "search_sequences"):
        if key in payload:
            current[key] = bool(payload[key])
    for key, cast in (("min_score", float), ("max_candidates", int)):
        if payload.get(key) is not None:
            try:
                current[key] = cast(payload[key])
            except (TypeError, ValueError):
                return {"ok": False, "success": False, "error": f"{key} 값이 올바르지 않습니다"}
    _update_console(lambda s: s.__setitem__("sllm", current))
    _log("도우미 설정 저장", "s-log-ok")
    return {"ok": True, "success": True, "settings": current}


@app.post("/api/sllm/suggest")
def advisor_suggest_compat(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    return advisor_suggest(payload)


@app.post("/api/sllm/approve")
def advisor_approve(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """제안을 고른 것일 뿐 실행이 아니다."""
    return {"ok": True, "approved": True, "actual_hardware_called": False, "error": "",
            "note": "실행은 기존 실행 절차를 그대로 거칩니다"}


@app.post("/api/recover-robot-usb")
def recover_usb(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    instance = _selected()
    resource = instance.runtime_url or instance.instance_id
    leases.release(resource, CONSOLE_HOLDER)
    result = runtime.forward(instance, "/api/recover-robot-usb", payload)
    _log(f"{instance.display_name}: 연결 복구 시도 (임대 해제 후)", "s-log-info")
    return result


@app.post("/api/server-restart")
def server_restart(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """콘솔과 로봇 런타임을 실제로 다시 시작한다.

    전에는 "콘솔은 스스로 다시 시작하지 않습니다"만 돌려줬다. 그런데 **화면은
    실제로 재시작되는 줄 알고** 만들어져 있었다(simple.js의 확인 문구가
    "서버 프로세스가 재시작되며"라고 말한다). 화면과 서버가 서로 다른 말을 하니
    누르는 사람에게는 그냥 "요청이 거부되었습니다"만 뜬다.

    **런타임까지 다시 시작하는 이유**가 있다. 코드를 고쳐 놓고 콘솔만 새로
    띄우면 런타임은 옛 코드로 계속 돈다 — 화면에는 단추가 보이는데 런타임에는
    그 기능이 아예 없는 상태가 되고, 눌러도 아무 일도 안 일어난다(2026-08-21에
    목표물 추적이 정확히 그랬다).

    팔에는 아무 명령도 보내지 않는다. 포트를 닫는 것뿐이고, 서보는 자기 토크
    상태를 그대로 들고 있다. 다만 컨트롤러가 시리얼 열림에 리셋되는 팔
    (MyCobot 계열의 M5)은 다시 열릴 때 리셋될 수 있으므로 응답에 적어 보낸다.
    """
    import subprocess
    import sys

    if not RESTART_SCRIPT.exists():
        return {"ok": False, "success": False, "manual": True,
                "error": f"실행 스크립트를 찾지 못했습니다: {RESTART_SCRIPT}",
                "message": "터미널에서 ./run.sh 를 실행하세요"}

    with_runtimes = bool(payload.get("restart_runtimes", True))
    # 죽일 대상을 정규식으로 적는다. `[.]`은 점 하나를 뜻하면서, **이 명령줄
    # 자신은 걸리지 않게** 한다 — 그냥 'hangeul_console.app'이라고 쓰면 이 조각을
    # 실행하는 껍데기가 자기 자신을 죽인다.
    patterns = ["hangeul_console[.]app"]
    if with_runtimes:
        patterns.insert(0, "hangeul_runtime[.]server")
    alive = "|".join(patterns)

    # 지금 프로세스가 죽은 **뒤에** 새로 띄워야 한다. 떨어져 나간 자식에게 시킨다 —
    # 부모(콘솔)를 죽이는 일이므로 부모가 직접 할 수 없다.
    steps = ["sleep 1"]
    steps += [f"pkill -f '{p}' || true" for p in patterns]
    steps += [
        # **정말 죽을 때까지 기다린다.** uvicorn은 TERM을 받고도 몇 초를 더 답한다.
        # 그 사이에 run.sh가 포트를 두드리면 "이미 떠 있음"으로 보고 건너뛴다 —
        # 그러면 콘솔만 새 코드로 돌아오고 런타임은 아예 사라진다(실측).
        f"for _ in $(seq 1 40); do pgrep -f '{alive}' >/dev/null 2>&1 || break; sleep 0.25; done",
        *[f"pkill -9 -f '{p}' || true" for p in patterns],
        "sleep 1",
        f"cd {shlex.quote(str(PROJECT_ROOT))}",
        f"exec {shlex.quote(str(RESTART_SCRIPT))} >> data/console.log 2>&1",
    ]
    try:
        subprocess.Popen(["bash", "-c", "; ".join(steps)],
                         start_new_session=True,
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError as exc:
        return {"ok": False, "success": False, "manual": True,
                "error": f"재시작을 시작하지 못했습니다: {exc}",
                "message": "터미널에서 ./run.sh 를 실행하세요"}

    _log("서버 재시작 요청 — 콘솔"
         + ("과 로봇 런타임을" if with_runtimes else "만") + " 다시 시작합니다", "s-log-err")
    return {"ok": True, "success": True, "manual": False,
            "restart_runtimes": with_runtimes,
            "message": "다시 시작합니다. 5~10초 뒤 브라우저를 새로고침하세요",
            # 어느 팔이 시리얼 열림에 스스로 초기화되는지는 **이 저장소가 실측으로
            # 아는 바가 없다.** 그러니 특정 팔을 지목하지 않는다 — 사람이 팔을
            # 낮은 자세에 두게 하는 것으로 충분하고, 지목하려면 부품 기술서가
            # 그 성질을 밝히고 나서야 한다.
            "note": ("로봇 런타임도 함께 다시 시작합니다. 팔에는 아무 명령도 보내지 "
                     "않지만, 시리얼이 다시 열릴 때 컨트롤러가 스스로 초기화되는 팔이 "
                     "있습니다. 팔을 낮은 자세에 두고 누르세요" if with_runtimes else
                     "로봇 런타임은 그대로 둡니다 — 런타임 코드를 고쳤다면 그것도 "
                     "다시 시작해야 합니다"),
            "python": sys.executable}


# 화면 파일은 브라우저에 저장해 두지 않는다.
# 고친 내용이 반영 안 되는 이유가 "브라우저가 옛 파일을 들고 있어서"인 일이
# 실제로 있었다. 이 콘솔은 한 사람이 쓰는 것이라 매번 받아도 부담이 없다.
NO_CACHE = {"Cache-Control": "no-store, must-revalidate", "Pragma": "no-cache"}


class FreshFiles(StaticFiles):
    def is_not_modified(self, response_headers, request_headers) -> bool:
        return False                     # 항상 새로 보낸다

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers.update(NO_CACHE)
        return response


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", headers=NO_CACHE)


if WEB_DIR.is_dir():
    app.mount("/", FreshFiles(directory=WEB_DIR, html=True), name="web")
