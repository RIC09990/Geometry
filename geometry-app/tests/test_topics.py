import asyncio
import base64
import io
import json
from pathlib import Path

import pytest
from PIL import Image
from fastapi import HTTPException
from fastapi.testclient import TestClient
from server import topics
from server.main import app
from server.models import Problem


def problem():
    raw = json.loads((Path(__file__).resolve().parents[1] / 'data/cases.json').read_text(encoding='utf-8'))[0]
    return Problem.model_validate({k:v for k,v in raw.items() if k not in ['tag','description']})


def image():
    data=io.BytesIO();Image.new('RGB',(30,30),'white').save(data,format='PNG')
    return {'name':'synthetic-test.png','dataUrl':'data:image/png;base64,'+base64.b64encode(data.getvalue()).decode()}


def test_import_transmits_actual_image_and_requires_confirmation(monkeypatch):
    async def dispatch(request,key,**options):
        assert request.messages[0].images[0].dataUrl==image()['dataUrl']
        assert key=='test-key'
        return {'content':json.dumps({'recognizedText':'AB=AC','uncertainties':['核对点名'],'unsupported':[],'problem':problem().model_dump()})}
    monkeypatch.setattr(topics,'dispatch',dispatch)
    reply=TestClient(app).post('/api/ai/import-topic',json={'images':[image()],'keyMode':'personal'},headers={'X-DeepSeek-Api-Key':'test-key'})
    assert reply.status_code==200,reply.text
    assert reply.json()['requiresConfirmation'] is True
    assert reply.json()['uncertainties']==['核对点名']


def test_refinement_keeps_current_problem_in_context(monkeypatch):
    async def dispatch(request,key,**options):
        prompt=request.messages[0].content
        assert '请加上中点条件' in prompt and '当前已确认/编辑的题目' in prompt
        assert 'midpoint' in prompt
        return {'content':json.dumps({'recognizedText':'用户补充 D 是 BC 中点','problem':problem().model_dump()})}
    monkeypatch.setattr(topics,'dispatch',dispatch)
    reply=TestClient(app).post('/api/ai/import-topic',json={'images':[image()],'description':'请加上中点条件','currentProblem':problem().model_dump()})
    assert reply.status_code==200


def test_unsupported_image_conditions_are_not_replaced_by_a_preset(monkeypatch):
    async def dispatch(request,key,**options):
        return {'content':json.dumps({'recognizedText':'AB=5','unsupported':['固定长度 AB=5'],'problem':None})}
    monkeypatch.setattr(topics,'dispatch',dispatch)
    reply=TestClient(app).post('/api/ai/import-topic',json={'images':[image()]})
    assert reply.json()['problem'] is None
    assert reply.json()['unsupported']==['固定长度 AB=5']


@pytest.mark.parametrize('content',['not json','{"problem": {}}'])
def test_incomplete_import_keeps_the_reply_for_follow_up_without_a_fake_problem(monkeypatch,content):
    async def dispatch(request,key,**options):return {'content':content}
    monkeypatch.setattr(topics,'dispatch',dispatch)
    reply=TestClient(app).post('/api/ai/import-topic',json={'images':[image()]})
    assert reply.status_code==200
    result=reply.json()
    assert result['problem'] is None and result['encodingIssues']
    assert result['recognizedText']==content


def test_partial_circle_draft_preserves_missing_goal_and_unencoded_arc(monkeypatch):
    partial=problem().model_dump();partial.pop('goal')
    async def dispatch(request,key,**options):
        return {'content':json.dumps({'recognizedText':'AB 是半圆直径，P 在半圆弧上运动。',
            'unsupported':['P 位于上半圆弧'], 'problem':partial})}
    monkeypatch.setattr(topics,'dispatch',dispatch)
    result=TestClient(app).post('/api/ai/import-topic',json={'images':[image()]}).json()
    assert result['problem'] is None and result['draft']==partial
    assert '求证目标' in ' '.join(result['encodingIssues'])
    assert result['unsupported']==['P 位于上半圆弧']
    assert '半圆' in result['recognizedText']


def test_refinement_includes_partial_draft_when_no_complete_problem_exists(monkeypatch):
    partial={'points':[{'id':'P','x':0,'y':2}], 'conditions':[]}
    async def dispatch(request,key,**options):
        assert json.dumps(partial,ensure_ascii=False) in request.messages[0].content
        assert '想证明两个角相等' in request.messages[0].content
        return {'content':json.dumps({'recognizedText':'请补充角的顶点和端点。', 'problem':None})}
    monkeypatch.setattr(topics,'dispatch',dispatch)
    reply=TestClient(app).post('/api/ai/import-topic',json={'images':[image()],
        'previousDraft':partial, 'description':'想证明两个角相等'})
    assert reply.status_code==200


