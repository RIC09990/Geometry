"""Image-to-problem import and explicitly attributed AI proof candidates."""
import asyncio
import json
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import Field, ValidationError, field_validator, model_validator
import z3

from .ai import ImageInput, Message, ChatRequest, dispatch, sse_response
from .constraints import ConstraintSystem
from .models import KINDS, StrictModel, Problem, Relation
from .import_normalization import normalize_problem
from .ai_providers import ProviderOptions, resolve_provider
from .homework import read_ai_json
from .spatial_conditions import spatial_statement

router = APIRouter(prefix='/api/ai')


class ImportRequest(StrictModel):
    images: list[ImageInput] = Field(default_factory=list, max_length=600)
    description: str = Field(default='', max_length=20000)
    currentProblem: Problem | None = None
    previousText: str = Field(default='', max_length=20000)
    previousDraft: dict | None = None
    conversation: list[Message] = Field(default_factory=list, max_length=16)
    reasoningEffort: Literal['low','medium','high','max']|None=None
    language: Literal['zh', 'en'] = 'zh'
    keyMode: Literal['personal', 'server'] = 'server'
    provider: ProviderOptions|None=None

    @model_validator(mode='after')
    def content_present(self):
        if not self.images and not self.description.strip():raise ValueError('请上传题目图片或填写题目文字。')
        if sum(len(m.content) for m in self.conversation)>50000:raise ValueError('核对记录过长，请重新整理题目。')
        if any(m.images for m in self.conversation):raise ValueError('核对记录中的图片请统一放在题目附件中。')
        return self

    @field_validator('previousDraft')
    @classmethod
    def bounded_draft(cls, value):
        if value is not None and len(json.dumps(value, ensure_ascii=False)) > 30000:
            raise ValueError('待核对的题目数据过长，请分成一道题后继续。')
        return value


class ImportReply(StrictModel):
    recognizedText: str = Field(max_length=20000)
    uncertainties: list[str] = Field(default_factory=list, max_length=20)
    unsupported: list[str] = Field(default_factory=list, max_length=20)
    problem: Problem | None = None
    draft: dict | None = None
    encodingIssues: list[str] = Field(default_factory=list, max_length=20)


def decode_import(content: str, truncated=False) -> ImportReply:
    """Keep what the model read even when its proposed formal problem is incomplete."""
    issues = ['回复尚未完整返回，可以继续补充或让助手接着整理。'] if truncated else []
    try:
        payload = read_json(content)
    except HTTPException:
        return ImportReply(recognizedText=content[:20000], encodingIssues=issues +
                           ['已保留助手回复。请在下方继续沟通，补齐条件和求证目标后再生成例题。'])
    if not isinstance(payload, dict):
        return ImportReply(recognizedText=content[:20000], encodingIssues=issues +
                           ['助手尚未整理出题目对象，请在下方继续补充。'])
    raw = payload.get('problem')
    # Providers sometimes call a degree relation `angle`. Normalize the
    # unambiguous spelling only; do not infer any missing geometric premise.
    if isinstance(raw,dict):
        conditions=raw.get('conditions',[])
        for relation in (conditions if isinstance(conditions,list) else []) + ([raw['goal']] if isinstance(raw.get('goal'),dict) else []):
            if isinstance(relation,dict) and relation.get('kind')=='angle' and isinstance(relation.get('args'),list) and len(relation['args'])==3:
                relation['kind']='fixed_angle' if relation.get('value') is not None else 'angle_value'
    draft = raw if isinstance(raw, dict) else payload.get('draft')
    if not isinstance(draft, dict) or len(json.dumps(draft, ensure_ascii=False)) > 30000:
        draft = None
    original = payload.get('recognizedText')
    original = original if isinstance(original, str) and original.strip() else content
    notices = {}
    for name in ('uncertainties', 'unsupported'):
        values = payload.get(name, [])
        notices[name] = [str(v)[:1000] for v in values][:20] if isinstance(values, list) else [str(values)[:1000]]
    problem = None
    if raw is not None:
        try:
            problem = Problem.model_validate(normalize_problem(raw,original[:20000],notices['unsupported']))
            for point in problem.points:point.fixed=False
            notices['unsupported']=[notice for notice in notices['unsupported'] if not spatial_statement(notice)]
        except ValidationError as error:
            names = {'goal':'求证目标', 'points':'点', 'conditions':'已知条件', 'nondegenerate':'非退化要求',
                     'triangles':'三角形', 'segments':'线段', 'circles':'圆', 'title':'题目名称',
                     'id':'编号', 'args':'涉及的点', 'kind':'关系类型', 'x':'横坐标', 'y':'纵坐标'}
            for item in error.errors(include_url=False)[:8]:
                location = ' · '.join(names.get(str(v), str(v)) for v in item['loc']) or '题目'
                detail = '尚未提供' if item['type'] == 'missing' else item['msg'].removeprefix('Value error, ')
                issues.append(f'{location}：{detail}')
        except (ValueError,TypeError,AttributeError,KeyError):
            issues.append('题目对象或条件格式尚未整理完整，已保留识别文字，请继续核对。')
    elif not notices['uncertainties'] and not notices['unsupported']:
        issues.append('题目还没有整理完整。请告诉助手剩余条件，以及你想证明什么。')
    return ImportReply(recognizedText=original[:20000], problem=problem, draft=draft,
                       encodingIssues=issues[:20], **notices)


