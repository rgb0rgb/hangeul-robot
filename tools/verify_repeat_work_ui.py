"""Browser + real console API verification, with no network or hardware access.

Run: python3 tools/verify_repeat_work_ui.py
Requires pytest, Playwright and its Chromium browser.
"""
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "console/src")]

from conftest import install_fixture_robots, isolate_console_state
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from pytest import MonkeyPatch
from hangeul_console import app as console
from hangeul_console.repeat_work import RepeatWork


def main():
    with tempfile.TemporaryDirectory() as temp, MonkeyPatch.context() as patch:
        install_fixture_robots(patch, Path(temp))
        isolate_console_state(patch, Path(temp))
        patch.setattr(console, "repeat_work", RepeatWork())
        patch.setattr(console, "get_away_mode", lambda: {"away_mode": False})
        patch.setattr(console.runtime, "health", lambda i: {
            "connected": True, "reason": "", "capability_health": {"_default": "AVAILABLE"}, "parts": {}})
        patch.setattr(console.runtime, "forward", lambda *a, **kw: {
            "joint_tick_limits": {"12": [1000, 2200], "15": [500, 1963]}})
        patch.setattr(console.runtime, "read_pose", lambda i: {"success": True, "present": {"12": 1500, "15": 800}})
        patch.setattr(console.runtime, "stop", lambda i: {"stopped": True})
        calls = []
        def move(instance, skill, **kw):
            calls.append(kw["targets"])
            time.sleep(0.005)
            return {"ok": True, "detail": {"success": True}}
        patch.setattr(console.runtime, "run", move)
        client = TestClient(console.app)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page()
            # Only the repeat panel runs here. Existing conversion/modal helpers
            # are supplied explicitly; real repeat HTTP handlers run via ASGI.
            html = (ROOT / "console/web/index.html").read_text()
            start = html.index('      <div class="s-micro-move-panel" id="repeat-work-panel">')
            end = html.index('\n      <div style="margin-top: 15px;', start)
            page.set_content(html[start:end])
            page.add_script_tag(content="""
              var lang='ko', BACKEND='http://repeat.test';
              var state={robotJoints:{instance_id:'young_omx',all_joints:[
                {joint_id:12,label_kr:'관절 1',label_en:'Joint 1'},
                {joint_id:15,label_kr:'손',label_en:'Gripper'}]},
                jointTickLimits:{12:[1000,2200],15:[500,1963]},excludedJointIds:[]};
              var isMyCobotUi=()=>false, isGripperJoint=j=>j=='15';
              var formatUiRange=(j,b)=>b.join(' ~ '), rawToUiValue=(j,v)=>v;
              var uiToRawValue=(j,v)=>Math.round(Number(v));
              var showModal=fn=>fn();
              var getSafetyInputs=()=>({operator_present:true,workspace_clear:true,
                manual_stop_available:true,estop_ready:true});
            """)
            def route(req):
                request = req.request
                response = client.request(request.method, request.url.replace("http://repeat.test", ""),
                                          content=request.post_data,
                                          headers={"Content-Type": "application/json"})
                req.fulfill(status=response.status_code, content_type="application/json",
                            body=response.content, headers={"Access-Control-Allow-Origin": "*"})
            page.route("http://repeat.test/**", route)
            page.add_script_tag(path=str(ROOT / "console/web/repeat-work.js"))
            page.locator("#repeat-a").fill("1300")
            page.locator("#repeat-b").fill("2000")
            page.locator("#repeat-count").fill("50")
            page.locator("#repeat-start").click()
            expect(page.locator("#repeat-status")).to_contain_text("50/50", timeout=15000)
            assert calls == [{"12": 1300}, {"12": 2000}] * 50
            page.locator("#repeat-joint").select_option("15")
            page.locator("#repeat-capture-a").click()
            expect(page.locator("#repeat-a")).to_have_value("800")
            page.locator("#repeat-b").fill("1500")
            page.locator("#repeat-wait-a").fill("60")
            page.locator("#repeat-start").click()
            expect(page.locator("#repeat-pause")).to_be_enabled()
            page.locator("#repeat-pause").click()
            expect(page.locator("#repeat-status")).to_contain_text("일시정지")
            page.locator("#repeat-resume").click()
            page.locator("#repeat-cancel").click()
            expect(page.locator("#repeat-status")).to_contain_text("취소됨")
            assert calls[100:] == [{"15": 800}]
            page.evaluate("lang='en'; refreshRepeatWork()")
            expect(page.locator("#repeat-title")).to_have_text("Repeat work mode")
            expect(page.locator("#repeat-status")).to_contain_text("Canceled")
            page.close()
            # Full production HTML/JavaScript: exercise the actual save modal,
            # pose API, catalog, edit and page reload, not replacement helpers.
            client.post("/api/robots/young_omx/select")
            page = browser.new_page()
            def full_route(req):
                request = req.request
                if not request.url.startswith("http://repeat.test/"):
                    req.abort()
                    return
                response = client.request(request.method, request.url.replace("http://repeat.test", ""),
                                          content=request.post_data,
                                          headers={"Content-Type": "application/json"})
                req.fulfill(status=response.status_code,
                            content_type=response.headers.get("content-type", "application/json"),
                            body=response.content)
            page.route("**/*", full_route)
            page.goto("http://repeat.test/", wait_until="domcontentloaded")
            expect(page.locator("#repeat-start")).to_be_enabled()
            page.locator("#repeat-joint").select_option("12")
            page.locator("#repeat-a").fill("1300")
            page.locator("#repeat-b").fill("2000")
            page.locator("#repeat-count").fill("3")
            page.locator("#repeat-save").click()
            expect(page.locator("#save-motion-repeat")).to_be_checked()
            expect(page.locator("#save-repeat-count")).to_have_value("3")
            page.locator("#save-name-kr").fill("반복 저장 검증")
            page.locator("#btn-save-pose-submit").click()
            expect(page.locator("#s-save-modal")).to_be_hidden()
            page.wait_for_function("state.catalog.some(c => c.display_name_kr === '반복 저장 검증')")
            card = page.evaluate("state.catalog.find(c => c.display_name_kr === '반복 저장 검증')")
            assert card["repeat_work"]["count"] == 3
            before = len(calls)
            page.evaluate("openEditModal(state.catalog.find(c => c.display_name_kr === '반복 저장 검증'))")
            expect(page.locator("#save-repeat-count")).to_have_value("3")
            page.locator("#save-repeat-count").fill("50")
            page.locator("#btn-save-pose-submit").click()
            expect(page.locator("#s-save-modal")).to_be_hidden()
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function("state.catalog.some(c => c.display_name_kr === '반복 저장 검증')")
            card = page.evaluate("state.catalog.find(c => c.display_name_kr === '반복 저장 검증')")
            assert card["repeat_work"]["count"] == 50
            assert len(calls) == before
            # 아래쪽 "💾 자세 저장"도 같은 저장이다 — 사람은 이 단추를 누른다.
            # 반복 칸이 비어 있으면 평소 자세 저장이고, 채워 있으면 반복째 저장한다.
            page.locator("#repeat-a").fill("")
            page.locator("#btn-save-pose-modal").click()
            expect(page.locator("#save-motion-repeat")).not_to_be_checked()
            expect(page.locator("#save-motion-repeat")).to_be_disabled()
            page.evaluate("closeSaveModal ? closeSaveModal() : document.getElementById('s-save-modal').style.display='none'")
            page.locator("#repeat-joint").select_option("12")
            page.locator("#repeat-a").fill("1100")
            page.locator("#repeat-b").fill("2100")
            page.locator("#repeat-count").fill("7")
            page.locator("#repeat-wait-a").fill("1.5")
            page.locator("#repeat-wait-b").fill("2")
            page.locator("#btn-save-pose-modal").click()
            expect(page.locator("#save-motion-repeat")).to_be_checked()
            expect(page.locator("#save-repeat-count")).to_have_value("7")
            page.locator("#save-name-kr").fill("아래 단추 반복 저장")
            page.locator("#btn-save-pose-submit").click()
            expect(page.locator("#s-save-modal")).to_be_hidden()
            page.wait_for_function("state.catalog.some(c => c.display_name_kr === '아래 단추 반복 저장')")
            main_card = page.evaluate("state.catalog.find(c => c.display_name_kr === '아래 단추 반복 저장')")
            assert main_card["motion_type"] == "repeat", main_card
            assert main_card["repeat_work"] == {"joint_id": "12", "a": 1100, "b": 2100, "count": 7,
                                                "wait_a": 1.5, "wait_b": 2.0}, main_card["repeat_work"]
            assert len(calls) == before
            calls.clear()
            answer = client.post("/api/execute-actual", json={"skill_id": card["skill_id"],
                "safety_inputs": {k: True for k in ("operator_present", "workspace_clear", "manual_stop_available", "estop_ready")}}).json()
            assert answer["success"], answer
            assert calls == [{"12": 1300}, {"12": 2000}] * 50
            browser.close()
        print("PASS: 50 cycles/100 moves, gripper capture, pause/resume/cancel, English labels; hardware calls: 0")
        print("PASS: full-page save, edit count, reload, saved card executes 50 cycles; main save button keeps A/B, count and waits; saving causes no motion")


if __name__ == "__main__":
    main()
