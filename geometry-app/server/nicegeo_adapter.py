"""Structured relations -> closed theorem -> official NiceGeo CLI."""
import os
import re
import subprocess
import sys
import tempfile
import time
from itertools import combinations
from pathlib import Path
from .config import ROOT, setting
from .models import Problem, Relation
from .nicegeo_rules import script as student_script, RuleMismatch

COMMIT = '3719c2cc58fda083aaca2c2fa46a57c7a654e623'
SOURCE = ROOT / 'vendor' / 'nicegeo'
KINDS = {'equal_length', 'equal_angle', 'on_segment', 'midpoint', 'collinear', 'on_circle', 'perpendicular', 'parallel'}

class Unsupported(ValueError):
    pass

def executable() -> Path:
    configured = setting('NICEGEO_EXECUTABLE')
    return Path(configured) if configured else SOURCE / '_build/default/bin/main.exe'

def status():
    available = executable().is_file() and (SOURCE / 'synthetic/env.ncg').is_file()
    return {'status': 'runtime_available' if available else 'unavailable', 'version': COMMIT,
            'source': 'https://github.com/nicegeo/nicegeo', 'documentedCommand': 'dune exec nicegeo file.ncg',
            'supportedRelations': sorted(KINDS),
            'reason': 'NiceGeo 官方 CLI 已就绪；仅在已实现映射内检查提交的证明脚本。' if available else 'NiceGeo 编译产物尚未就绪。'}

def collinear(a: str, b: str, c: str) -> str:
    return f'Exists Line (fun L => OnLine {a} L /\\ OnLine {b} L /\\ OnLine {c} L)'

def distinct(p: Problem, a: str, b: str) -> bool:
    return a != b and (p.nondegenerate.distinct or any({a, b} <= set(t) for t in p.nondegenerate.triangles))

def conjunction(*parts: str) -> str:
    result = parts[-1]
    for part in reversed(parts[:-1]):
        result = f'({part}) /\\ ({result})'
    return result

def on_line(points: list[str], name: str, continuation: str) -> str:
    content = conjunction(*[f'OnLine {point} {name}' for point in points], continuation)
    return f'Exists Line (fun {name} => {content})'

def line_relation(kind: str, args: list[str]) -> str:
    # Segment direction and the order of the two lines do not affect either
    # relation. Canonical names also make these symmetries definitionally equal.
    first, second = sorted([sorted(args[:2]), sorted(args[2:])])
    if kind == 'parallel':
        # The existing coordinate model allows coincident nonzero directions.
        # Strict disjointness alone would silently change its meaning.
        lines = r'(ngL = ngM) \/ ((ngX: Point) -> Not (OnLine ngX ngL /\ OnLine ngX ngM))'
    else:
        # Use arbitrary rays on the supporting lines, not an assumed intersection
        # at one of the named endpoints. This covers AD perpendicular to BC too.
        rays = conjunction('ngV ≠ ngI', 'OnLine ngV ngM', 'Angle ngU ngI ngV = RightAngle')
        rays = f'Exists Point (fun ngV => {rays})'
        rays = conjunction('ngU ≠ ngI', 'OnLine ngU ngL', rays)
        rays = f'Exists Point (fun ngU => {rays})'
        lines = conjunction('OnLine ngI ngL', 'OnLine ngI ngM', rays)
        lines = f'Exists Point (fun ngI => {lines})'
    lines = on_line(second, 'ngM', lines)
    lines = on_line(first, 'ngL', lines)
    return conjunction(f'{first[0]} ≠ {first[1]}', f'{second[0]} ≠ {second[1]}', lines)

def relation(r: Relation, p: Problem) -> str:
    a = r.args
    if r.kind in {'perpendicular', 'parallel'}:
        return line_relation(r.kind, a)
    if r.kind == 'equal_length':
        return f'Length {a[0]} {a[1]} = Length {a[2]} {a[3]}'
    if r.kind == 'equal_angle':
        angle = f'Angle {a[0]} {a[1]} {a[2]} = Angle {a[3]} {a[4]} {a[5]}'
        pairs = dict.fromkeys(tuple(sorted(pair)) for pair in [(a[0],a[1]),(a[1],a[2]),(a[3],a[4]),(a[4],a[5])])
        guards = [f'{x} ≠ {y}' for x,y in pairs if not distinct(p,x,y)]
        return conjunction(*guards, angle) if guards else angle
    if r.kind == 'on_segment':
        return f'Between {a[1]} {a[0]} {a[2]}'
    if r.kind == 'collinear':
        return collinear(*a)
    if r.kind == 'midpoint':
        strict = f'(Between {a[1]} {a[0]} {a[2]}) /\\ (Length {a[1]} {a[0]} = Length {a[0]} {a[2]})'
        if distinct(p,a[1],a[2]):
            return strict
        collapsed = conjunction(f'{a[1]} = {a[0]}',f'{a[0]} = {a[2]}')
        return f'({strict}) \\/ ({collapsed})'
    if r.kind == 'on_circle':
        return f'({a[1]} ≠ {a[2]}) /\\ (Length {a[1]} {a[0]} = Length {a[1]} {a[2]})'
    raise Unsupported(f'NiceGeo 当前尚未验证 {r.kind} 的映射（条件/目标 {r.id}），未忽略该关系。可仅选择本步骤实际使用且受支持的前提。')

