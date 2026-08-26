"""부품 교체 실증 — C8(손 교체) · C9(축 변경).

**콘솔 코드를 한 줄도 고치지 않고** 기술서만 바꿔서 무엇이 따라 바뀌는지 보인다.
로봇을 움직이지 않는다. 읽기와 계산만 한다.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "console" / "src"))

from hangeul_console import capability, task as task_mod          # noqa: E402
from hangeul_console.registry import Registry                     # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "install" / "modules"


# 실증에 쓸 로봇은 여기서 만들어 쓴다. 남의 컴퓨터에는 등록된 로봇이 없다 —
# 대표 로봇 이름을 박아 두면 받은 사람은 이 실증을 한 번도 못 본다.
DEMO_ROBOT = {
    "instance_id": "swap_demo_arm",
    "display_name": "실증용 팔",
    "runtime_url": "http://127.0.0.1:8601",
    "modules": ["core_a", "arm_omx", "hand_omx"],
}


def show(title, config, store, tasks):
    caps = store.visible(config, {"_default": "AVAILABLE"})
    line = {c.capability_id: c.verification for c in caps}
    resolved = tasks.resolve("pick_move", config) if "pick_move" in tasks.meanings else None
    print(f"\n[{title}]")
    print("  관절 :", [j["label"] for j in config.joint_view()])
    print("  지문 :", config.fingerprint()[:22], "| 손지문", config.part_fingerprint("hand"))
    print("  검증 : 팔=", line.get("motion.move_pose"), " 손=", line.get("hand.open"))
    if resolved:
        print("  작업 : 가르침=", resolved["taught"], resolved.get("reason", ""))


def main() -> int:
    backup = {}
    for name in ("hand_omx.json", "arm_omx.json"):
        backup[name] = (MODULES / name).read_text(encoding="utf-8")
    tmp = tempfile.TemporaryDirectory(prefix="hangeul_swap_demo_")
    robots = Path(tmp.name)
    (robots / "swap_demo_arm.json").write_text(
        json.dumps(DEMO_ROBOT, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        reg = Registry(MODULES, robots)
        config = reg.get("swap_demo_arm")
        store = capability.CapabilityStore()
        tasks = task_mod.TaskStore(json.loads((ROOT / "data" / "tasks.json").read_text(encoding="utf-8"))
                                   if (ROOT / "data" / "tasks.json").exists() else None)
        store.mark_verified("motion.move_pose", config, evidence_ref="run:demo", operator="demo")
        store.mark_verified("hand.open", config, evidence_ref="run:demo", operator="demo")
        show("처음 — 팔·손 모두 해봤음", config, store, tasks)

        # C8: 손만 교체 (MyCobot 손을 OMX 팔에)
        swapped = json.loads(backup["hand_omx.json"])
        swapped["display_name"] = "바꿔 낀 손"
        swapped["command"] = {"joint": 15, "unit": "percent", "open": 100, "close": 0}
        swapped["limits"] = {"grip_g": 150, "mass_g": 90}
        (MODULES / "hand_omx.json").write_text(json.dumps(swapped, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
        reg.reload()
        show("C8 손 교체 — 손 검증만 내려간다", reg.get("swap_demo_arm"), store, tasks)

        # C9: 축 줄이기 (4축 → 2축)
        (MODULES / "hand_omx.json").write_text(backup["hand_omx.json"], encoding="utf-8")
        arm = json.loads(backup["arm_omx.json"])
        for joint in arm["joints"][2:]:
            joint["disabled"] = True
            joint["reason"] = "실증용 축 축소"
        (MODULES / "arm_omx.json").write_text(json.dumps(arm, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
        reg.reload()
        show("C9 축 줄임 4→2 — 팔 검증만 내려간다", reg.get("swap_demo_arm"), store, tasks)
        return 0
    finally:
        for name, text in backup.items():
            (MODULES / name).write_text(text, encoding="utf-8")
        tmp.cleanup()
        print("\n(기술서 원상복구 완료)")


if __name__ == "__main__":
    raise SystemExit(main())