def read_json(content: str):
    text = content.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
    try:return read_ai_json(text)
    except (ValueError,TypeError):
        raise HTTPException(502, 'AI 未返回完整的题目数据，请重新识别；没有用预设例题替代。') from None


async def run_import(request:ImportRequest,personal_key:str|None,legacy_key:str|None,emit=None)->dict:
    schema = ImportReply.model_json_schema()
    task = ('请识别附件中的几何题，转为可编辑的题目。返回符合下列 schema 的单个 JSON 对象，不要 Markdown。'
            'recognizedText 保留实际读到的题目文字；uncertainties 列出看不清、需用户核对的内容；'
            'unsupported 列出无法用当前关系准确表达的原题条件或目标，不要悄悄忽略。'
            '不能仅凭图形看起来等长、平行或垂直就当作已知；使用题面文字或明确标记。'
            'points 坐标仅用于示意和初始布局，不是证明前提。id 用 import-draft，version 和 schemaVersion 为1。'
            '题干明确给出的点坐标必须另编码为 fixed_point 条件：args=[A],coordinates=[-1,2] 表示 A(-1,2)；负数与零均支持。不要把已知坐标只放进 points 或 free_text。'
            '例如单位圆上动点 P，应编码圆心 O(0,0) 的 fixed_point 与 fixed_length=[O,Q],value=1，再用 on_circle=[P,O,Q]；不能遗漏圆心与半径条件。'
            '以下关系的 args 顺序：equal_length=[A,B,C,D] 表示 AB=CD；midpoint=[M,A,B]；'
            'perpendicular/parallel=[A,B,C,D]；collinear=[A,B,C]；on_segment=[D,B,C] 表示 D 在线段 BC 上（不含端点），界面和整理后的条件使用这个说法；'
            'equal_angle=[B,A,D,D,A,C] 表示 ∠BAD=∠DAC；on_circle=[P,O,Q] 表示 P 在以 O 为圆心过 Q 的圆上。'
            'inside_triangle=[D,A,B,C] 表示 D 严格在△ABC内部（不含边界），已正式支持，不能再用free_text代替。inside_circle/outside_circle=[P,O,Q] 表示P严格在以O为圆心过Q的圆内/圆外。'
            'same_side/opposite_side=[P,Q,A,B] 表示P、Q在直线AB的严格同侧/异侧（均不在线上）。图中未命名内点可使用明确说明的临时点名，允许用户修改；不要因缺一个字母而丢掉已看清的连线和角度。'
            'fixed_angle=[A,C,B],value=40 表示 ∠ACB=40°；angle_value=[A,B,C] 只能作为goal，表示求∠ABC的度数。不要使用angle这种未定义名称。已知角度和求角度都支持。'
            '图形对象、条件、目标、非退化要求要分别列出；不要把目标放进已知条件。'
            '可编辑条件 toggleable=true。先读出题面，再整理条件；整理不完整不能说成图片不清楚。'
            '没有给出求证目标时不要编造目标，在 uncertainties 中问学生想证明什么。'
            '现在支持圆弧、数值长度、线段比、三角形相似和加权距离最小值，不要把它们列为不支持。'
            'length_ratio args=[P,A,P,B],value=2 表示 PA=2PB，画板会自动导出阿氏圆；不用另造独立圆心前提。similar_triangles args=[A,D,E,A,B,C] 表示按所列顺序对应的两个非退化三角形相似，可镜像。'
            '若题目需要辅助构造，在识别阶段只收录原题对象和已知；证明中可以提出辅助点思路，但不能偷加辅助结论作独立已知。'
            'fixed_length args=[A,B],value=6 表示 AB=6。on_arc args=[P,O,A,B],orientation=ccw或cw，表示以O为圆心从A到B的不超过180度的有向圆弧，包含端点；半圆也支持。'
            'circles 中 end=B 表示只画从 through=A 到 end=B 的圆弧，orientation 与条件一致；不填end才画整圆。'
            'minimize 只能用作goal：args=[P,C,P,D],weights=[1,2] 表示求 PC+2PD 最小值。不要把最值写成相等关系或普通已知。'
            '所有 points 的 fixed 一律为 false，不要用这个显示字段锁点。画板根据当前有效条件自动决定点的轨迹、交点和联动；不得把参考图的位置当作隐藏约束。'
            '必须画出题面已有线段与圆弧。P在圆弧上不能只编成整圆；不得以要求学生另行提供清晰图片代替已经读到的内容。'
            '非退化要求只添加题意必需的三角形；若动点可到弧端点，distinct=false。'
            '不得把推导得到的长度、垂直、中点等另加为独立已知，避免删除原条件后暗中保留推论。'
            '不因关系种类、复杂公式、最值或定值而拒绝整理整道题。未能转成几何内核关系的条件使用 free_text，description 保存完整原文或 LaTeX 公式，args 可为空；目标也可用 free_text 保存任意表达式和求解要求。'
            'nondegenerate 是独立对象字段，不是条件的 kind。三角形不共线写入 nondegenerate.triangles；不得生成 kind=nondegenerate。'
            '尽力提取图中的点、线段、圆与圆弧，用坐标绘制大致而不矛盾的初始图。仅看不清的内容提问核对，复杂题照样输出 problem。'
            '如果提供了当前题目，结合学生的新补充修改它，保留没有被明确要求删除的条件。'
            '用户明确要求新增的条件可以添加，recognizedText 中说明这是用户补充；不要把其他条件悄悄丢掉。'
            '\n当前已确认/编辑的题目：' + (json.dumps(request.currentProblem.model_dump(),ensure_ascii=False) if request.currentProblem else '无') +
            '\n上次识别文字：' + request.previousText +
            '\n此前核对对话：' + json.dumps([{'role':m.role,'content':m.content} for m in request.conversation],ensure_ascii=False) +
            '\n上次尚未整理完整的题目：' + (json.dumps(request.previousDraft,ensure_ascii=False) if request.previousDraft else '无') +
            '\nJSON schema：' + json.dumps(schema, ensure_ascii=False) + '\n用户补充：' + request.description)
    provider = resolve_provider(request.provider)
    effort = request.reasoningEffort or ('low' if provider.reasoningEffort in (None,'high','max') else provider.reasoningEffort)
    if provider.protocol in ('chat','responses'):
        provider = provider.model_copy(update={'reasoningEffort':effort})
    response = await dispatch(ChatRequest(messages=[Message(role='user', content=task, images=request.images)],
                                         language=request.language,keyMode=request.keyMode,provider=provider),personal_key or legacy_key,structured=True,emit=emit)
    parsed = decode_import(response['content'], response.get('finishReason') == 'length')
    return {**parsed.model_dump(),'provider':response.get('provider','AI'),'requiresConfirmation':True}


