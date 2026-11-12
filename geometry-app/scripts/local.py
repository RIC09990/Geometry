"""Windows local website launcher. A non-inherited Job handle owns every service.

The gated worker starts no subprocess until assigned to the kill-on-close Job.
If the owner dies before assignment, pipe EOF makes the worker exit harmlessly.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from local_runtime import StateWriter, ServiceSupervisor

ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'.local'/'local'
PYTHON=ROOT/'.venv'/'Scripts'/'python.exe'
IDENT=hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:20]
NAME='Local\\GeometryLocal-'+IDENT
STATE=LOCAL/'state.json'
K=C.WinDLL('kernel32',use_last_error=True)

def bind(name,args,result):
    fn=getattr(K,name);fn.argtypes=args;fn.restype=result;return fn
CreateJob=bind('CreateJobObjectW',[C.c_void_p,W.LPCWSTR],W.HANDLE)
SetJob=bind('SetInformationJobObject',[W.HANDLE,C.c_int,C.c_void_p,W.DWORD],W.BOOL)
AssignJob=bind('AssignProcessToJobObject',[W.HANDLE,W.HANDLE],W.BOOL)
Close=bind('CloseHandle',[W.HANDLE],W.BOOL)
CreateMutex=bind('CreateMutexW',[C.c_void_p,W.BOOL,W.LPCWSTR],W.HANDLE)
CreateEvent=bind('CreateEventW',[C.c_void_p,W.BOOL,W.BOOL,W.LPCWSTR],W.HANDLE)
OpenEvent=bind('OpenEventW',[W.DWORD,W.BOOL,W.LPCWSTR],W.HANDLE)
SetEvent=bind('SetEvent',[W.HANDLE],W.BOOL)
Wait=bind('WaitForSingleObject',[W.HANDLE,W.DWORD],W.DWORD)
OpenProcess=bind('OpenProcess',[W.DWORD,W.BOOL,W.DWORD],W.HANDLE)

class BasicLimits(C.Structure):
    _fields_=[('perProcess',C.c_longlong),('perJob',C.c_longlong),('flags',W.DWORD),('minWS',C.c_size_t),('maxWS',C.c_size_t),('active',W.DWORD),('affinity',C.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]
class IO(C.Structure):
    _fields_=[(name,C.c_ulonglong) for name in ('readOps','writeOps','otherOps','readBytes','writeBytes','otherBytes')]
class ExtendedLimits(C.Structure):
    _fields_=[('basic',BasicLimits),('io',IO),('processMemory',C.c_size_t),('jobMemory',C.c_size_t),('peakProcess',C.c_size_t),('peakJob',C.c_size_t)]

def say(message):
    print(message,flush=True)

state_writer=StateWriter(STATE,warn=say)

def write_state(**values):
    return state_writer.write(values)

def get_json(url,headers=None):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(urllib.request.Request(url,headers=headers or {}),timeout=3) as response:
        return json.load(response)

def listening(port):
    # A refused Windows TCP connect can otherwise consume ~2s per initial probe.
    with socket.socket() as probe:
        probe.settimeout(.1)
        return probe.connect_ex(('127.0.0.1',port))==0

def fingerprint():
    digest=hashlib.sha256(b'geometry-local-production-v1')
    files=[]
    for directory in ('app','components','lib','public','data','worker','db','scripts'):
        for p in (ROOT/directory).rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts:continue
            # These run the launcher, not the website build. Editing them must not rebuild the UI.
            if directory=='scripts' and (p.suffix in ('.py','.ps1') or p.name in ('local-gateway.mjs','launch.mjs','setup.mjs')):continue
            files.append(p)
    files.extend(p for p in ROOT.iterdir() if p.is_file() and (p.suffix in ('.json','.ts','.mjs') or p.name.startswith('.env')))
    for p in sorted(files):
        digest.update(str(p.relative_to(ROOT)).encode());digest.update(p.read_bytes())
    return digest.hexdigest()

def output_fingerprint():
    digest=hashlib.sha256()
    for p in sorted((ROOT/'dist').rglob('*')):
        if p.is_file():
            digest.update(str(p.relative_to(ROOT/'dist')).encode());digest.update(p.read_bytes())
    return digest.hexdigest()

class OwnedServiceProcess:
    def __init__(self,process,job):
        self.process,self.job=process,job
    def poll(self):
        code=self.process.poll()
        if code is not None and self.job:
            # The service gate has exited. Close only its Job so no child
            # Wrangler/Python process can retain that service's listening port.
            Close(self.job);self.job=None
        return code

def start_owned_service(command,**kwargs):
    job=CreateJob(None,None)
    if not job:raise C.WinError(C.get_last_error())
    process=None
    try:
        limits=ExtendedLimits();limits.basic.flags=0x2000
        if not SetJob(job,9,C.byref(limits),C.sizeof(limits)):raise C.WinError(C.get_last_error())
        kwargs['stdin']=subprocess.PIPE
        process=subprocess.Popen([sys._base_executable,'-u',str(Path(__file__).resolve()),'--service'],**kwargs)
        if not AssignJob(job,int(process._handle)):raise C.WinError(C.get_last_error())
        # This is the only point that permits the gate to create descendants.
        process.stdin.write((json.dumps(command)+'\n').encode('utf-8'));process.stdin.flush();process.stdin.close()
        return OwnedServiceProcess(process,job)
    except BaseException:
        try:
            if process:
                process.stdin.close()
                # Popen's own process handle, never a PID recovered from state.json.
                if process.poll() is None:process.kill()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:pass
        finally:
            Close(job)
        raise

def service_gate():
    data=sys.stdin.readline()
    if not data:return 1
    command=json.loads(data)
    if not isinstance(command,list) or not command or not all(isinstance(a,str) for a in command):return 1
    process=subprocess.Popen(command,stdin=subprocess.DEVNULL)
    return process.wait()

def worker(args):
    if sys.stdin.readline().strip()!='GO':return 1
    started=time.monotonic()
    # All descendants now inherit the Windows Job; no detached daemons.
    node=shutil.which('node.exe')
    if not node or not PYTHON.exists():raise RuntimeError('缺少项目的 Node.js 或 Python 环境。')
    for port in (3000,3101,8001):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            try:sock.bind(('127.0.0.1',port))
            except OSError:raise RuntimeError(f'端口 {port} 已被占用。请先关闭原来的 Geometry 或占用它的程序；不会自动结束其他程序。')
    env=os.environ.copy()
    env.update(PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1',NODE_ENV='production',
               GEOMETRY_SERVICE_KEY=secrets.token_hex(32),DEEPSEEK_API_KEY='',AI_API_KEY='',
               GEOMETRY_API_ORIGIN='http://127.0.0.1:8001',GEOMETRY_LOCAL_INSTANCE=secrets.token_hex(16),
               WRANGLER_SEND_METRICS='false',CLOUDFLARE_CF_FETCH_ENABLED='false')
    services=ServiceSupervisor(ROOT,LOCAL,env,notify=say,popen=start_owned_service)
    def alive():
        services.tick()
    def ready(url,timeout,headers=None,check=lambda value: True):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            alive()
            if url.startswith('http://127.0.0.1:') and not listening(int(url.split(':',2)[2].split('/',1)[0])):
                time.sleep(.1);continue
            try:
                if check(get_json(url,headers)):return
            except (OSError,ValueError):pass
            time.sleep(.5)
        raise RuntimeError(f'服务启动超时：{url}。请查看日志。')
    stamp=LOCAL/'build.json'
    signature=fingerprint()
    try:cached=json.loads(stamp.read_text())
    except (OSError,ValueError):cached={}
    if not isinstance(cached,dict):cached={}
    if not (ROOT/'dist/server/wrangler.json').exists() or cached.get('source')!=signature or cached.get('output')!=output_fingerprint():
        say('正在准备网站页面，首次启动或修改代码后可能需要一两分钟…')
        with (LOCAL/'build.log').open('w',encoding='utf-8') as output:
            build=subprocess.Popen([node,'scripts/run-framework.mjs','build'],cwd=ROOT,env=env,
                stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            try:result=build.wait(timeout=300)
            except subprocess.TimeoutExpired:raise RuntimeError('网站构建超时，请查看 build.log。')
        if result:raise RuntimeError('网站构建失败，请查看 build.log。')
        stamp.write_text(json.dumps({'source':signature,'output':output_fingerprint()}))
    say('正在启动 Geometry 网页和计算服务…')
    services.add('api',[str(PYTHON),'-m','uvicorn','server.main:app','--host','127.0.0.1','--port','8001','--no-access-log'])
    services.add('frontend',[node,'--import','./scripts/sites-env.mjs','./node_modules/wrangler/bin/wrangler.js','dev','--config','dist/server/wrangler.json','--local','--persist-to','.wrangler/state','--ip','127.0.0.1','--port','3101','--inspector-port','0'])
    services.add('gateway',[node,'scripts/local-gateway.mjs'])
    ready('http://127.0.0.1:8001/api/health',60,{'X-Geometry-Service-Key':env['GEOMETRY_SERVICE_KEY']},lambda value:value.get('status')=='ok')
    # Wait for actual production HTML instead of merely checking a listening port.
    deadline=time.monotonic()+90
    local=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while True:
        alive()
        if not listening(3101):
            if time.monotonic()>deadline:raise RuntimeError('网页启动超时，请查看 frontend.log。')
            time.sleep(.1);continue
        try:
            with local.open('http://127.0.0.1:3101/',timeout=3) as response:
                if response.status==200 and b'<html' in response.read():break
        except OSError:pass
        if time.monotonic()>deadline:raise RuntimeError('网页启动超时，请查看 frontend.log。')
        time.sleep(.5)
    ready('http://127.0.0.1:3000/__geometry_local_status',15,check=lambda value:value.get('instance')==env['GEOMETRY_LOCAL_INSTANCE'])
    local_seconds=round(time.monotonic()-started,2)
    local_url='http://127.0.0.1:3000/'
    state={'status':'ready','pid':args.owner,'instance':env['GEOMETRY_LOCAL_INSTANCE'],
           'url':local_url,'localUrl':local_url,'localReadySeconds':local_seconds}
    def publish(**changes):
        state.update(changes)
        state['elapsedSeconds']=round(time.monotonic()-started,2)
        write_state(**state)
    publish()
    say(f'\nGeometry 已启动（{local_seconds:.1f} 秒）：{local_url}')
    say('仅在本机运行。使用期间请保留此窗口，关闭本窗口 / Ctrl+C 即可停止。')
    last_services=None;last_publish=0
    while True:
        alive()
        service_status=services.status()
        if service_status!=last_services or time.monotonic()-last_publish>=10:
            publish(services=service_status);last_services=service_status;last_publish=time.monotonic()
        time.sleep(1)


def supervise(args):
    LOCAL.mkdir(parents=True,exist_ok=True)
    mutex=CreateMutex(None,False,NAME+'-lock')
    if not mutex:raise C.WinError(C.get_last_error())
    if C.get_last_error()==183:
        try:
            state=get_json('http://127.0.0.1:3000/__geometry_local_status')
            if state.get('running') is True:
                say('Geometry 已在运行：http://127.0.0.1:3000/')
                if not args.no_browser:os.startfile('http://127.0.0.1:3000/')
            else:raise ValueError('not ready')
        except (OSError,ValueError):say('Geometry 正在另一个启动窗口准备，请等待该窗口提示网站已打开。')
        Close(mutex);return 0
    event=CreateEvent(None,True,False,NAME+'-stop')
    job=CreateJob(None,None)
    parent=OpenProcess(0x00100000,False,os.getppid()) # SYNCHRONIZE, keep exact parent identity
    child=None
    try:
        if not event or not job:raise C.WinError(C.get_last_error())
        limits=ExtendedLimits();limits.basic.flags=0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not SetJob(job,9,C.byref(limits),C.sizeof(limits)):raise C.WinError(C.get_last_error())
        write_state(status='starting',pid=os.getpid())
        def request_stop(*_):SetEvent(event)
        signal.signal(signal.SIGINT,request_stop)
        signal.signal(signal.SIGBREAK,request_stop)
        # Base executable avoids the venv redirector spawning before Job assignment.
        command=[sys._base_executable,'-u',str(Path(__file__).resolve()),'--worker','--owner',str(os.getpid())]
        child=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.PIPE,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        if not AssignJob(job,int(child._handle)):
            child.stdin.close();child.wait(timeout=5);raise C.WinError(C.get_last_error())
        child.stdin.write(b'GO\n');child.stdin.flush();child.stdin.close()
        opened=False
        while child.poll() is None and Wait(event,250)==258:
            if parent and Wait(parent,0)==0:break
            if not opened and not args.no_browser:
                try:
                    state=json.loads(STATE.read_text(encoding='utf-8'))
                    if state.get('pid')==os.getpid() and state.get('localUrl'):
                        os.startfile(state['localUrl']);opened=True
                except (OSError,ValueError):pass
        code=child.poll() or 0
    finally:
        # Also runs for Ctrl+C, startup errors, worker failure, and explicit stop.
        # Window-close/forced owner termination closes this non-inherited handle in the OS.
        if job:Close(job)
        if child:
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill()
        write_state(status='stopped',pid=os.getpid())
        if event:Close(event)
        if parent:Close(parent)
        Close(mutex)
    say('\nGeometry 已停止，本次启动的本机服务均已关闭。')
    return code

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--worker',action='store_true');parser.add_argument('--owner',type=int)
    parser.add_argument('--service',action='store_true')
    parser.add_argument('--stop',action='store_true');parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    args.no_browser=args.no_browser or os.environ.get('GEOMETRY_NO_OPEN')=='1'
    if args.stop:
        event=OpenEvent(2,False,NAME+'-stop')
        if event:
            SetEvent(event);Close(event)
            try:
                state=json.loads(STATE.read_text(encoding='utf-8'));owner=OpenProcess(0x00100000,False,int(state['pid']))
                if owner:
                    completed=Wait(owner,10000)==0;Close(owner)
                    say('Geometry 已停止。' if completed else '已请求停止，启动窗口正在完成清理。')
                else:say('Geometry 已停止。')
            except (OSError,ValueError,KeyError):say('已请求停止 Geometry。')
        else:say('Geometry 当前没有通过启动脚本运行。')
        return 0
    try:return service_gate() if args.service else worker(args) if args.worker else supervise(args)
    except Exception as error:
        say('\n启动失败：'+str(error));return 1

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    sys.exit(main())
