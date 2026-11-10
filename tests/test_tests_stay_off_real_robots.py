"""시험이 떠 있는 실제 로봇에 정지·해제를 보내지 않는다 (2026-11-10).

시험이 실제 로봇1(127.0.0.1:8601)에 긴급 정지를 걸어 화면이 돌던 FR5 반복을 멈춘 일이 있었다.
"""
from __future__ import annotations

import http.server
import threading
import urllib.error
import urllib.request

import pytest


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8601/api/estop",
    "http://localhost:8606/api/estop-reset",
    "http://127.0.0.1:8099/api/status",
])
def test_real_service_ports_are_refused(url):
    with pytest.raises(urllib.error.URLError, match="실제 서비스"):
        urllib.request.urlopen(urllib.request.Request(url, data=b"{}", method="POST"), timeout=1)


def test_estop_from_a_test_console_reaches_no_real_robot(client, monkeypatch, tmp_path):
    from conftest import install_fixture_robots
    install_fixture_robots(monkeypatch, tmp_path)   # 주소가 실제 로봇1(8601)과 같은 시험 로봇
    sent: list[str] = []
    real = urllib.request.urlopen   # 이미 막힌 urlopen — 무엇을 보내려 했는지만 적는다

    def record(url, *a, **kw):
        sent.append(url.full_url if isinstance(url, urllib.request.Request) else str(url))
        return real(url, *a, **kw)

    monkeypatch.setattr(urllib.request, "urlopen", record)
    assert client.post("/api/estop", json={}).json()["success"] is True
    client.post("/api/estop-reset", json={"operator": "운영자"})
    assert sent, "정지가 런타임 쪽으로 나가지 않았다 — 이 시험이 아무것도 확인하지 못한다"
    # 보내려던 것은 전부 막혀 런타임이 꺼진 것처럼 처리됐다(위 시험이 막힘을 확인한다).


def test_a_server_the_test_starts_itself_still_answers():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
            assert r.read() == b"ok"
    finally:
        httpd.shutdown()