@router.post('/import-topic')
async def import_topic(request:ImportRequest,personal_key:str|None=Header(default=None,alias='X-AI-Api-Key'),legacy_key:str|None=Header(default=None,alias='X-DeepSeek-Api-Key')):
    return await run_import(request,personal_key,legacy_key)


@router.post('/import-topic/stream')
async def import_topic_stream(request:ImportRequest,personal_key:str|None=Header(default=None,alias='X-AI-Api-Key'),legacy_key:str|None=Header(default=None,alias='X-DeepSeek-Api-Key')):
    """Stream recognition progress, then the same payload as /import-topic."""
    async def produce(emit):
        payload=await run_import(request,personal_key,legacy_key,emit)
        await emit({'type':'done','reply':payload})
    return sse_response(produce,request.language)


class IdeasRequest(StrictModel):
    problem: Problem
    language: Literal['zh', 'en'] = 'zh'
    keyMode: Literal['personal', 'server'] = 'server'
    webSearch: bool = True
    diagram: ImageInput | None = None
    provider: ProviderOptions|None=None


class IdeaStep(StrictModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]+$', max_length=60)
    statement: str = Field(min_length=1, max_length=2000)
    reason: str = Field(default='', max_length=1000)
    premises: list[str] = Field(default_factory=list, max_length=30)
    conclusion: Relation | None = None


