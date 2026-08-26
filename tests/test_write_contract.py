"""쓰기·삭제 쪽 화면 계약 — 화면이 보내는 자리와 읽는 이름이 콘솔과 맞는가.

`test_screen_contract.py`는 이미 있었지만 **읽기(GET)만** 봤다. 코드에 이렇게
적혀 있었다.

    if re.search(r"method:\\s*['\\"](POST|DELETE|PUT)", tail[:200]):
        continue        # ← 저장·삭제는 검사에서 뺀다

2026-08-18~19에 나온 것이 전부 그 빠진 절반이었다.

    이름이 POSE_1787108447로 저장   화면은 name_kr, 콘솔은 display_name_kr
    카드가 안 지워짐               화면은 주소줄, 콘솔은 본문
    유령 순서 카드 ok/robot_id     화면은 응답을 통째로 목록으로 쓰는데 감싸서 줌
    로봇 추가가 아무 일도 안 함     화면은 종류 한 줄, 콘솔은 부품 목록을 요구

전부 조용히 죽었다. 아무것도 터지지 않고 값만 사라졌다. 그래서 나머지 절반을
여기서 본다. **실행하지 않고 글자만 본다** — 저장·삭제·정지를 실제로 부르면
로봇이 움직이거나 자료가 지워지기 때문이다.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "console" / "web"
APP = ROOT / "console" / "src" / "hangeul_console" / "app.py"
SCRIPTS = ("simple.js", "hangeul-grid.js")

# 응답 본문이 아니라 자바스크립트 문법·유틸·화면이 스스로 붙이는 값
NOT_FIELDS = {
    "then", "catch", "json", "map", "forEach", "filter", "length", "status",
    "toFixed", "push", "indexOf", "split", "join", "slice", "trim", "value",
    "checked", "textContent", "style", "target", "message",
    "_status",        # 화면이 HTTP 상태를 스스로 붙여 쓰는 이름
    "detail",         # FastAPI가 오류 응답에 붙이는 이름
}

WINDOW = 1200         # 호출 뒤 이만큼만 본다


def _source() -> str:
    return "\n".join((WEB / name).read_text(encoding="utf-8") for name in SCRIPTS)


def _write_calls() -> dict[str, dict[str, set[str]]]:
    """화면의 저장·삭제 호출 → 주소줄로 보내는 이름, 응답에서 읽는 이름."""
    source = _source()
    found: dict[str, dict[str, set[str]]] = {}
    pattern = r"fetch\(\s*(?:BACKEND\s*\+\s*)?['\"](/api/[A-Za-z0-9_\-/]+)([^'\"]*)['\"]"
    for match in re.finditer(pattern, source):
        tail = source[match.end():match.end() + WINDOW]
        cut = tail.find("fetch(")             # 다음 호출부터는 남의 코드다
        tail = tail[:cut] if cut > 0 else tail
        # 창을 줄 끝에서 끊는다 — 잘린 이름(candidates → ca)을 진짜로 착각하지 않게
        last_line = tail.rfind("\n")
        if cut <= 0 and last_line > 0:
            tail = tail[:last_line]
        if not re.search(r"method:\s*['\"](POST|DELETE|PUT)", tail[:250]):
            continue
        entry = found.setdefault(match.group(1), {"query": set(), "fields": set()})
        entry["query"] |= set(re.findall(r"[?&]([A-Za-z_][A-Za-z0-9_]*)=", match.group(2)))
        entry["fields"] |= (set(re.findall(r"\b(?:d|data)\.([A-Za-z_][A-Za-z0-9_]*)", tail))
                            - NOT_FIELDS)
    return found


def _handlers() -> dict[str, dict]:
    """콘솔의 저장·삭제 처리기 → 받는 이름, 돌려줄 수 있는 이름."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        paths = [dec.args[0].value for dec in node.decorator_list
                 if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                 and dec.func.attr in ("post", "delete", "put")
                 and dec.args and isinstance(dec.args[0], ast.Constant)]
        if not paths:
            continue
        keys: set[str] = set()
        dynamic = False
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Return):
                continue
            if not isinstance(sub.value, ast.Dict):
                dynamic = True        # 다른 곳이 만든 응답을 넘긴다 — 여기서는 알 수 없다
                continue
            for key in sub.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
                else:
                    dynamic = True    # **다른것 으로 펼친다
        params = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
        for path in paths:
            cur = out.setdefault(path, {"keys": set(), "params": set(), "dynamic": False})
            cur["keys"] |= keys
            cur["params"] |= params
            cur["dynamic"] = cur["dynamic"] or dynamic
    return out


_CALLS = _write_calls()
_HANDLERS = _handlers()
_SHARED = sorted(path for path in _CALLS if path in _HANDLERS)


@pytest.mark.parametrize("path", _SHARED)
def test_console_receives_what_the_screen_sends_in_the_url(path):
    """화면이 주소줄로 보내는 이름을 콘솔이 받는가.

    안 받으면 콘솔은 빈 값으로 일한다 — 지울 것을 못 찾아 아무것도 안 지우고,
    화면에는 사유 없는 '삭제 실패:'만 남는다.
    """
    missing = sorted(name for name in _CALLS[path]["query"]
                     if name not in _HANDLERS[path]["params"])
    assert not missing, f"{path}: 화면이 주소줄로 보내는데 콘솔이 안 받는 이름 {missing}"


@pytest.mark.parametrize("path", _SHARED)
def test_screen_reads_only_fields_the_console_can_return(path):
    """화면이 응답에서 읽는 이름을 콘솔이 실제로 담는가."""
    if _HANDLERS[path]["dynamic"]:
        pytest.skip(f"{path}: 응답을 다른 곳에서 만든다 — 글자만으로는 알 수 없다")
    missing = sorted(name for name in _CALLS[path]["fields"]
                     if name not in _HANDLERS[path]["keys"])
    assert not missing, f"{path}: 화면이 읽지만 응답에 없는 이름 {missing}"


def test_the_write_half_is_actually_being_checked():
    """이 시험이 빈 목록을 돌며 통과하고 있지는 않은가."""
    assert len(_SHARED) >= 15, f"저장·삭제 경로를 {len(_SHARED)}개밖에 못 찾았다"
