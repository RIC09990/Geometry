"""Conversation history stored on this machine, one file per conversation."""
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from server import conversations
from server.main import app


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(conversations, 'STORE', tmp_path / 'ai-conversations')
    return tmp_path / 'ai-conversations'


def conversation(conversation_id=None, content='等腰三角形为什么会成立？'):
    return {'id': conversation_id or str(uuid.uuid4()), 'title': '',
            'messages': [{'role': 'user', 'content': content},
                         {'role': 'assistant', 'content': '因为两腰相等。', 'reasoning': '先看两腰',
                          'sources': [{'title': '来源', 'url': 'https://example.com/a'}],
                          'elapsedMs': 1234.0,
                          'usage': {'promptTokens': 900, 'cachedTokens': 400, 'completionTokens': 30}},
                         {'role': 'user', 'content': '再看一遍', 'images': [{'name': '题.png', 'dataUrl': 'data:image/png;base64,AAAA'}]}],
            'lastUsage': {'promptTokens': 900, 'cachedTokens': 400, 'completionTokens': 30},
            'summary': {'text': '早期提要', 'through': 2}}


def test_saving_lists_and_reading_a_conversation_round_trips(store):
    client = TestClient(app)
    payload = conversation()
    saved = client.post('/api/ai/conversations', json=payload).json()
    assert saved['title'] == '等腰三角形为什么会成立？'
    assert saved['messageCount'] == 3
    assert 'text' not in saved
    listing = client.get('/api/ai/conversations').json()
    assert [item['id'] for item in listing] == [payload['id']]
    stored = client.get('/api/ai/conversations/' + payload['id']).json()
    assert stored['messages'][1]['reasoning'] == '先看两腰'
    assert stored['messages'][1]['usage']['cachedTokens'] == 400
    assert stored['messages'][2]['images'][0]['name'] == '题.png'
    assert stored['summary'] == {'text': '早期提要', 'through': 2}


def test_newer_conversations_are_listed_first(store):
    client = TestClient(app)
    first = client.post('/api/ai/conversations', json=conversation()).json()
    time.sleep(0.02)
    second = client.post('/api/ai/conversations', json=conversation()).json()
    ids = [item['id'] for item in client.get('/api/ai/conversations').json()]
    assert ids == [second['id'], first['id']]


def test_search_matches_titles_and_answer_text(store):
    client = TestClient(app)
    payload = conversation(content='完全无关的问题')
    client.post('/api/ai/conversations', json=payload)
    assert [item['id'] for item in client.get('/api/ai/conversations?q=两腰').json()] == [payload['id']]
    assert client.get('/api/ai/conversations?q=不存在的词').json() == []


def test_renaming_keeps_the_custom_title_on_later_saves(store):
    client = TestClient(app)
    payload = conversation()
    client.post('/api/ai/conversations', json=payload)
    renamed = client.patch('/api/ai/conversations/' + payload['id'], json={'title': '我的证明'}).json()
    assert renamed['title'] == '我的证明'
    payload['title'] = ''
    payload['messages'][1]['content'] = '更新后的解答。'
    client.post('/api/ai/conversations', json=payload)
    assert client.get('/api/ai/conversations').json()[0]['title'] == '我的证明'


def test_deleting_removes_the_conversation_and_its_metadata(store):
    client = TestClient(app)
    payload = conversation()
    client.post('/api/ai/conversations', json=payload)
    assert client.delete('/api/ai/conversations/' + payload['id']).json() == {'deleted': True}
    assert client.get('/api/ai/conversations').json() == []
    assert client.get('/api/ai/conversations/' + payload['id']).status_code == 404
    assert client.delete('/api/ai/conversations/' + payload['id']).status_code == 200


@pytest.mark.parametrize('conversation_id', ['../../secret', 'not-a-uuid'])
def test_invalid_conversation_ids_are_refused(store, conversation_id):
    client = TestClient(app)
    assert client.get('/api/ai/conversations/' + conversation_id).status_code in (404, 422)


def test_oversized_conversations_are_refused_before_writing(store, monkeypatch):
    monkeypatch.setattr(conversations, 'MAX_BYTES', 200)
    client = TestClient(app)
    response = client.post('/api/ai/conversations', json=conversation())
    assert response.status_code == 413
    assert client.get('/api/ai/conversations').json() == []


def test_missing_conversation_reports_not_found(store):
    client = TestClient(app)
    response = client.get('/api/ai/conversations/' + str(uuid.uuid4()))
    assert response.status_code == 404
    assert response.json()['detail'] == '没有找到这次对话'
