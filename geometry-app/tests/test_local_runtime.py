import concurrent.futures
from http.client import IncompleteRead
import importlib
import io
import json
import os
from pathlib import Path

import pytest

from scripts.local_runtime import StateWriter, ServiceSupervisor


class Process:
    def __init__(self):
        self.code = None

    def poll(self):
        return self.code


class Clock:
    now = 0

    def __call__(self):
        return self.now


def manager(tmp_path, clock, spawn=None):
    calls = []

    def popen(command, **kwargs):
        calls.append(command)
        return spawn(command, **kwargs) if spawn else Process()

    return ServiceSupervisor(tmp_path, tmp_path, {}, popen=popen, clock=clock, notify=lambda _: None), calls


def test_state_replace_retries_a_transient_windows_lock(tmp_path):
    attempts, sleeps = [], []

    def replace(source, destination):
        attempts.append(source)
        if len(attempts) < 3:
            raise PermissionError('Windows sharing violation')
        os.replace(source, destination)

    writer = StateWriter(tmp_path / 'state.json', replace=replace, sleep=sleeps.append)
    assert writer.write({'status': 'ready'})
    assert json.loads(writer.path.read_text()) == {'status': 'ready'}
    assert sleeps == [.025, .05]
    assert not list(tmp_path.glob('*.tmp'))


def test_state_persistent_lock_is_bounded_nonfatal_and_recovers(tmp_path):
    warnings, attempts = [], []

    def replace(source, destination):
        attempts.append(source)
        raise PermissionError('locked')

    writer = StateWriter(tmp_path / 'state.json', warn=warnings.append, replace=replace, sleep=lambda _: None)
    assert writer.write({'status': 'ready'}) is False
    assert len(attempts) == 6
    assert writer.write({'status': 'ready'}) is False
    assert len(warnings) == 1
    writer.replace = os.replace
    assert writer.write({'status': 'ready'})
    assert not list(tmp_path.glob('*.tmp'))


def test_concurrent_state_publications_are_complete_json_and_have_unique_temp_files(tmp_path):
    paths = []

    def replace(source, destination):
        paths.append(source)
        assert json.loads(Path(source).read_text())['status'] == 'ready'
        os.replace(source, destination)

    writer = StateWriter(tmp_path / 'state.json', replace=replace)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(lambda i: writer.write({'status': 'ready', 'generation': i}), range(40)))
    assert len(set(paths)) == 40
    assert json.loads(writer.path.read_text())['generation'] in range(40)
    assert not list(tmp_path.glob('*.tmp'))


def test_only_exited_owned_service_restarts_and_survivors_keep_their_handles(tmp_path):
    clock = Clock()
    supervisor, calls = manager(tmp_path, clock)
    api = supervisor.add('api', ['api'])
    frontend = supervisor.add('frontend', ['frontend'])
    gateway = supervisor.add('gateway', ['gateway'])
    originals = frontend.process, gateway.process
    api.process.code = 1
    supervisor.tick()
    assert api.state == 'recovering'
    assert len(calls) == 3
    clock.now = 1
    supervisor.tick()
    assert calls == [['api'], ['frontend'], ['gateway'], ['api']]
    assert (frontend.process, gateway.process) == originals
    assert api.generation == 2
    for service in supervisor.services.values():
        service.log.close()


def test_failed_spawn_or_port_conflict_never_kills_other_processes_and_backs_off(tmp_path):
    clock = Clock()

    def failing(*args, **kwargs):
        raise PermissionError('occupied or temporarily unavailable')

    supervisor, calls = manager(tmp_path, clock, failing)
    service = supervisor.add('api', ['api'])
    delays = []
    for _ in range(10):
        delays.append(service.retry_at - clock.now)
        count = len(calls)
        supervisor.tick()
        assert len(calls) == count
        clock.now = service.retry_at
        supervisor.tick()
    assert delays == [1, 2, 4, 8, 16, 30, 30, 30, 30, 30]
    assert service.log is None


def test_stable_service_resets_restart_backoff(tmp_path):
    clock = Clock()
    supervisor, _ = manager(tmp_path, clock)
    service = supervisor.add('api', ['api'])
    service.failures = 8
    clock.now = 35
    supervisor.tick()
    assert service.failures == 0
    service.process.code = 1
    supervisor.tick()
    assert service.retry_at == 36


def test_previous_exit_log_is_kept_once_and_bounded(tmp_path):
    (tmp_path / 'api.log').write_bytes(b'x' * 200000)
    supervisor, _ = manager(tmp_path, Clock())
    service = supervisor.add('api', ['api'])
    assert (tmp_path / 'api.previous.log').stat().st_size == 131072
    service.log.close()










@pytest.mark.skipif(os.name != 'nt', reason='Windows Job API wiring')
def test_owned_service_gate_does_not_start_descendants_before_job_assignment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    share = importlib.import_module('local')
    events = []

    class Pipe(io.BytesIO):
        def write(self, data):
            events.append('release gate')
            return super().write(data)

    class Gate(Process):
        _handle = 321
        def __init__(self):
            super().__init__(); self.stdin = Pipe()

    gate = Gate()
    monkeypatch.setattr(share, 'CreateJob', lambda *_: 123)
    monkeypatch.setattr(share, 'SetJob', lambda *_: True)
    monkeypatch.setattr(share, 'AssignJob', lambda *_: events.append('assign job') or True)
    monkeypatch.setattr(share, 'Close', lambda handle: events.append(('close job', handle)))
    monkeypatch.setattr(share.subprocess, 'Popen', lambda *_, **__: events.append('spawn gated wrapper') or gate)
    owned = share.start_owned_service(['unit-test-command'])
    assert events == ['spawn gated wrapper', 'assign job', 'release gate']
    assert owned.poll() is None
    gate.code = 1
    assert owned.poll() == 1
    assert events[-1] == ('close job', 123)
    owned.poll()
    assert events.count(('close job', 123)) == 1


@pytest.mark.skipif(os.name != 'nt', reason='Windows Job API wiring')
def test_failed_job_assignment_never_releases_gate_and_closes_owned_handle(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    share = importlib.import_module('local')
    events = []

    class Pipe(io.BytesIO):
        def write(self, data):
            pytest.fail('A failed assignment must never release the gate')

    class Gate(Process):
        _handle = 321
        stdin = Pipe()
        def kill(self):
            events.append('kill owned gate')
        def wait(self, timeout):
            raise share.subprocess.TimeoutExpired('owned-gate', timeout)

    monkeypatch.setattr(share, 'CreateJob', lambda *_: 123)
    monkeypatch.setattr(share, 'SetJob', lambda *_: True)
    monkeypatch.setattr(share, 'AssignJob', lambda *_: False)
    monkeypatch.setattr(share, 'Close', lambda handle: events.append(('close job', handle)))
    monkeypatch.setattr(share.subprocess, 'Popen', lambda *_, **__: Gate())
    with pytest.raises(OSError):
        share.start_owned_service(['unit-test-command'])
    assert events == ['kill owned gate', ('close job', 123)]