class Idea(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    steps: list[IdeaStep] = Field(min_length=1, max_length=12)


class IdeasReply(StrictModel):
    routes: list[Idea] = Field(max_length=3)
    message: str = Field(default='', max_length=2000)
    answer: str = Field(default='',max_length=30000)


def same_goal_relation(conclusion: Relation, goal: Relation):
    """Compare the complete encoded claim, without labels or display metadata."""
    fields = {'kind', 'args'}
    if goal.kind in ('fixed_length', 'fixed_angle', 'length_ratio'):
        fields.add('value')
    elif goal.kind == 'fixed_point':
        fields.add('coordinates')
    elif goal.kind == 'minimize':
        fields.add('weights')
    elif goal.kind == 'on_arc':
        fields.add('orientation')
    # Exact schema values are intentional: even a small difference can change
    # the theorem. Drawing tolerances must never decide proof equivalence.
    return conclusion.model_dump(include=fields) == goal.model_dump(include=fields)


def check_ideas(problem: Problem, reply: IdeasReply):
    known = {r.id: r for r in problem.conditions if r.enabled}
    point_ids = {p.id for p in problem.points}
    proofs = []
    for index, route in enumerate(reply.routes):
        prefix = f'ai-{index + 1}-'
        nodes = {}; facts = {}; steps = []; used = set()
        for step in route.steps:
            if step.id in nodes or step.id in known or step.id == 'domain':
                raise HTTPException(502, 'AI 证明的步骤编号发生冲突，请重试。')
            if any(p not in known and p not in nodes and p != 'domain' for p in step.premises):
                raise HTTPException(502, 'AI 证明引用了不存在、已取消或尚未得出的依据，请重试。')
            check = 'unencoded'
            conclusion = step.conclusion
            if conclusion and conclusion.kind not in ('minimize','angle_value','free_text'):
                if conclusion.kind not in KINDS or len(conclusion.args) != KINDS[conclusion.kind] or any(p not in point_ids for p in conclusion.args):
                    raise HTTPException(502, 'AI 步骤使用了不能准确编码的关系，请重试。')
                if any(p in known and known[p].kind=='free_text' for p in step.premises):
                    check='unencoded'
                elif any(p in nodes and p not in facts for p in step.premises):
                    check = 'unverified_dependency'
                else:
                    reduced = problem.model_copy(deep=True)
                    reduced.conditions = [known[p] if p in known else facts[p] for p in step.premises if p != 'domain']
                    # Coordinate normalization must preserve the claim being
                    # checked here, not only the final goal of the whole route.
                    reduced.goal = conclusion
                    system = ConstraintSystem(reduced, timeout=500)
                    consistent = system.solver.check()
                    if consistent == z3.unsat:
                        check = 'inconsistent'
                    elif consistent == z3.unknown:
                        check = 'unknown'
                    else:
                        system.solver.add(z3.Not(system.encode(conclusion)))
                        answer = system.solver.check()
                        check = 'verified' if answer == z3.unsat else 'counterexample' if answer == z3.sat else 'unknown'
                    if check == 'verified':
                        facts[step.id] = conclusion.model_copy(update={'id': prefix + step.id, 'enabled': True})
            nodes[step.id] = prefix + step.id
            used.update(p for p in step.premises if p in known)
            steps.append({'id': nodes[step.id], 'statement': step.statement, 'rule': step.reason,
                          'premises': [nodes.get(p, p) for p in step.premises], 'checkStatus': check, 'checkedRelation': conclusion.model_dump() if conclusion else None})
        last = route.steps[-1].conclusion
        verified = all(s['checkStatus'] == 'verified' for s in steps) and last and same_goal_relation(last, problem.goal)
        proofs.append({'id': prefix + 'route', 'title': route.title, 'engine': 'AI · 逐步约束核验',
                       'status': 'verified' if verified else 'candidate', 'steps': steps,
                       'assumptionIds': sorted(used), 'assumptionNodes': [],
                       'verification': '编码关系逐步检查；自然语言说明来自 AI。' if verified else 'AI 候选思路，包含尚未核验或未通过的步骤。'})
    return proofs


@router.post('/proof-ideas')
async def proof_ideas(request:IdeasRequest,personal_key:str|None=Header(default=None,alias='X-AI-Api-Key'),legacy_key:str|None=Header(default=None,alias='X-DeepSeek-Api-Key')):
    from .ai import problem_context,problem_search_query
    prompt = ('请根据当前全部有效条件解答题目，包括任意形式的最值、定值、复杂表达式。'
              'answer 写完整规范的最终数学过程；先给答案，再按已知、推导、结论组织，不展示试错或未完成的路线。'
              '公式使用 LaTeX，分式用 \\frac，角、垂直、平行、全等等使用专业数学符号。'
              '利用所提供的联网资料查找原题或相关方法，核对来源是否和当前条件一致；撤去的条件不得偷偷加回。'
              '若结论不成立，给出满足当前全部条件的具体反例并逐项代入核对。数值试验不能冒充普遍证明。'
              '给出有实际差异的证明路线，不能把一条结论重复三次。找不到时 routes 返回空数组并说明，answer 仍保留实际进展。'
              '返回符合 schema 的一个 JSON 对象。使用规范数学符号，不要将观察当成证明。'
              '每个步骤写清 statement、reason 和 premises。premises 只能是实际使用的保留条件 id、'
              '本路线先前步骤 id 或 domain（非退化要求）。不要补入未给出的已知条件。'
              'conclusion 如能使用已编码关系准确表达就填写，否则用 null；未编码不阻挡自然语言解答。'
              '最后一步必须对应当前目标。Relation 的 args 语义与题目一致。'
              '\n当前题目：' + json.dumps(problem_context(request.problem), ensure_ascii=False) +
              '\nJSON schema：' + json.dumps(IdeasReply.model_json_schema(), ensure_ascii=False))
    response = await dispatch(ChatRequest(messages=[Message(role='user', content=prompt,images=[request.diagram] if request.diagram else [])], language=request.language,
                                         keyMode=request.keyMode,webSearch=request.webSearch,provider=request.provider),personal_key or legacy_key,structured=True,search_query=problem_search_query(request.problem))
    try:
        payload=read_json(response['content'])
    except HTTPException:
        # Ordinary prose may still be useful, but malformed protocol objects
        # must never be presented as a mathematical solution.
        raw=response['content'].strip()
        answer=raw if not raw.startswith(('{','[','```json')) else ''
        return {'version':request.problem.version,'proofs':[],'answer':answer,
                'message':'本次解答未形成可追踪的步骤图。' if answer else 'AI 返回的解答格式不完整，请重试。',
                'sources':response.get('sources',[]),'searchStatus':response.get('searchStatus')}
    try:parsed = IdeasReply.model_validate(payload)
    except ValidationError:
        # Keep a complete readable answer when only the optional route graph
        # failed validation. Do not serialize the failed graph into the page.
        answer=payload.get('answer','') if isinstance(payload,dict) else ''
        answer=answer[:30000] if isinstance(answer,str) else ''
        return {'version':request.problem.version,'proofs':[],'answer':answer,
                'message':'解答已保留；本次依赖步骤格式不完整，请重新生成。' if answer else 'AI 返回的解答格式不完整，请重试。',
                'sources':response.get('sources',[]),'searchStatus':response.get('searchStatus')}
    try:proofs = await asyncio.to_thread(check_ideas, request.problem, parsed)
    except HTTPException as error:
        proofs=[];parsed.message='解答已保留；依赖步骤需重新整理：'+str(error.detail)
    answer=parsed.answer or '\n\n'.join('### '+route.title+'\n\n'+'\n\n'.join(step.statement for step in route.steps) for route in parsed.routes)
    return {'version': request.problem.version, 'proofs': proofs, 'message': parsed.message,'answer':answer,
            'sources':response.get('sources',[]),'searchStatus':response.get('searchStatus')}
