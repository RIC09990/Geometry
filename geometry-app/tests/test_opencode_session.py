"""OpenCode's gateway needs a per-conversation routing header and a named client."""
import asyncio
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from server import ai
from server.ai_providers import ProviderOptions, resolve_provider
from server.main import app

KEY = 'isolated-opencode-key'
OPENCODE = {'provider': 'compatible', 'baseUrl': 'https://opencode.ai/inference/go/v1',
            'protocol': 'chat', 'model': 'deepseek-v4.1-flash'}


@pytest.fixture(autouse=True)
def isolated_rate_limit(monkeypatch):
    monkeypatch.setattr(ai, 'recent_requests', ai.deque())


def reply(seen):
    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={'choices': [{'message': {'content': 'ok'}, 'finish_reason': 'stop'}]})
    return httpx.MockTransport(respond)


def call(session_id=None, config=OPENCODE):
    seen = []
    options = resolve_provider(ProviderOptions(**config))
    result = asyncio.run(ai.complete([ai.Message(role='user', content='Question')], api_key=KEY,
        provider=options, transport=reply(seen), session_id=session_id))
    assert result['content'] == 'ok'
    return seen[0]


def test_the_conversation_id_becomes_the_required_routing_header():
    request = call('conversation-abc123')
    assert request.headers['x-opencode-session'] == 'conversation-abc123'
    assert request.headers['user-agent'] == 'Geometry/1.0'
    assert KEY not in request.headers['x-opencode-session']


def test_one_shot_calls_still_send_a_routing_header():
    session = call(None).headers['x-opencode-session']
    assert re.fullmatch(r'[0-9a-f-]{36}', session)


def test_other_providers_never_receive_the_routing_header():
    request = call('conversation-abc123', {'provider': 'deepseek', 'baseUrl': 'https://api.deepseek.com',
                                           'protocol': 'chat', 'model': 'deepseek-flash'})
    assert 'x-opencode-session' not in request.headers
    assert request.headers['user-agent'] == 'Geometry/1.0'


@pytest.mark.parametrize('session_id', ['bad id!!', 'x' * 101])
def test_malformed_session_ids_are_rejected(session_id):
    with pytest.raises(ValueError):
        ai.ChatRequest(messages=[ai.Message(role='user', content='q')], sessionId=session_id)


def test_chat_route_forwards_the_session_id(monkeypatch):
    captured = {}

    async def complete(messages, **kwargs):
        captured.update(kwargs)
        return {'content': json.dumps({'mode': 'conversation', 'content': 'ok'}), 'finishReason': 'stop'}

    monkeypatch.setattr(ai, 'complete', complete)
    response = TestClient(app).post('/api/ai/chat', headers={'X-AI-Api-Key': KEY}, json={
        'messages': [{'role': 'user', 'content': 'hello'}], 'keyMode': 'personal',
        'provider': OPENCODE, 'sessionId': 'conversation-abc123'})
    assert response.status_code == 200, response.text
    assert captured['session_id'] == 'conversation-abc123'
