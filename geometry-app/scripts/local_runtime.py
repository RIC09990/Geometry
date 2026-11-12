"""Small, dependency-free lifecycle helpers for the Windows local launcher."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid


class StateWriter:
    def __init__(self, path, warn=print, replace=os.replace, sleep=time.sleep):
        self.path = Path(path)
        self.warn, self.replace, self.sleep = warn, replace, sleep
        self.lock = threading.Lock()
        self.warned = False

    def write(self, values):
        with self.lock:
            temporary = self.path.with_name(f'{self.path.stem}.{os.getpid()}.{uuid.uuid4().hex}.tmp')
            try:
                temporary.write_text(json.dumps(values, ensure_ascii=False), encoding='utf-8')
                for attempt in range(6):
                    try:
                        self.replace(temporary, self.path)
                        self.warned = False
                        return True
                    except PermissionError:
                        if attempt == 5:
                            raise
                        self.sleep(.025 * 2 ** attempt)
            except OSError:
                if not self.warned:
                    self.warn('Geometry 状态文件暂时被占用，网站继续运行；稍后自动重试。')
                    self.warned = True
                return False
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


@dataclass
class Service:
    name: str
    command: list
    process: object = None
    log: object = None
    state: str = 'starting'
    failures: int = 0
    retry_at: float = 0
    started_at: float = 0
    generation: int = 0


class ServiceSupervisor:
    """Restart exited owned Popen instances only. Never kill by PID or port."""
    def __init__(self, root, logs, env, *, popen=subprocess.Popen, clock=time.monotonic, notify=print, maximum_delay=30):
        self.root, self.logs, self.env = Path(root), Path(logs), env
        self.popen, self.clock, self.notify = popen, clock, notify
        self.maximum_delay = maximum_delay
        self.services = {}

    def add(self, name, command):
        service = Service(name, command)
        self.services[name] = service
        self.tick()
        return service

    def _retry(self, service, reason):
        if service.log:
            service.log.close()
            service.log = None
        service.process = None
        service.failures += 1
        delay = min(2 ** min(service.failures - 1, 9), self.maximum_delay)
        service.retry_at = self.clock() + delay
        service.state = 'recovering'
        self.notify(f'{service.name} {reason}；{delay} 秒后只重启该服务。')

    def tick(self):
        now = self.clock()
        for service in self.services.values():
            if service.process is not None:
                code = service.process.poll()
                if code is None:
                    if now - service.started_at >= 30:
                        service.failures = 0
                    continue
                self._retry(service, f'已退出（{code}）')
                continue
            if now < service.retry_at:
                continue
            try:
                log_path = self.logs / (service.name + '.log')
                # Keep one bounded previous log for diagnosing the last exit.
                try:
                    with log_path.open('rb') as previous:
                        previous.seek(0, 2)
                        previous.seek(max(0, previous.tell() - 131072))
                        log_path.with_suffix('.previous.log').write_bytes(previous.read())
                except OSError:
                    pass
                service.log = log_path.open('w', encoding='utf-8')
                service.process = self.popen(service.command, cwd=self.root, env=self.env,
                    stdin=subprocess.DEVNULL, stdout=service.log, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                service.started_at = now
                service.generation += 1
                service.state = 'running'
            except OSError as error:
                self._retry(service, f'暂时无法启动（{type(error).__name__}）')

    def status(self):
        return {name: {'state': s.state, 'generation': s.generation}
                for name, s in self.services.items()}
