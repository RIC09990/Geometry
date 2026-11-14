import pytest
from fastapi.testclient import TestClient

from server import topics
from server.ai_providers import PRESETS
from server.main import app


class Parsed:
    def model_dump(self):
        return {'problem': None, 'recognizedText': '已识别', 'uncertainties': [], 'unsupported': [],
                'encodingIssues': [], 'draft': None}


def post(**extra):
    body = {'description': '等腰三角形底角相等', 'keyMode': 'personal', 'provider': PRESETS['deepseek'], **extra}
    return TestClient(app).post('/api/ai/import-topic/stream', headers={'X-AI-Api-Key': 'import-stream-key'}, json=body)


def test_streaming_import_emits_reasoning_then_the_payload(monkeypatch):
    async def dispatch(request, key, structured=False, emit=None, **kwargs):
        await emit({'type': 'reasoning', 'text': '读题中'})
        return {'content': '{}', 'finishReason': 'stop', 'provider': 'DeepSeek'}
    monkeypatch.setattr(topics, 'dispatch', dispatch)
    monkeypatch.setattr(topics, 'decode_import', lambda *args, **kwargs: Parsed())
    response = post()
    assert response.status_code == 200, response.text
    assert 'event: reasoning' in response.text and '读题中' in response.text
    assert 'event: done' in response.text and '已识别' in response.text
    assert 'requiresConfirmation' in response.text


def test_streaming_import_reports_failures_as_an_error_event(monkeypatch):
    async def dispatch(request, key, structured=False, emit=None, **kwargs):
        raise topics.HTTPException(502, '识别失败')
    monkeypatch.setattr(topics, 'dispatch', dispatch)
    response = post()
    assert response.status_code == 200
    assert 'event: error' in response.text and '识别失败' in response.text

def test_recognition_caps_thinking_effort(monkeypatch):
    seen = {}

    async def dispatch(request, key, structured=False, emit=None, **kwargs):
        seen['effort'] = request.provider.reasoningEffort
        seen['protocol'] = request.provider.protocol
        return {'content': '{}', 'finishReason': 'stop'}
    monkeypatch.setattr(topics, 'dispatch', dispatch)
    monkeypatch.setattr(topics, 'decode_import', lambda *args, **kwargs: Parsed())
    assert post(provider={**PRESETS['deepseek'], 'reasoningEffort': 'max'}).status_code == 200
    assert seen == {'effort': 'low', 'protocol': 'chat'}

