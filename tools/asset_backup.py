"""운영자 자산 백업·복원 — 1단계 "안전한 출발".

지키려는 것: 사람이 직접 가르친 자세, 실행 순서, 안전 범위, 손 교정값.
코드는 다시 만들 수 있지만 이 값들은 다시 만들 수 없다.

규칙
1. 원본을 절대 건드리지 않는다. 읽기만 한다.
2. 파일마다 SHA-256을 남긴다.
3. 복원은 빈 폴더에 풀고 **해시가 전부 같을 때만** 성공으로 본다.
4. 하나라도 다르면 실패로 끝낸다. 부분 복원은 하지 않는다.

사용법
    python3 tools/asset_backup.py export <원본디렉터리> <백업파일.json>
    python3 tools/asset_backup.py restore <백업파일.json> <복원디렉터리>
    python3 tools/asset_backup.py verify <백업파일.json> <복원디렉터리>
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BUNDLE_FORMAT = "hangeul_robot.asset_bundle.v1"

# 백업 대상 — 사람이 만든 것만. 로그·상태 같은 재생성 가능한 것은 제외한다.
ASSET_FILES = ("poses.json", "sequence.json", "sequence_library.json", "settings.json")


def file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def export(source: Path) -> dict[str, Any]:
    """인스턴스 디렉터리들을 하나의 묶음으로 읽어낸다. 원본은 수정하지 않는다."""
    if not source.is_dir():
        raise SystemExit(f"원본 디렉터리가 없습니다: {source}")
    instances: dict[str, Any] = {}
    for inst_dir in sorted(p for p in source.iterdir() if p.is_dir()):
        if inst_dir.name.startswith((".", "_")):
            continue
        files: dict[str, Any] = {}
        for name in ASSET_FILES:
            target = inst_dir / name
            if not target.exists():
                continue
            files[name] = {
                "sha256": file_hash(target),
                "bytes": target.stat().st_size,
                "content": json.loads(target.read_text(encoding="utf-8")),
            }
        if files:
            instances[inst_dir.name] = files
    return {
        "format": BUNDLE_FORMAT,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "instance_count": len(instances),
        "file_count": sum(len(f) for f in instances.values()),
        "instances": instances,
    }


def restore(bundle: dict[str, Any], target: Path) -> dict[str, Any]:
    """묶음을 대상 디렉터리에 푼다. 기존 파일이 있으면 덮어쓰지 않고 멈춘다."""
    if bundle.get("format") != BUNDLE_FORMAT:
        raise SystemExit(f"알 수 없는 백업 형식: {bundle.get('format')}")
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for inst_id, files in bundle["instances"].items():
        inst_dir = target / inst_id
        inst_dir.mkdir(parents=True, exist_ok=True)
        for name, meta in files.items():
            out = inst_dir / name
            if out.exists():
                raise SystemExit(f"이미 파일이 있습니다. 빈 디렉터리에 복원하세요: {out}")
            out.write_text(
                json.dumps(meta["content"], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            written.append(str(out.relative_to(target)))
    return {"restored": len(written), "files": written}


def verify(bundle: dict[str, Any], target: Path) -> dict[str, Any]:
    """복원 결과가 원본과 **의미상 같은지** 확인한다.

    바이트 동일은 요구하지 않는다 — JSON 들여쓰기·줄바꿈이 달라질 수 있기 때문이다.
    대신 내용을 정규화해 비교하고, 하나라도 다르면 실패다.
    """
    mismatches, checked = [], 0
    for inst_id, files in bundle["instances"].items():
        for name, meta in files.items():
            path = target / inst_id / name
            checked += 1
            if not path.exists():
                mismatches.append(f"{inst_id}/{name}: 파일 없음")
                continue
            try:
                actual = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                mismatches.append(f"{inst_id}/{name}: 읽을 수 없음 ({exc})")
                continue
            if _canonical(actual) != _canonical(meta["content"]):
                mismatches.append(f"{inst_id}/{name}: 내용 불일치")
    return {"ok": not mismatches, "checked": checked, "mismatches": mismatches}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 2
    action, first, second = argv[1], Path(argv[2]), Path(argv[3])
    if action == "export":
        bundle = export(first)
        second.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        print(f"백업 완료: 로봇 {bundle['instance_count']}대 / 파일 {bundle['file_count']}개 → {second}")
        return 0
    bundle = json.loads(first.read_text(encoding="utf-8"))
    if action == "restore":
        result = restore(bundle, second)
        print(f"복원 완료: {result['restored']}개 파일 → {second}")
        check = verify(bundle, second)
        print("검증:", "통과" if check["ok"] else f"실패 {check['mismatches']}")
        return 0 if check["ok"] else 1
    if action == "verify":
        check = verify(bundle, second)
        print(f"검사 {check['checked']}개 →", "전부 일치" if check["ok"] else check["mismatches"])
        return 0 if check["ok"] else 1
    print(f"알 수 없는 명령: {action}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
