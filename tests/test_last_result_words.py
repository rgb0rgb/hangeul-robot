"""로봇 목록의 '마지막:' 칸 — 판정 코드를 사람에게 그대로 보이지 않는다 (2026-11-08).

화면이 `마지막: ACTUAL_MOTION_EXECUTED_ONCE`를 그렸다. 판정 코드는 내부 ID이고,
사용자 모드에서는 원시 용어를 쓰지 않는다(terms.py 규칙 2). 낱말은 terms.py에만 둔다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from hangeul_console import terms

ROOT = Path(__file__).resolve().parents[1]
CODE = re.compile(r"^[A-Z][A-Z0-9_]+$")


def _verdicts_in_source() -> set[str]:
    """런타임·콘솔이 판정으로 내보내는 코드를 소스에서 모은다 — 새 코드가 생기면 여기 걸린다."""
    found = set()
    patterns = [
        r"[\"']verdict[\"']\s*:\s*[\"']([A-Z][A-Z0-9_]{3,})[\"']",
        r"verdict\s*=\s*[\"']([A-Z][A-Z0-9_]{3,})[\"']",
    ]
    for base in ("runtime/src", "console/src"):
        for path in (ROOT / base).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for pattern in patterns:
                found.update(re.findall(pattern, text, flags=re.S))
            found.update(_run_verdicts(text))
    return found


def _run_verdicts(text: str) -> set[str]:
    """런타임의 `_run(…, "판정")` — 마지막 인자가 성공 판정이다. 괄호가 겹쳐도 끝까지 읽는다."""
    out = set()
    for match in re.finditer(r"\b_run\(", text):
        depth, i = 1, match.end()
        while i < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            i += 1
        last = re.search(r"[\"']([A-Z][A-Z0-9_]{3,})[\"']\s*\)$", text[match.start():i])
        if last:
            out.add(last.group(1))
    return out


def test_the_source_scan_finds_the_common_verdicts():
    found = _verdicts_in_source()
    assert {"ACTUAL_MOTION_EXECUTED_ONCE", "DISCONNECTED", "MOVED"} <= found


@pytest.mark.parametrize("lang", ["ko", "en"])
def test_no_verdict_reaches_the_screen_as_a_code(lang):
    for verdict in sorted(_verdicts_in_source()) + ["SOMETHING_NEW", "BLOCKED_SOMETHING_NEW"]:
        word = terms.result_text(verdict, lang)
        assert word, verdict
        assert not CODE.match(word), f"{verdict} → {word}"
        assert verdict not in word


def test_every_verdict_from_the_source_has_its_own_word():
    """'막힘'·'알 수 없는 결과'로 뭉개지지 않게 — 나오는 코드는 전부 제 낱말이 있다."""
    missing = sorted(v for v in _verdicts_in_source() if f"result.{v}" not in terms.TERMS)
    assert missing == []


def test_the_executed_once_verdict_reads_as_completed():
    assert terms.result_text("ACTUAL_MOTION_EXECUTED_ONCE", "ko") == "실행 완료"
    assert terms.result_text("ACTUAL_MOTION_EXECUTED_ONCE", "en") == "Completed"
    assert terms.result_text("", "ko") == ""


@pytest.fixture
def one_robot(tmp_path, monkeypatch):
    """로봇 한 대만 있는 콘솔. 사람의 install/robots·data를 쓰지 않고, 런타임 주소는
    아무도 듣지 않는 곳이라 실물에 닿지 않는다."""
    import json
    from fastapi.testclient import TestClient
    from hangeul_console import app as app_mod
    from hangeul_console.device_lease import LeaseBook
    from hangeul_console.registry import Registry

    robots = tmp_path / "robots"
    robots.mkdir()
    (robots / "r1.json").write_text(json.dumps({
        "instance_id": "r1", "display_name": "시험 로봇", "runtime_url": "http://127.0.0.1:9",
        "modules": ["core_a", "arm_omx", "hand_omx"]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(app_mod, "ROBOT_CONFIG_DIR", robots)
    monkeypatch.setattr(app_mod, "registry", Registry(app_mod.MODULE_DIR, robots))
    monkeypatch.setattr(app_mod, "INSTANCE_DIR", tmp_path / "instances")
    monkeypatch.setattr(app_mod, "CONSOLE_STATE", tmp_path / "console.json")
    monkeypatch.setattr(app_mod, "TASK_PATH", tmp_path / "tasks.json")
    monkeypatch.setattr(app_mod, "leases", LeaseBook(tmp_path / "leases"))
    return app_mod, TestClient(app_mod.app)


def test_the_robot_list_sends_words_with_the_code(one_robot):
    app_mod, client = one_robot
    app_mod._store("r1").update_runtime(last_result="ACTUAL_MOTION_EXECUTED_ONCE")
    row = next(r for r in client.get("/api/robots").json()["robots"] if r["robot_id"] == "r1")
    assert row["last_result"] == "ACTUAL_MOTION_EXECUTED_ONCE"          # 코드는 그대로 남는다
    assert row["last_result_i18n"] == {"ko": "실행 완료", "en": "Completed"}


def test_an_empty_result_sends_no_words(one_robot):
    _, client = one_robot
    row = next(r for r in client.get("/api/robots").json()["robots"] if r["robot_id"] == "r1")
    assert row["last_result"] == "" and row["last_result_i18n"] == {"ko": "", "en": ""}
