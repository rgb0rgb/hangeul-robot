"""USB가 다시 붙어 번호가 바뀌어도 런타임이 스스로 이어진다.

실제로 겪은 일(2026-09-24, OMX U2D2). USB-IP 연결이 끊겼다 다시 붙었는데,
런타임이 옛 /dev/ttyUSB0 을 쥐고 있어서 새 장치는 ttyUSB1 이 됐다.
런타임은 없는 ttyUSB0 만 다시 열려다 실패했고, 화면의 서버 재시작은
run.sh 가 "ttyUSB0 없음 — 건너뜀"으로 런타임을 아예 띄우지 않았다.
"""
from __future__ import annotations

import os

from hangeul_runtime import server


def test_a_numbered_port_is_replaced_by_its_serial_number_path(tmp_path):
    by_id = tmp_path / "by-id"
    by_id.mkdir()
    (by_id / "usb-FTDI_Serial_Converter_ABC123-if00-port0").symlink_to("/dev/tty")
    assert server._stable_device("/dev/tty", str(by_id)) == \
        str(by_id / "usb-FTDI_Serial_Converter_ABC123-if00-port0")


def test_nothing_is_guessed_when_no_identity_path_matches(tmp_path):
    by_id = tmp_path / "by-id"
    by_id.mkdir()
    (by_id / "usb-other-if00-port0").symlink_to("/dev/null")
    assert server._stable_device("/dev/tty", str(by_id)) == "/dev/tty"
    # 없는 장치는 없는 그대로 둔다 — 다른 장치를 짐작해 열지 않는다
    assert server._stable_device("/dev/ttyUSB97", str(by_id)) == "/dev/ttyUSB97"
    assert server._stable_device("COM3", str(by_id)) == "COM3"
    assert server._stable_device("/dev/tty", str(tmp_path / "missing")) == "/dev/tty"


class Reopenable:
    def __init__(self):
        self.opened = 0

    def __enter__(self):
        self.opened += 1
        return self

    def __exit__(self, *exc):
        return False


def test_reattached_device_under_the_same_identity_path_is_reopened(tmp_path, monkeypatch):
    # by-id 링크는 다시 붙을 때 새 ttyUSBn 을 가리킨다. 이름은 같고 가리키는 것이 바뀐다.
    first, second = tmp_path / "ttyUSB0", tmp_path / "ttyUSB1"
    first.write_text("")
    second.write_text("")
    link = tmp_path / "usb-FTDI_ABC123-if00-port0"
    link.symlink_to(first)
    adapter = Reopenable()
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    monkeypatch.setitem(server.CONFIG, "adapter", adapter)
    monkeypatch.setitem(server.CONFIG, "device", str(link))
    monkeypatch.setitem(server.CONFIG, "device_stamp", server._device_stamp())

    server._ensure_link()
    assert adapter.opened == 0                 # 그대로면 다시 열지 않는다

    first.unlink()                             # 끊김
    link.unlink()
    link.symlink_to(second)                    # 다른 번호로 다시 붙음
    server._ensure_link()
    assert adapter.opened == 1
    assert server.CONFIG["device_stamp"] == server._device_stamp()
    assert os.path.realpath(server.CONFIG["device"]) == str(second)


def test_missing_device_says_so_instead_of_a_python_error(tmp_path, monkeypatch):
    import pytest
    from hangeul_runtime.hardware_errors import HardwareConnectionLostError
    device = tmp_path / "ttyUSB0"
    device.write_text("")
    monkeypatch.setitem(server.CONFIG, "adapter", Reopenable())
    monkeypatch.setitem(server.CONFIG, "device", str(device))
    monkeypatch.setitem(server.CONFIG, "device_stamp", server._device_stamp())
    device.unlink()
    with pytest.raises(HardwareConnectionLostError) as caught:
        server._ensure_link()
    assert "USB 장치가 보이지 않습니다" in str(caught.value)
    assert "NoneType" not in str(caught.value)


def test_same_name_coming_back_is_reopened(monkeypatch):
    # 윈도우 COM3 은 빠졌다 붙어도 이름도 신원값도 같다. '없어졌던 적'으로 알아본다.
    import pytest
    from hangeul_runtime.hardware_errors import HardwareConnectionLostError
    seen = iter([("com", "COM3"), None, ("com", "COM3")])
    adapter = Reopenable()
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    monkeypatch.setattr(server, "_device_stamp", lambda: next(seen))
    monkeypatch.setitem(server.CONFIG, "adapter", adapter)
    monkeypatch.setitem(server.CONFIG, "device", "COM3")
    monkeypatch.setitem(server.CONFIG, "device_stamp", ("com", "COM3"))
    monkeypatch.setitem(server.CONFIG, "device_lost", False)
    server._ensure_link()
    assert adapter.opened == 0
    with pytest.raises(HardwareConnectionLostError):
        server._ensure_link()
    server._ensure_link()
    assert adapter.opened == 1
    assert server.CONFIG["device_lost"] is False


def test_a_device_that_was_never_a_file_is_left_alone(monkeypatch):
    # ROS 2 는 장치 자리에 주소를 쓴다. 파일이 없다고 '빠졌다'고 하면 안 된다.
    adapter = Reopenable()
    monkeypatch.setitem(server.CONFIG, "adapter", adapter)
    monkeypatch.setitem(server.CONFIG, "device", "/joint_trajectory_controller")
    monkeypatch.setitem(server.CONFIG, "device_stamp", None)
    monkeypatch.setitem(server.CONFIG, "device_lost", False)
    server._ensure_link()
    assert adapter.opened == 0
