import importlib.metadata as md
import json
from pathlib import Path
import time
import os
import hmac
from threading import BoundedSemaphore
from functools import wraps
from fastapi.responses import JSONResponse
from fastapi import FastAPI, HTTPException
from .models import AnalyzeRequest, LayoutRequest, StepRequest, Problem
from .constraints import ConstraintSystem
from .proofs import newclid, teaching_proofs, dependencies
from .nicegeo_adapter import status as nicegeo_status, check as nicegeo_check
from .ai import router as ai_router
from .conversations import router as conversations_router
from .topics import router as topics_router
from .topics_store import router as topics_store_router
from .request_budget import AIRequestBudgetMiddleware

ROOT=Path(__file__).resolve().parents[1]
app=FastAPI(title='Geometry 计算服务',version='0.1.0',docs_url='/api/docs')
app.include_router(ai_router)
app.include_router(conversations_router)
app.include_router(topics_router)
app.include_router(topics_store_router)
capacity=BoundedSemaphore(2)

@app.middleware('http')
async def service_boundary(request,call_next):
    limit=48*1024*1024 if request.url.path.startswith('/api/ai/') else 262144
    if int(request.headers.get('content-length','0') or 0)>limit:
        return JSONResponse({'detail':'题目数据超过大小限制'},status_code=413)
    key=os.environ.get('GEOMETRY_SERVICE_KEY','')
    if key and not hmac.compare_digest(request.headers.get('x-geometry-service-key',''),key):
        return JSONResponse({'detail':'计算服务访问凭据无效'},status_code=401)
    return await call_next(request)

app.add_middleware(AIRequestBudgetMiddleware)

def bounded(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        if not capacity.acquire(blocking=False):raise HTTPException(429,'当前计算任务较多，请稍后重试。')
        try:return fn(*args,**kwargs)
        finally:capacity.release()
    return wrapper

@app.get('/api/health')
def health():
    return {'status':'ok','engines':{n:{'version':md.version(pkg),'status':'runtime_available'} for n,pkg in [('newclid','newclid'),('networkx','networkx'),('z3','z3-solver'),('sympy','sympy')]},'nicegeo':nicegeo_status()}

@app.get('/api/cases')
def cases():return json.loads((ROOT/'data'/'cases.json').read_text(encoding='utf-8'))

@app.post('/api/validate')
def validate(request:LayoutRequest):
    if request.pinned and request.pinned.id not in {p.id for p in request.problem.points}:raise HTTPException(422,'拖动的点不存在')
    if not set(request.fixedPoints)<={p.id for p in request.problem.points}:raise HTTPException(422,'固定点不存在')
    unencoded=[r.id for r in request.problem.conditions if r.enabled and r.kind=='free_text']
    if unencoded and not request.ignoreUnencoded:
        return {'status':'unverified','unverifiedConditions':unencoded,'version':request.problem.version,
                'message':'仍有条件未转成几何约束，无法确认图形符合完整题意；已暂停联动。'}
    target=request.problem
    if unencoded:
        target=request.problem.model_copy(update={'conditions':[r for r in request.problem.conditions
            if not (r.enabled and r.kind=='free_text')]})
    result=ConstraintSystem(target,normalize=False).layout(request.pinned,request.fixedPoints,request.pinTolerance)
    if not unencoded:return {**result,'version':request.problem.version}
    labels=[next((r.description.strip() or r.id) for r in request.problem.conditions if r.id==uid) for uid in unencoded]
    return {**result,'version':request.problem.version,'unverifiedConditions':unencoded,
            'message':'示意图只按已编码条件生成，未落实：'+'、'.join(labels)+'。结论仍以补齐后的完整条件为准。'}

@app.post('/api/analyze')
@bounded
def analyze(request:AnalyzeRequest):
    p=request.problem
    started=time.monotonic()
    if p.goal.kind=='free_text' or any(r.enabled and r.kind=='free_text' for r in p.conditions):
        result={'outcome':'unknown','message':'完整题目已保留，请生成 AI 解答。文字条件尚未完成精确计算核验。','engine':'待核验'}
    elif p.goal.kind=='minimize':
        from .optimization import analyze_minimum
        result=analyze_minimum(p)
    else:result=ConstraintSystem(p).analyze()
    proofs=result.pop('proofs',[])
    search={'status':'skipped','message':''}
    if result['outcome']=='proven' and p.goal.kind!='angle_value':
        proofs=teaching_proofs(p)
        search=newclid(p)
        if search['status']=='found':proofs.append(search)
    elif p.goal.kind=='angle_value':search={'status':'skipped','message':''}
    active=[r.id for r in p.conditions if r.enabled]
    impact=[dependencies(pr.model_dump(),active) for pr in request.previous]
    return {**result,'version':p.version,'proofs':proofs,'search':search,'impact':impact,'elapsed':round(time.monotonic()-started,3),'scope':'核验当前完整保留的已编码关系；Z3 采用精确实数约束，图形坐标仅用于显示。计算未完成时不标为已核验。'}

@app.post('/api/check-step')
@bounded
def check_step(request:StepRequest):
    if any(a not in {p.id for p in request.problem.points} for a in request.statement.args):raise HTTPException(422,'步骤引用了不存在的点')
    p=request.problem.model_copy(deep=True)
    known={r.id for r in p.conditions if r.enabled}
    if not set(request.premises)<=known:raise HTTPException(422,'步骤引用了已取消或不存在的前提')
    for r in p.conditions:r.enabled=r.enabled and r.id in request.premises
    p.goal=request.statement
    try:p=Problem.model_validate(p.model_dump())
    except ValueError as e:raise HTTPException(422,str(e))
    unencoded=p.goal.kind=='free_text' or any(r.enabled and r.kind=='free_text' for r in p.conditions)
    if unencoded or p.goal.kind in ('minimize','angle_value'):
        message=('所选前提或结论仍有未编码的文字表达式，已保留原文，当前不能完成单步形式核验。'
                 if unencoded else '最值和求角度属于求解目标，请使用题目分析或 AI 解答，不能当作已成立的单步结论。')
        result={'outcome':'unknown','message':message,'engine':'待核验'}
        checked={'status':'cannot_check','message':message}
    else:
        result=ConstraintSystem(p).analyze()
        if result['outcome']=='inconsistent':
            checked={'status':'inconsistent','message':'所选前提与非退化要求矛盾，未将矛盾前提下的证明视为有效。'}
        else:
            checked=nicegeo_check(p,request.proofBody,request.reason)
            if checked['status']=='verified' and result['outcome']=='counterexample':
                checked={**checked,'status':'cannot_check','message':'NiceGeo 与独立约束核验出现分歧，本次不接受为已验证证明。'}
    return {'status':checked['status'],'message':checked['message'],'nicegeo':checked,'constraintCheck':result,'constraintLabel':'Z3 对所选前提的独立约束核验；与 NiceGeo 证明脚本检查分别展示','version':request.problem.version}