def test_truncated_recognition_keeps_text_instead_of_claiming_photo_is_unclear():
    result=topics.decode_import('已经读到：AB 是半圆的直径', truncated=True)
    assert result.problem is None and '半圆' in result.recognizedText
    assert result.encodingIssues and '图片不清楚' not in str(result)


def test_import_recovers_mixed_latex_escaping_without_losing_problem():
    recognized=r'Given \(AB=AC\), find \(\angle A\); ratio \(\frac{1}{2}\).'
    source=json.dumps({'recognizedText':recognized,'problem':problem().model_dump()})
    source=source.replace(r'\\(',r'\(').replace(r'\\frac',r'\frac')
    result=topics.decode_import(source)
    assert result.problem is not None
    assert result.recognizedText==recognized and not result.encodingIssues
    assert result.problem.sourceText==recognized


@pytest.mark.parametrize('raw',[
    'partial',42,[],
    {**problem().model_dump(),'conditions':None},
    {**problem().model_dump(),'points':None},
    {**problem().model_dump(),'conditions':[{'kind':'nondegenerate','args':None}]},
])
def test_malformed_import_problem_retains_readable_text_and_allows_refinement(raw,monkeypatch):
    async def dispatch(*args,**kwargs):return {'content':json.dumps({'recognizedText':'Readable geometry statement.','problem':raw})}
    monkeypatch.setattr(topics,'dispatch',dispatch)
    response=TestClient(app).post('/api/ai/import-topic',json={'description':'A geometry question'})
    assert response.status_code==200,response.text
    reply=response.json()
    assert reply['problem'] is None and reply['encodingIssues']
    assert reply['recognizedText']=='Readable geometry statement.'
    assert reply['draft']==(raw if isinstance(raw,dict) else None)


@pytest.mark.parametrize('provider,protocol',[('openai','responses'),('anthropic','anthropic'),('gemini','gemini')])
def test_import_refinement_keeps_selected_provider_image_and_current_conditions(provider,protocol,monkeypatch):
    async def dispatch(request,key,**kwargs):
        assert request.provider.provider==provider and request.provider.protocol==protocol
        assert request.provider.model=='selected-test-model' and key=='isolated-topic-key'
        assert request.messages[0].images[0].dataUrl==image()['dataUrl']
        assert 'current-condition-marker' in request.messages[0].content
        return {'content':json.dumps({'recognizedText':'Updated statement','problem':problem().model_dump()})}
    monkeypatch.setattr(topics,'dispatch',dispatch)
    current=problem().model_dump();current['conditions'][0]['id']='current-condition-marker'
    response=TestClient(app).post('/api/ai/import-topic',headers={'X-AI-Api-Key':'isolated-topic-key'},json={
        'images':[image()],'description':'Refine the conditions','currentProblem':current,'keyMode':'personal',
        'provider':{'provider':provider,'protocol':protocol,'model':'selected-test-model'}})
    assert response.status_code==200,response.text


def idea(p,premises):
    return topics.IdeasReply.model_validate({'routes':[{'title':'Test route','steps':[{'id':'s1','statement':'∠BAD=∠DAC','premises':premises,'conclusion':p.goal.model_dump()}]}]})


def test_ai_relation_is_verified_only_from_joint_listed_premises():
    p=problem()
    checked=topics.check_ideas(p,idea(p,[r.id for r in p.conditions]))[0]
    assert checked['status']=='verified'
    assert checked['steps'][0]['checkedRelation']['args']==p.goal.args
    reduced=[r.id for r in p.conditions if r.kind in ['equal_length','on_segment']]
    checked=topics.check_ideas(p,idea(p,reduced))[0]
    assert checked['status']=='candidate'
    assert checked['steps'][0]['checkStatus']=='counterexample'


def test_removed_premise_is_rejected_instead_of_silently_reintroduced():
    p=problem();p.conditions[0].enabled=False
    with pytest.raises(HTTPException):topics.check_ideas(p,idea(p,[p.conditions[0].id]))


def test_unencoded_reasoning_is_not_marked_formally_verified():
    reply=topics.IdeasReply.model_validate({'routes':[{'title':'Synthetic route','steps':[{'id':'s1','statement':'两个三角形全等','premises':[],'conclusion':None}]}]})
    assert topics.check_ideas(problem(),reply)[0]['status']=='candidate'


def test_forward_or_cyclic_dependency_is_rejected():
    with pytest.raises(HTTPException):topics.check_ideas(problem(),idea(problem(),['s1']))
