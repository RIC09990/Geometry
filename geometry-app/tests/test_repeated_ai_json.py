"""Regression for the actual duplicate-JSON reply shown as garbled math in AI."""
import base64
import io
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfReader

from server import ai
from server.homework import parse_tutor_reply,read_ai_json,has_grading_payload,TutorReplyFormatError
from server.main import app
from server.topics import read_json
from server import topics
from tests.test_topics import problem


@pytest.mark.parametrize('separator',['','\n','\n  \n'])
@pytest.mark.parametrize('malformed',[False,True])
def test_identical_reply_copies_are_decoded_once_with_original_math(separator,malformed):
    content='1）正确。\n'+r'\[3(x-2)=12\Rightarrow x=6.\]'+'\n2）错误。\n'+r'\[\frac12+\frac13=\frac56.\]'
    source=json.dumps({'mode':'homework','content':content},ensure_ascii=False)
    if malformed:source=source.replace(r'\\[',r'\[')
    reply=parse_tutor_reply(source+separator+source)
    assert reply.content==content and reply.content.count('正确')==1
    assert reply.grading is None and not reply.exportPdf


def test_valid_json_keeps_literal_json_examples_inside_the_answer():
    content='An example: {"content":"not an extra answer"}.\n'+r'\(\frac12\)'
    source=json.dumps({'mode':'conversation','content':content})
    assert parse_tutor_reply(source).content==content
    markdown='An example:\n```json\n{"content":"example value"}\n```'
    assert parse_tutor_reply(markdown).content==markdown


def test_repeated_grading_still_passes_through_the_consistency_guard():
    source=json.dumps({'mode':'homework','content':'Review.','grading':{'score':50,'maximum':100}})
    assert has_grading_payload(source+'\n'+source)
    assert parse_tutor_reply(source+'\n'+source).grading.score==50


def test_conflicting_objects_are_never_selected_or_displayed_as_protocol_text():
    source=json.dumps({'mode':'homework','content':'Correct.','exportPdf':True})+'\n'+json.dumps({'mode':'homework','content':'Incorrect.'})
    with pytest.raises(ValueError):read_ai_json(source)
    with pytest.raises(TutorReplyFormatError):parse_tutor_reply(source)
    with pytest.raises(HTTPException):read_json(source)


def test_geometry_import_uses_same_duplicate_guard_without_merging_fields():
    payload={'recognizedText':'AB=AC','problem':None,'uncertainties':['缺少目标']}
    source=json.dumps(payload)
    assert read_json(source+'\n'+source)==payload


def test_actual_http_reply_and_generated_pdf_contain_one_answer_not_raw_json(monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    content='第一题正确。\n'+r'\[3(x-2)=12\Rightarrow x=6.\]'+'\n第二题错误，改正如下：\n'+r'\[\frac12+\frac13=\frac56.\]'
    source=json.dumps({'mode':'homework','content':content,'grading':{'score':None,'items':[
        {'label':'1','verdict':'correct','studentWork':'3(x-2)=12，所以x=6。'},
        {'label':'2','verdict':'incorrect','studentWork':'1/2+1/3=2/5','correction':'5/6'},
    ]}},ensure_ascii=False)
    async def complete(*args,**kwargs):return {'content':source+'\n'+source,'finishReason':'stop'}
    monkeypatch.setattr(ai,'complete',complete)
    response=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'isolated-duplicate-test'},json={
        'keyMode':'personal','messages':[{'role':'user','content':'检查我的解答并生成PDF'}]})
    assert response.status_code==200,response.text
    reply=response.json()
    assert reply['content'].endswith(content) and 'reportError' not in reply
    document=PdfReader(io.BytesIO(base64.b64decode(reply['reportPdf']['dataUrl'].split(',',1)[1])))
    text='\n'.join(page.extract_text() for page in document.pages)
    assert text.count('第一题正确')==1 and '"mode"' not in text and '公式原文' not in text


@pytest.mark.parametrize('payload',[
    {'routes':[{'title':'Incomplete route','steps':[]}],'answer':'完整的自然语言解答。'},
    {'routes':'bad route graph','answer':'完整的自然语言解答。'},
])
def test_invalid_optional_proof_graph_never_hides_readable_answer_or_shows_json(payload,monkeypatch):
    async def dispatch(*args,**kwargs):return {'content':json.dumps(payload)}
    monkeypatch.setattr(topics,'dispatch',dispatch)
    reply=TestClient(app).post('/api/ai/proof-ideas',json={'problem':problem().model_dump()}).json()
    assert reply['answer']==payload['answer'] and reply['proofs']==[]


def test_malformed_proof_protocol_never_becomes_user_facing_answer(monkeypatch):
    async def dispatch(*args,**kwargs):return {'content':'{"routes":[{"title":"unfinished"'}
    monkeypatch.setattr(topics,'dispatch',dispatch)
    reply=TestClient(app).post('/api/ai/proof-ideas',json={'problem':problem().model_dump()}).json()
    assert reply['answer']=='' and reply['proofs']==[] and '格式不完整' in reply['message']


def test_duplicate_route_only_reply_renders_readable_steps(monkeypatch):
    payload={'routes':[{'title':'路线','steps':[{'id':'s1','statement':'AB=AC，故两底角相等。','premises':[]}]}]}
    source=json.dumps(payload)
    async def dispatch(*args,**kwargs):return {'content':source+'\n'+source}
    monkeypatch.setattr(topics,'dispatch',dispatch)
    reply=TestClient(app).post('/api/ai/proof-ideas',json={'problem':problem().model_dump()}).json()
    assert '两底角相等' in reply['answer'] and '"routes"' not in reply['answer']
    assert len(reply['proofs'])==1 and reply['proofs'][0]['status']=='candidate'
