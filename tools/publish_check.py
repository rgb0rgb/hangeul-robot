"""올리기 전에 확인한다 — 무엇이 올라가고, 남의 것이 섞이지 않았는가.

공개는 되돌릴 수 없다. 한 번 올라간 파일은 지워도 남는다. 그래서 push 전에
**올라갈 목록을 눈으로 본다.** 이 도구는 고치지 않는다. 보여주고 판정만 한다.

    python3 tools/publish_check.py

내보내는 값: 0 = 올려도 된다, 1 = 막을 것이 있다
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 남의 컴퓨터에서 뜻이 없거나, 올리면 안 되는 것들.
FORBIDDEN = [
    ("data/console_state.json", "이 컴퓨터의 화면 상태와 운전 기록"),
    ("data/leases/", "장치 임대 기록 — 이 컴퓨터에서만 뜻이 있다"),
    ("build/", "만들어 쓰는 묶음 — 저장소에 넣지 않는다"),
]

# 개인을 가리키는 흔적. 발견되면 막지 않고 눈으로 보라고 알린다.
SUSPECT = re.compile(r"tigersin|/mnt/c/Users/|\b192\.168\.\d+\.\d+\b|\b10\.\d+\.\d+\.\d+\b")


def git(*args: str) -> str:
    return subprocess.run(("git", *args), cwd=ROOT, capture_output=True,
                          text=True, check=False).stdout


def main() -> int:
    problems: list[str] = []
    notes: list[str] = []

    tracked = [line for line in git("ls-files").splitlines() if line]
    pending = [line for line in git("status", "--porcelain").splitlines() if line]

    print(f"올라갈 파일  {len(tracked)}개")
    print(f"아직 커밋 안 된 것  {len(pending)}건"
          + ("  ← 이대로 push하면 이건 안 올라갑니다" if pending else ""))

    # 1. 올리면 안 되는 것이 목록에 있는가
    for needle, why in FORBIDDEN:
        hit = [p for p in tracked if p == needle or p.startswith(needle)]
        if hit:
            problems.append(f"{needle} 가 올라갑니다 ({why}) — {len(hit)}개")

    # 2. 등록된 로봇이 새어 나가는가. 남의 화면에 내 로봇이 뜨면 안 된다.
    robots = [p for p in tracked
              if p.startswith("install/robots/") and p.endswith(".json")
              and not p.endswith(".example.json")]
    if robots:
        problems.append(f"등록된 로봇이 올라갑니다 — {', '.join(robots)}")

    on_disk = sorted(p.name for p in (ROOT / "install" / "robots").glob("*.json")
                     if not p.name.endswith(".example.json"))
    if on_disk:
        notes.append(f"이 컴퓨터에 등록된 로봇 {len(on_disk)}대는 그대로 있습니다 "
                     f"({', '.join(on_disk)}) — 올라가지만 않습니다")

    # 3. 받은 사람은 0대로 시작해야 한다
    if not (ROOT / "install" / "robots" / "arm.example.json").exists():
        problems.append("install/robots/arm.example.json 이 없습니다 — 받은 사람이 만들 본이 없습니다")

    # 4. 배포물의 최소 형식
    for name in ("LICENSE", "VERSION", "CHANGELOG.md", "README.md", "README.en.md"):
        if name not in tracked and not (ROOT / name).exists():
            problems.append(f"{name} 이 없습니다")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "?"

    # 5. 개인 흔적
    for rel in tracked:
        path = ROOT / rel
        if rel == "tools/publish_check.py":       # 찾는 글자가 여기 적혀 있다
            continue
        if not path.exists() or path.stat().st_size > 400_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for match in set(SUSPECT.findall(text)):
            notes.append(f"눈으로 확인: {rel} 에 '{match}'")

    print(f"판올림  {version}")
    print()

    if notes:
        print("알아둘 것")
        for note in sorted(set(notes)):
            print(f"  · {note}")
        print()

    if problems:
        print("막습니다 — 아래를 고치기 전에는 올리지 마십시오")
        for problem in problems:
            print(f"  ✗ {problem}")
        return 1

    print("올려도 됩니다. 개인 데이터는 목록에 없습니다.")
    if pending:
        print("다만 커밋 안 된 것이 남아 있습니다. 커밋해야 올라갑니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
