"""Prompt layout keeps the repeated prefix byte-identical for provider prefix caching."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from server import ai
from server.ai_providers import PRESETS
from server.main import app


def reply(content='答案'):
    return {'content':json.dumps({'mode':'conversation','content':content,'searchQuery':None,'grading':None,'exportPdf':False}),'finishReason':'stop'}


@pytest.fixture(autouse=True)
def budget(monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque())


def post(messages,**extra):
    body={'provider':PRESETS['deepseek'],'keyMode':'personal','messages':messages,**extra}
    return TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'cache-layout-key'},json=body)


def test_search_evidence_extends_the_current_message_instead_of_shifting_the_prefix(monkeypatch):
    calls=[]
    async def search_web(query,**kwargs):
        return [{'title':'来源','url':'https://example.com/a','content':'检索正文'}]
    async def complete(messages,**kwargs):
        calls.append((messages,kwargs));return reply()
    monkeypatch.setattr(ai,'search_web',search_web)
    monkeypatch.setattr(ai,'complete',complete)
    response=post([{'role':'user','content':'今天天气如何'}],webSearch=True)
    assert response.status_code==200,response.text
    assert len(calls)==1
    messages,system=calls[0][0],calls[0][1]['system']
    assert len(messages)==1 and messages[0].role=='user'
    assert messages[0].content.startswith('今天天气如何')
    assert '本轮检索资料' in messages[0].content and '检索正文' in messages[0].content
    assert '检索资料' not in system


def test_missing_search_results_add_a_tail_notice_without_touching_the_system_prompt(monkeypatch):
    calls=[]
    async def search_web(query,**kwargs):
        raise ai.HTTPException(502,'search failed')
    async def complete(messages,**kwargs):
        calls.append((messages,kwargs));return reply()
    monkeypatch.setattr(ai,'search_web',search_web)
    monkeypatch.setattr(ai,'complete',complete)
    response=post([{'role':'user','content':'今天天气如何'}],webSearch=True)
    assert response.status_code==200,response.text
    messages,system=calls[0][0],calls[0][1]['system']
    assert len(messages)==1 and '未获取到实时检索资料' in messages[0].content
    assert '未获取到实时检索资料' not in system


def test_format_retry_appends_a_message_and_keeps_the_same_system_prompt(monkeypatch):
    calls=[]
    async def complete(messages,**kwargs):
        calls.append((messages,kwargs))
        return {'content':'{"mode":"conversation","content":' if len(calls)==1 else reply()['content'],'finishReason':'stop'}
    monkeypatch.setattr(ai,'complete',complete)
    request=ai.ChatRequest(provider=PRESETS['deepseek'],keyMode='personal',messages=[ai.Message(role='user',content='解释一下等腰三角形')])
    asyncio.run(ai.dispatch(request,'cache-layout-key',ai.chat_system(request),structured=True,verify_homework=True))
    assert len(calls)==2
    first_messages,first_system=calls[0][0],calls[0][1]['system']
    second_messages,second_system=calls[1][0],calls[1][1]['system']
    assert first_system==second_system
    assert len(second_messages)==len(first_messages)+1
    assert second_messages[:-1]==first_messages
    assert '请重新回答' in second_messages[-1].content
