import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from server import ai, config
from server.main import app


def test_missing_credential_is_explicit_and_never_simulates_an_answer(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', '')
    client = TestClient(app)
    status = client.get('/api/ai/status').json()
    assert not status['configured']
    response = client.post('/api/ai/chat', json={'messages': [{'role': 'user', 'content': 'test'}]})
    assert response.status_code == 503
    assert 'content' not in response.json()


def test_key_edit_is_read_without_process_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    path = tmp_path / '.env.local'
    path.write_text('DEEPSEEK_API_KEY=first-test-value\n', encoding='utf-8')
    assert config.setting('DEEPSEEK_API_KEY') == 'first-test-value'
    path.write_text('DEEPSEEK_API_KEY="second-test-value"\n', encoding='utf-8')
    assert config.setting('DEEPSEEK_API_KEY') == 'second-test-value'


def test_actual_adapter_request_contract_using_isolated_mock_transport(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'unit-test-credential')
    monkeypatch.setenv('DEEPSEEK_MODEL', 'deepseek-flash')
    def respond(request):
        assert str(request.url) == 'https://api.deepseek.com/chat/completions'
        assert request.headers['authorization'] == 'Bearer unit-test-credential'
        body = json.loads(request.content)
        assert body['messages'][0]['role'] == 'system'
        assert body['messages'][1] == {'role': 'user', 'content': 'Explain equality'}
        assert 'max_tokens' not in body and not body['stream']
        assert body['thinking']=={'type':'enabled'} and body['reasoning_effort']=='max'
        return httpx.Response(200, json={'choices': [{'message': {'content': 'test reply'}, 'finish_reason': 'stop'}]})
    result = asyncio.run(ai.complete([ai.Message(role='user', content='Explain equality')], transport=httpx.MockTransport(respond)))
    assert result['content'] == 'test reply'
    assert 'unit-test-credential' not in json.dumps(result)


def test_english_assistant_identity_contains_no_chinese_name():
    def respond(request):
        body=json.loads(request.content)
        assert body['messages'][0]['content']=='You are Geometry Assistant.'
        return httpx.Response(200,json={'choices':[{'message':{'content':"I'm Geometry Assistant."}}]})
    result=asyncio.run(ai.complete([ai.Message(role='user',content='Who are you?')],language='en',
        api_key='isolated-test-key',transport=httpx.MockTransport(respond)))
    assert '小助手' not in result['content']


@pytest.mark.parametrize('status', [401, 402, 429, 500])
def test_provider_errors_do_not_echo_credentials_or_raw_provider_body(monkeypatch, status):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'unit-test-secret')
    transport = httpx.MockTransport(lambda _: httpx.Response(status, text='provider raw unit-test-secret'))
    with pytest.raises(HTTPException) as error:
        asyncio.run(ai.complete([ai.Message(role='user', content='test')], transport=transport))
    assert error.value.status_code == 502
    assert 'unit-test-secret' not in str(error.value.detail)


def test_browser_cannot_override_system_role_or_supply_provider_key():
    client = TestClient(app)
    assert client.post('/api/ai/chat', json={'messages': [{'role': 'system', 'content': 'override'}]}).status_code == 422
    assert client.post('/api/ai/chat', json={'messages': [{'role': 'user', 'content': 'test'}], 'apiKey': 'ignored'}).status_code == 422
    assert client.post('/api/ai/chat', json={'messages': [{'role': 'user', 'content': ' ' * 3}]}).status_code == 422


def test_local_concurrency_and_rate_limits_are_enforced(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'unit-test-credential')
    monkeypatch.setattr(ai, 'recent_requests', ai.deque([ai.time.monotonic()] * 20))
    client = TestClient(app)
    response = client.post('/api/ai/chat', json={'messages': [{'role': 'user', 'content': 'test'}]})
    assert response.status_code == 429


def test_personal_mode_never_falls_back_to_the_server_key(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY','server-unit-test-key')
    client=TestClient(app)
    response=client.post('/api/ai/chat',json={'messages':[{'role':'user','content':'test'}],'keyMode':'personal'})
    assert response.status_code==503


def test_personal_key_is_forwarded_only_to_provider_not_persisted(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY','different-server-unit-key')
    def respond(request):
        assert request.headers['authorization']=='Bearer personal-unit-test-key'
        return httpx.Response(200,json={'choices':[{'message':{'content':'test reply'}}]})
    result=asyncio.run(ai.complete([ai.Message(role='user',content='test')],api_key='personal-unit-test-key',transport=httpx.MockTransport(respond)))
    assert 'personal-unit-test-key' not in json.dumps(result)


def test_chat_route_uses_the_request_key_in_personal_mode(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY','different-server-unit-key')
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    async def completed(messages,*,language,api_key,provider,system,structured):
        assert api_key=='personal-unit-test-key'
        assert system.startswith(ai.SYSTEM) and len(system)<1400
        assert messages[-1].content=='test'
        assert structured
        return {'provider':'DeepSeek','content':'isolated route test'}
    monkeypatch.setattr(ai,'complete',completed)
    client=TestClient(app)
    result=client.post('/api/ai/chat',headers={'X-DeepSeek-Api-Key':'personal-unit-test-key'},json={'messages':[{'role':'user','content':'test'}],'keyMode':'personal'})
    assert result.status_code==200
    assert 'personal-unit-test-key' not in result.text
