"""Unscored homework remains a complete review, including nullable maximums."""
import asyncio
import base64
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from server import ai,homework
from server.main import app
from tests.test_homework import sample_homework


@pytest.mark.parametrize('verdict',['correct','incorrect','partial','unclear'])
def test_no_score_and_no_rubric_preserve_every_kind_of_item(verdict):
    source=json.dumps({'mode':'homework','content':'本次作答的批注。','grading':{
        'score':None,'maximum':None,'items':[{'label':'本题','verdict':verdict,'studentWork':'几何证明'}]}})
    draft=homework.parse_tutor_reply(source)
    assert draft.grading is not None and draft.grading.maximum is None
    final=homework.checked_homework_reply(source,draft)
    assert final.grading.items[0].verdict==verdict and final.content=='本次作答的批注。'


def test_numeric_score_requires_a_known_maximum():
    with pytest.raises(ValueError):homework.Grading(score=50,maximum=None)
    with pytest.raises(ValueError):homework.Grading(score=101,maximum=100)


def test_captured_complex_model_reply_is_reviewed_once_and_produces_current_pdf(monkeypatch):
    result=json.loads((Path(__file__).parent/'fixtures/unscored-homework-reply.json').read_text(encoding='utf-8'))
    calls=[]
    async def complete(*args,**kwargs):
        calls.append(1)
        assert len(calls)==1,'nullable unscored metadata must not trigger another paid review'
        return result
    monkeypatch.setattr(ai,'complete',complete);monkeypatch.setattr(ai,'recent_requests',ai.deque())
    response=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'isolated-null-rubric'},json={
        'keyMode':'personal','messages':[{'role':'user','content':'检查三动点加权最值作答，不用打分。'}]})
    assert response.status_code==200,response.text
    reply=response.json()
    assert calls==[1] and reply['pdfEligible'] and reply['grading']['maximum'] is None
    assert '独立复核暂未完成' not in reply['content'] and '221' in reply['content']
    pdf=base64.b64decode(reply['reportPdf']['dataUrl'].split(',',1)[1])
    text='\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    assert '作业批改' in text and '学生作答' in text and '暂无法评分' not in text


def test_image_search_reads_the_actual_picture_before_selecting_a_query(monkeypatch):
    queries=[];completions=[]
    async def search(query,**kwargs):
        queries.append(query);assert query=='三角形内点 角度 反射法'
        return [{'title':'几何资料','url':'https://example.com/geometry','content':'相关数学资料'}]
    async def complete(messages,**kwargs):
        completions.append(messages)
        assert messages[-1].images and messages[-1].content.startswith('请查看附件。')
        if len(completions)==1:
            assert not queries,'attachment placeholder must never reach search'
            return {'content':json.dumps({'mode':'conversation','content':'','searchQuery':'三角形内点 角度 反射法'})}
        return {'content':json.dumps({'mode':'solution','content':'结合图中的角度求解。'})}
    monkeypatch.setattr(ai,'search_web',search);monkeypatch.setattr(ai,'complete',complete);monkeypatch.setattr(ai,'recent_requests',ai.deque())
    request=ai.ChatRequest(keyMode='personal',webSearch=True,messages=[ai.Message(role='user',content='请查看附件。',images=sample_homework()[2])])
    reply=asyncio.run(ai.dispatch(request,'isolated-image-query',structured=True,search_query='请查看附件。'))
    assert queries==['三角形内点 角度 反射法'] and len(completions)==2
    assert reply['sources'][0]['title']=='几何资料'


def test_failed_review_does_not_present_unused_search_results_as_references(monkeypatch):
    calls=[]
    async def search(*args,**kwargs):return [{'title':'Unused evidence','url':'https://example.com/unrelated','content':'Unused'}]
    async def complete(*args,**kwargs):
        calls.append(1)
        if len(calls)>1:raise TimeoutError('private details')
        return {'content':json.dumps({'mode':'homework','content':'100/100','grading':{
            'score':100,'maximum':100,'items':[{'label':'1','verdict':'incorrect'}]}})}
    monkeypatch.setattr(ai,'search_web',search);monkeypatch.setattr(ai,'complete',complete);monkeypatch.setattr(ai,'recent_requests',ai.deque())
    request=ai.ChatRequest(keyMode='personal',webSearch=True,messages=[ai.Message(role='user',content='检查当前几何证明')])
    reply=asyncio.run(ai.dispatch(request,'isolated-failed-search',structured=True,verify_homework=True))
    assert len(calls)==2 and reply['sources']==[] and reply['searchStatus'] is None
    assert homework.parse_tutor_reply(reply['content']).grading is None
