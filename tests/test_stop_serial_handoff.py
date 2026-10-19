"""멈춤은 진행 중인 이동과 시리얼을 동시에 쓰지 않는다.

실제로 겪은 일(2026-10-19, OMX): 반복 동작 도중 일시정지를 누르면 같은 초에
'연결 끊김: 레지스터 읽기 재시도 후 실패: comm=-1000'이 걸렸다. -1000은
dynamixel_sdk의 COMM_PORT_BUSY다 — 멈춤(_stop_hardware)이 잠금 없이 자세를
읽고 다시 쓰는 동안, 이동은 SERIAL_LOCK을 쥔 채 같은 포트로 도착을 감시하고
있었다. 두 대화가 SDK의 '사용 중' 표시 위에서 부딪혔다.
"""
from __future__ import annotations

import threading
import time

import pytest

from hangeul_runtime import server
from hangeul_runtime.hardware import openmanipulator_x_arm_adapter as omx

COMM_PORT_BUSY = -1000


class FakePort:
    is_using = False


class FakePacket:
    """SDK처럼 동작한다: 포트가 사용 중이면 -1000, 아니면 잠깐 점유했다 놓는다."""

    def __init__(self):
        self.overlaps = 0
        self.position = {i: 1000 for i in omx.EXPECTED_IDS}

    def _talk(self, port, value):
        if port.is_using:
            self.overlaps += 1
            return value, COMM_PORT_BUSY, 0
        port.is_using = True
        time.sleep(0.003)
        port.is_using = False
        return value, 0, 0

    def read1ByteTxRx(self, port, dxl_id, addr):
        value = {omx.ADDR_MOVING: 1, omx.ADDR_HARDWARE_ERROR: 0}.get(addr, 30)
        return self._talk(port, value)

    def read2ByteTxRx(self, port, dxl_id, addr):
        return self._talk(port, 10)

    def read4ByteTxRx(self, port, dxl_id, addr):
        # 계속 조금씩 움직인다 — 도착도, 끼임 판정도 나지 않는다.
        self.position[dxl_id] += 10
        return self._talk(port, self.position[dxl_id])

    def write1ByteTxRx(self, port, dxl_id, addr, value):
        return self._talk(port, 0)[1:]

    def write4ByteTxRx(self, port, dxl_id, addr, value):
        return self._talk(port, 0)[1:]


class FakeSyncWrite:
    def __init__(self, port, packet, addr, length):
        self.port, self.packet = port, packet

    def addParam(self, dxl_id, data):
        return True

    def clearParam(self):
        pass

    def txPacket(self):
        return self.packet._talk(self.port, 0)[1]


@pytest.fixture
def arm(monkeypatch):
    monkeypatch.setattr(omx, "GroupSyncWrite", FakeSyncWrite)
    adapter = omx.OpenManipulatorXArmAdapter(device="fake")
    adapter.port, adapter.packet = FakePort(), FakePacket()
    server.build("arm_omx", "", simulate=True)
    server.CONFIG["adapter"] = adapter
    yield adapter
    server.CONFIG["adapter"] = None


def _start_move(adapter):
    out: dict = {}

    def run():
        try:
            with server.SERIAL_LOCK:          # _send()와 같은 방식으로 쥔다
                out["result"] = adapter.move_joints(
                    {"11": 3000, "12": 3000}, velocity=50, acceleration=20, label="반복")
        except Exception as exc:              # noqa: BLE001
            out["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    time.sleep(0.15)                          # 도착 감시 루프에 들어갈 때까지
    return thread, out


def test_stop_takes_the_serial_from_a_running_move_instead_of_talking_over_it(arm):
    thread, out = _start_move(arm)

    server._stop_hardware()
    thread.join(timeout=5)

    assert not thread.is_alive(), "진행 중인 이동이 멈춤 뒤에도 감시를 계속합니다"
    assert "error" not in out, f"멈춤이 이동을 연결 끊김으로 만들었습니다: {out.get('error')}"
    assert arm.packet.overlaps == 0, f"두 대화가 포트에서 {arm.packet.overlaps}번 부딪혔습니다"
    assert out["result"]["canceled"] is True, "끊긴 이동은 CANCELED로 올라가야 재개 때 다시 보냅니다"


def test_a_halt_does_not_cancel_the_freeze_that_follows_it(arm):
    """멈춤 뒤의 '그 자리에 세우기'도 move_joints다 — 자기 멈춤 요청에 걸려 끊기면 안 된다."""
    calls = []
    real = arm.move_joints

    def spy(targets, **kwargs):
        result = real(targets, **kwargs)
        calls.append(result)
        return result

    arm.move_joints = spy
    arm.packet.read1ByteTxRx = lambda port, i, addr: arm.packet._talk(port, 0)   # 곧바로 도착
    arm.packet.read4ByteTxRx = lambda port, i, addr: arm.packet._talk(port, 1000)
    server._stop_hardware()
    assert calls and calls[-1].get("canceled") is not True, calls
