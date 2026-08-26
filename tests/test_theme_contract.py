"""화면 배경(테마) — 새로 만든 화면도 대표가 고른 색을 따르는가.

실제로 겪은 일(2026-08-19). 로봇 추가 팝업을 만들면서 색을 어두운 값으로
그대로 박아 넣었다. Light·Orange·Aqua에서는 **테두리조차 보이지 않았다.**
게다가 있지도 않은 변수 이름(--theme-panel, --theme-input-bg)을 써서, 조용히
대체값(어두운 색)으로 떨어졌다 — 아무것도 터지지 않아 눈으로 볼 때까지 몰랐다.

여기서 지키는 것은 둘이다.
  1. 화면이 쓰는 테마 변수는 실제로 정의된 것이어야 한다.
  2. 고를 수 있는 모든 배경이 그 변수를 빠짐없이 정의해야 한다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "console" / "web"
BASE_CSS = (WEB / "simple.css").read_text(encoding="utf-8")
HTML = (WEB / "index.html").read_text(encoding="utf-8")


def _selectable_themes() -> list[str]:
    """환경 설정의 '화면 배경' 목록에서 직접 읽는다 — 사람이 관리하지 않는다."""
    block = re.search(r'<select id="ui-theme-select".*?</select>', HTML, re.S)
    assert block, "환경 설정에 화면 배경 목록이 없다"
    return ["theme-" + v for v in re.findall(r'<option value="([^"]+)"', block.group(0))]


def _defined_in(theme: str) -> set[str]:
    found = re.search(r"body\." + re.escape(theme) + r"\s*\{(.*?)\}", BASE_CSS, re.S)
    return set(re.findall(r"(--theme-[a-z0-9-]+)\s*:", found.group(1) if found else ""))


def _used_theme_vars() -> set[str]:
    css = "\n".join((WEB / name).read_text(encoding="utf-8")
                    for name in ("simple.css", "hangeul-grid.css"))
    return set(re.findall(r"var\(\s*(--theme-[a-z0-9-]+)", css))


def test_every_theme_variable_the_screen_uses_is_actually_defined():
    defined = set()
    for theme in _selectable_themes():
        defined |= _defined_in(theme)
    unknown = sorted(_used_theme_vars() - defined)
    assert not unknown, (
        "어느 배경에도 없는 변수 — 조용히 대체값(어두운 색)으로 떨어진다:\n  "
        + "\n  ".join(unknown))


@pytest.mark.parametrize("theme", _selectable_themes())
def test_every_selectable_background_defines_what_the_screen_uses(theme):
    missing = sorted(_used_theme_vars() - _defined_in(theme))
    assert not missing, f"{theme}에 없는 변수: {', '.join(missing)}"


def test_the_add_robot_popup_follows_the_theme():
    """새로 만든 화면이 색을 박아 넣으면 밝은 배경에서 읽히지 않는다."""
    grid_css = (WEB / "hangeul-grid.css").read_text(encoding="utf-8")
    block = grid_css[grid_css.index(".s-add-robot-modal {"):]
    for rule in (".s-add-robot-modal {", ".s-model-card {"):
        body = block[block.index(rule):].split("}", 1)[0]
        for prop in ("background", "border", "color"):
            line = [ln for ln in body.splitlines() if ln.strip().startswith(prop)]
            assert line, f"{rule}에 {prop}가 없다"
            assert "var(--theme-" in line[0], f"{rule}의 {prop}가 테마를 따르지 않는다: {line[0].strip()}"
