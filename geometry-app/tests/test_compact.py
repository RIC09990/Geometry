import json

import pytest
from fastapi.testclient import TestClient

from server import ai
from server.ai_providers import PRESETS
from server.main import app


@pytest.fixture(autouse=True)
def budget(monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque())


def post(messages,**extra):
    body={'provider':PRESETS['deepseek'],'keyMode':'personal','messages':messages,**extra}
    return TestClient(app).post('/api/ai/compact',headers={'X-AI-Api-Key':'compact-key'},json=body)


def test_compaction_summarizes_early_turns_and_unwraps_json_answers(monkeypatch):
    calls=[]
    async def complete(messages,**kwargs):
        calls.append((messages,kwargs));return {'content':'摘要正文','finishReason':'stop'}
    monkeypatch.setattr(ai,'complete',complete)
    envelope=json.dumps({'mode':'conversation','content':'两腰相等','searchQuery':None,'grading':None})
    response=post([{'role':'user','content':'第一题'},{'role':'assistant','content':envelope},{'role':'user','content':'继续'}])
    assert response.status_code==200,response.text
    assert response.json()=={'summary':'摘要正文'}
    transcript=calls[0][0][0].content
    assert transcript.startswith('学生：第一题')
    assert '助手：两腰相等' in transcript and '"grading"' not in transcript
    assert '摘要' in calls[0][1]['system']


def test_compaction_truncates_and_rejects_an_empty_summary(monkeypatch):
    async def long(messages,**kwargs):
        return {'content':'长'*9000,'finishReason':'stop'}
    monkeypatch.setattr(ai,'complete',long)
    assert len(post([{'role':'user','content':'问题'}]).json()['summary'])==ai.COMPACT_MAX_CHARS
    async def empty(messages,**kwargs):
        return {'content':'  ','finishReason':'stop'}
    monkeypatch.setattr(ai,'complete',empty)
    assert post([{'role':'user','content':'问题'}]).status_code==502