def validate_tactics(body: str):
    if re.search(r'\b(?:Axiom|Definition|Theorem|Import|Proof|Qed|Admitted|admit|sorry|sorry_ax)\b|["#]|\(\*|\*\)', body, re.I):
        raise Unsupported('这里只接受证明内的 tactics；不能加入公理、导入、声明、注释或跳过证明。')
    if len(body) > 3000 or len(re.findall(r'\.(?:\s|$)', body)) > 40:
        raise Unsupported('本次证明脚本超过长度或40步限制。')
    if re.search(r'\brepeat\b', body):
        raise Unsupported('本版暂不接受无界 repeat；请列出有限的证明步骤。')

def translate(p: Problem, body: str = '', reason: str = 'automatic') -> str:
    points = [point.id for point in p.points]
    hypotheses = []
    if p.nondegenerate.distinct:
        hypotheses.extend((f'nd{i}', f'{a} ≠ {b}') for i, (a, b) in enumerate(combinations(points, 2)))
    hypotheses.extend((f'nt{i}', f'Not ({collinear(*triangle)})') for i, triangle in enumerate(p.nondegenerate.triangles))
    premises = [(f'h{i}', relation(r, p)) for i, r in enumerate(p.conditions) if r.enabled]
    hypotheses.extend(premises)
    goal = relation(p.goal, p)
    if reason=='custom' and not body.strip():
        raise RuleMismatch('高级模式中请先填写证明代码，或关闭高级模式选择一个常用理由。')
    if reason not in {'automatic','custom'}:
        body=student_script(p,reason,relation,distinct)
    if not body.strip():
        matching = next((name for name, prop in premises if prop == goal), None)
        if matching:
            body = f'exact {matching}.'
        else:
            tactics = ['try reflexivity.'] if goal.startswith(('Length ', 'Angle ')) else []
            body = '\n'.join([*tactics, *[f'try exact {name}.' for name, _ in premises]])
    validate_tactics(body)
    binders = [f'({name}: Point)' for name in points] + [f'({name}: {prop})' for name, prop in hypotheses]
    introductions = '\n'.join(f'intro {name}.' for name in [*points, *[name for name, _ in hypotheses]])
    return ('Theorem GeometryStudentStep : ' + ' -> '.join([*binders, '(' + goal + ')'])
            + '\nProof.\n' + introductions + '\n' + body.strip() + '\nQed.\n')

def check(p: Problem, body: str = '', reason: str = 'automatic') -> dict:
    started = time.monotonic()
    try:
        source = translate(p, body, reason)
    except (Unsupported,RuleMismatch) as error:
        return {'status': 'cannot_check', 'message': str(error), 'version': COMMIT}
    if status()['status'] != 'runtime_available':
        return {'status': 'cannot_check', 'message': 'NiceGeo 运行环境尚未准备完成。', 'source': source, 'version': COMMIT}
    temporary = ROOT / '.local/nicegeo-jobs'
    temporary.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='step-', dir=temporary) as directory:
            proof = Path(directory) / 'step.ncg'
            proof.write_text(source, encoding='utf-8')
            env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'NICEGEO_TONE': 'minimal'}
            if os.name == 'nt':
                base = ROOT / '.local/opam'
                extra = [base / 'geometry/bin', base / '.cygwin/root/usr/x86_64-w64-mingw32/sys-root/mingw/bin']
                env['PATH'] = os.pathsep.join([*[str(v) for v in extra], env.get('PATH', '')])
            result = subprocess.run([sys.executable, str(ROOT / 'server/nicegeo_runner.py'), str(executable().resolve()), str(proof.resolve())],
                cwd=SOURCE, env=env, capture_output=True, encoding='utf-8', errors='replace', timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            raw = (result.stdout + '\n' + result.stderr).strip()[-24000:]
            if result.returncode == 124:
                return {'status': 'timeout', 'message': 'NiceGeo 检查超时，当前无法判断。', 'source': source, 'raw': raw, 'version': COMMIT}
            if result.returncode not in (0, 1) or (result.returncode == 0 and 'Valid proofs!' not in result.stdout):
                return {'status': 'cannot_check', 'message': 'NiceGeo 运行异常，本次无法判断证明。', 'source': source, 'raw': raw, 'exitCode': result.returncode, 'version': COMMIT}
            passed = result.returncode == 0 and 'Valid proofs!' in result.stdout
            return {'status': 'verified' if passed else 'rejected', 'version': COMMIT,
                    'message': 'NiceGeo 内核已检查此证明。' if passed else '此证明未通过 NiceGeo 检查；不能据此判断目标为假。',
                    'source': source, 'raw': raw, 'exitCode': result.returncode,
                    'elapsed': round(time.monotonic() - started, 3)}
    except subprocess.TimeoutExpired:
        return {'status': 'timeout', 'message': 'NiceGeo 检查超过15秒，当前无法判断。', 'source': source, 'version': COMMIT}
    except OSError:
        return {'status': 'cannot_check', 'message': 'NiceGeo 进程无法启动，请检查运行环境。', 'source': source, 'version': COMMIT}
