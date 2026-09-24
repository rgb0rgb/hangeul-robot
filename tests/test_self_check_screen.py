"""상태점검 — 로봇 목록에서 고르고, 거기서 누른다 (2026-09-24).

한글 로봇은 **기종이 섞인다**(OMX · MyCobot · 그 밖). 로봇이 수십 대가 되면
"고르는 자리"와 "누르는 자리"가 갈라져 있으면 안 된다. 로봇 목록에는 이미
체크박스가 있고 실행 시작 · 예약 취소 · 초기화가 같은 줄에 있다.
상태점검도 그 줄에 둔다.

순서는 이렇다.

    로봇 목록에서 체크 → [🔧 상태점검] → 안전 주의 → 실행 → 결과 → 닫기

앞서 실사용에서 겪은 것들이 여기 시험으로 남아 있다.

    · 창을 겹쳐 띄워 안전 문구가 뒤에 가려 보이지 않았다
    · 결과를 이미 닫힌 창에 그려서 다시 열어야 보였다
    · 시작 단추가 두 군데라 어느 것을 눌러야 할지 몰랐다
"""
from __future__ import annotations

from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "console" / "web"
JS = (WEB / "simple.js").read_text(encoding="utf-8")
GRID = (WEB / "hangeul-grid.js").read_text(encoding="utf-8")
HTML = (WEB / "index.html").read_text(encoding="utf-8")


def _body(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    return source[start:source.index("\n  }", start) if source is GRID
                  else source.index("\n}", start)]


# ── 어디에 있는가 ───────────────────────────────────────────────
def test_the_button_sits_with_the_other_robot_list_buttons():
    """실행 시작 · 예약 취소 · 초기화 옆이다. 고른 자리에서 누른다."""
    toolbar = HTML[HTML.index('id="hangeul-multi-execute"'):]
    toolbar = toolbar[:toolbar.index("</div>")]
    assert 'id="hangeul-multi-check"' in toolbar, "로봇 목록 단추 줄에 없습니다"


def test_it_is_no_longer_buried_in_settings():
    """고르는 자리와 누르는 자리가 갈라지면 로봇이 늘수록 헤맨다."""
    assert 'id="btn-self-check"' not in HTML, "환경설정에 아직 남아 있습니다"


def test_it_uses_the_list_checkboxes():
    """목록에 이미 있는 체크박스를 쓴다. 고르는 자리를 또 만들지 않는다."""
    body = _body(GRID, "runMultiSelfCheck")
    assert "checkedRobotIds()" in body, "목록의 체크박스를 쓰지 않습니다"
    assert "check-pick" not in HTML, "점검 창에 또 고르는 자리가 있습니다"


def test_it_says_so_when_nothing_is_checked():
    assert "checkNone" in _body(GRID, "runMultiSelfCheck")


# ── 순서 — 창을 겹치지 않는다 ───────────────────────────────────
def test_the_safety_notice_comes_before_the_robot_moves():
    body = _body(JS, "startSelfCheckFor")
    assert "showModal(" in body, "안전 확인을 띄우지 않습니다"
    assert "s-check-modal" not in body, \
        "안전 문구보다 먼저 결과 창을 띄웁니다 — 뒤에 가려 안 보입니다"


def test_it_uses_the_existing_safety_notice():
    """점검용 확인을 따로 만들지 않는다. 두 가지가 되면 하나는 느슨해진다."""
    assert "window.confirm" not in _body(JS, "startSelfCheckFor")
    assert "styledConfirm" not in _body(GRID, "runMultiSelfCheck")
    assert 'id="s-modal"' in HTML, "기존 안전 확인 창이 없어졌습니다"


def test_the_result_window_opens_when_the_robot_starts_moving():
    """움직이는 동안 아무것도 안 보이면 사람은 멈춘 줄 안다."""
    body = _body(JS, "runSelfCheck")
    assert "s-check-modal" in body and "flex" in body
    assert body.index("s-check-modal") < body.index("fetch("), \
        "요청을 보낸 뒤에 창을 띄웁니다 — 그 사이 화면이 비어 있습니다"


def test_the_result_lands_where_the_person_is_looking():
    """결과를 닫힌 창에 그리면 다시 열어야 보인다 — 실제로 그랬다."""
    body = _body(JS, "runSelfCheck")
    assert "renderSelfCheck" in body
    assert "closeSelfCheckModal" not in body, "결과를 그리기 전에 창을 닫습니다"


def test_there_is_only_one_start_button():
    """두 군데 있으면 어느 것을 눌러야 할지 모른다."""
    assert "btn-check-run" not in HTML
    assert "btn-check-start" not in HTML
    assert 'id="btn-check-close"' in HTML


# ── 여러 대 ─────────────────────────────────────────────────────
def test_the_robots_are_checked_one_at_a_time():
    """여러 대가 동시에 움직이면 사람이 어느 쪽을 봐야 할지 모른다."""
    assert "chain = chain.then" in _body(JS, "runSelfCheck")


def test_the_same_arm_is_not_checked_twice():
    """로봇 두 대가 같은 런타임을 보면 **같은 팔**이다.

    둘 다 체크하면 그 팔만 두 배로 닳고, 사람은 같은 결과를 두 번 본다.
    실제로 등록된 4대가 런타임 2개를 나눠 쓰고 있었다(2026-09-24 전수조사).
    """
    body = _body(GRID, "runMultiSelfCheck")
    assert "runtime_url" in body, "같은 런타임을 보는 로봇을 가려내지 않습니다"


def test_the_console_tells_the_screen_which_runtime_a_robot_uses():
    """화면이 모르면 가려낼 수가 없다."""
    app = (Path(__file__).resolve().parents[1] / "console" / "src" /
           "hangeul_console" / "app.py").read_text(encoding="utf-8")
    row = app[app.index("def _robot_row"):]
    row = row[:row.index("\n@app.")]
    assert '"runtime_url"' in row


def test_each_robot_gets_its_own_heading():
    """기종이 섞이면 관절 이름만 보고는 어느 팔인지 알 수 없다."""
    assert "item.robotId" in _body(JS, "renderSelfCheck")


def test_the_odometer_is_kept_per_robot():
    """남의 이력을 섞으면 정비 주기가 틀어진다."""
    assert "robot_id=" in _body(JS, "loadSelfCheckUsage")


# ── 기본 자세 안내 ──────────────────────────────────────────────
def test_it_tells_the_person_to_start_from_the_home_pose():
    """**알리기만 한다.** 안전한 자세는 로봇마다 다르고 코드가 정할 수 없다."""
    assert 'id="m-item-home"' in HTML
    assert "selfCheckHome" in JS, "안내가 사전을 안 거칩니다"
    assert "m-item-home" in _body(JS, "startSelfCheckFor")


def test_the_notice_does_not_linger_on_other_runs():
    """이 줄은 상태점검 것이다. 다른 실행의 확인 창에 남으면 거짓말이 된다."""
    assert 'style="display:none;"' in HTML.split('id="m-item-home"')[1][:60]
    assert "hideHomePoseNotice" in _body(JS, "hideModal")


def test_the_button_label_goes_through_the_dictionary():
    """이 화면의 낱말은 전부 사전을 거쳐야 영어로 바뀐다."""
    assert "setText('hangeul-multi-check'" in GRID
    assert "checkBtn: '🔧 Status check'" in GRID
