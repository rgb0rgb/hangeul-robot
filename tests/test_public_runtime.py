"""Public demo behavior, exercised without opening physical hardware."""
import pytest
from fastapi.testclient import TestClient
from hangeul_runtime import server


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setattr(server, 'CONFIG', dict(server.CONFIG))
    monkeypatch.setattr(server, 'state', server.safety.SafetyState())
    monkeypatch.setattr(server, '_read_cache', {'at': 0.0, 'value': {}})
    monkeypatch.setattr(server, '_TRACKING', {'session': None})
    server.build('arm_sim', '', simulate=True)
    with TestClient(server.app) as client:
        yield client


def test_simulation_can_read_jog_move_and_grip(runtime):
    health = runtime.get('/api/estop-status').json()
    assert health['simulated'] is True
    present = runtime.get('/api/read-pose').json()['present']
    assert set(present) == {'1', '2', '3', '4', '5'}
    jog = runtime.post('/api/jog', json={'joint_id': 1, 'delta_ticks': 50}).json()
    assert jog['success'] and jog['present']['1'] == present['1'] + 50
    assert jog['actual_hardware_called'] is False
    assert jog['simulated'] is True
    for joint, target in [(1, 2100), (5, 1500)]:
        answer = runtime.post('/api/move-to', json={'joint_id': joint, 'target_ticks': target}).json()
        assert answer['success'], answer
        assert answer['present'][str(joint)] == target
        assert answer['actual_hardware_called'] is False


def test_simulation_obeys_estop_and_range(runtime):
    runtime.post('/api/estop', json={})
    blocked = runtime.post('/api/jog', json={'joint_id': 1, 'delta_ticks': 50}).json()
    assert blocked['success'] is False and blocked['reason_code'] == 'estop_latched'
    server.state.clear_estop('test')
    blocked = runtime.post('/api/move-to', json={'joint_id': 1, 'target_ticks': 999999}).json()
    assert blocked['success'] is False
    assert blocked['reason_code'] == 'out_of_range'


def test_simulated_pose_requires_operator_checks(runtime):
    denied = runtime.post('/api/execute-actual', json={'targets': {'1': 2100}}).json()
    assert denied['success'] is False
    answer = runtime.post('/api/execute-actual', json={
        'targets': {'1': 2100}, 'safety_inputs': {
            'operator_present': True, 'workspace_clear': True,
            'manual_stop_available': True, 'estop_ready': True}}).json()
    assert answer['success'] is True
    assert answer['actual_hardware_called'] is False


def test_simulate_physical_descriptor_never_loads_physical_adapter(runtime, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError('Physical adapter must not be loaded')
    monkeypatch.setattr(server, '_adapter_class', forbidden)
    server.build('arm_omx', '/dev/DO_NOT_OPEN', simulate=True)
    assert server.CONFIG['adapter'].simulated is True
    assert '11' in server.read_pose()['present']


def test_demo_without_flag_still_uses_simulated_adapter(runtime):
    server.build('arm_sim', '')
    assert server.CONFIG['adapter'].simulated is True


@pytest.mark.parametrize('path', ['/api/target-tracking-status', '/api/color-tracking-status'])
def test_tracking_status_is_explicitly_unavailable(runtime, path):
    reply = runtime.get(path)
    assert reply.status_code == 200
    assert reply.json()['available'] is False
    assert reply.json()['reason_code'] == 'not_implemented'


@pytest.mark.parametrize('kind', ['target', 'color'])
def test_excluded_tracking_cannot_start(runtime, kind):
    reply = runtime.post(f'/api/{kind}-tracking/start', json={'follow': True})
    assert reply.status_code == 200
    assert reply.json()['success'] is False
    assert reply.json()['actual_hardware_called'] is False


def test_stop_selection_does_not_match_other_checkouts(tmp_path):
    from stop_project import is_project_server
    root = tmp_path / 'one'
    argv = ['python3', '-m', 'hangeul_runtime.server', '--simulate']
    assert is_project_server(root, argv, root)
    assert not is_project_server(tmp_path / 'two', argv, root)
    assert not is_project_server(root, ['python3', 'unrelated.py'], root)


def test_console_can_register_demo_and_forward_move(runtime, tmp_path, monkeypatch):
    from hangeul_console import app as console
    from hangeul_console.registry import Registry
    from hangeul_console.device_lease import LeaseBook
    monkeypatch.setattr(console, 'ROBOT_CONFIG_DIR', tmp_path / 'robots')
    monkeypatch.setattr(console, 'INSTANCE_DIR', tmp_path / 'instances')
    monkeypatch.setattr(console, 'CONSOLE_STATE', tmp_path / 'console.json')
    monkeypatch.setattr(console, 'TASK_PATH', tmp_path / 'tasks.json')
    monkeypatch.setattr(console, 'registry', Registry(console.MODULE_DIR, tmp_path / 'robots'))
    monkeypatch.setattr(console, 'leases', LeaseBook(tmp_path / 'leases'))

    def call(instance, path, payload=None, **kwargs):
        response = runtime.request(kwargs.get('method', 'GET'), path, json=payload)
        return {'ok': response.is_success, 'data': response.json()}
    monkeypatch.setattr(console.runtime, '_call', call)
    with TestClient(console.app) as client:
        assert client.get('/api/status').json()['robots'] == []
        for path in ['/api/target-tracking-status', '/api/color-tracking-status']:
            assert client.get(path).json()['reason_code'] == 'not_implemented'
        added = client.post('/api/robots/add', json={
            'modules': ['core_a', 'arm_sim', 'hand_sim']})
        assert added.status_code == 200, added.text
        assert client.get('/api/status').json()['selected_robot_id']
        pose = client.get('/api/read-pose').json()
        assert pose['success'] and '5' in pose['present']
        moved = client.post('/api/jog', json={'joint_id': 1, 'delta_ticks': 50}).json()
        assert moved['success'], moved
        assert moved['simulated'] and not moved['actual_hardware_called']


def test_stop_script_only_terminates_its_own_server(tmp_path):
    import shutil
    import subprocess
    import sys
    from pathlib import Path
    roots = [tmp_path / 'one', tmp_path / 'two']
    children = []
    for root in roots:
        (root / 'hangeul_runtime').mkdir(parents=True)
        (root / 'hangeul_runtime' / '__init__.py').write_text('')
        (root / 'hangeul_runtime' / 'server.py').write_text('import time\ntime.sleep(30)\n')
        children.append(subprocess.Popen([sys.executable, '-m', 'hangeul_runtime.server'], cwd=root))
    try:
        tools = roots[0] / 'tools'
        tools.mkdir()
        shutil.copy(Path(__file__).resolve().parents[1] / 'tools' / 'stop_project.py', tools)
        result = subprocess.run([sys.executable, str(tools / 'stop_project.py')], cwd=roots[0],
                                capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        children[0].wait(timeout=3)
        assert children[1].poll() is None
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=3)
