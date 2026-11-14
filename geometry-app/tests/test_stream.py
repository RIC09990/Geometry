"""Streaming tutor turns: envelope decoding, SSE parsing, usage, and the endpoint."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from server import ai
from server.ai import ContentStream
from server.ai_providers import ProviderOptions, normalize_usage, resolve_provider, stream_chat_events
from server.main import app

KEY = 'isolated-stream-key'
CHAT = {'provider': 'compatible', 'baseUrl': 'https://relay.example.com/v1',
        'protocol': 'chat', 'model': 'deepseek-v4.1-flash'}


@pytest.fixture(autouse=True)
def isolated_rate_limit(monkeypatch):
    monkeypatch.setattr(ai, 'recent_requests', ai.deque())


class AsyncBody(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


def transport(events):
    body = [('data: ' + json.dumps(event) + '\n\n').encode() for event in events]
    return httpx.MockTransport(lambda request: httpx.Response(200, stream=AsyncBody(body)))


def test_content_decoder_survives_fragmentation_and_escapes():
    raw = '{"mode":"solution","content":"甲\\n乙 \\u4e2d\\ud83d\\ude00 尾","searchQuery":null}'
    decoder = ContentStream()
    sent = ''
    for start in range(0, len(raw), 3):
        sent += decoder.feed(raw[start:start + 3])
    assert sent == '甲\n乙 中😀 尾'


def test_content_decoder_stops_at_the_closing_quote_and_accepts_spacing():
    decoder = ContentStream()
    assert decoder.feed('{"content" : "a\\"b", "grading": null}') == 'a"b'


def test_content_decoder_ignores_replies_without_the_envelope():
    decoder = ContentStream()
    assert decoder.feed('plain greeting text') == ''


def test_stream_events_expose_reasoning_text_finish_and_usage():
    lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"先想"}}]}',
        'data: {"choices":[{"delta":{"content":"{\\"mode\\""}}]}',
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":1200,"prompt_cache_hit_tokens":764,"completion_tokens":45}}',
        'data: [DONE]',
        'data: not json',
    ]
    assert list(stream_chat_events(lines)) == [
        ('reasoning', '先想'), ('text', '{"mode"'), ('finish', 'stop'),
        ('usage', {'prompt_tokens': 1200, 'prompt_cache_hit_tokens': 764, 'completion_tokens': 45})]


def test_usage_normalization_reads_deepseek_and_openai_cache_fields():
    assert normalize_usage({'prompt_tokens': 1200, 'prompt_cache_hit_tokens': 764,
                            'completion_tokens': 45,
                            'completion_tokens_details': {'reasoning_tokens': 12}}) == {
        'promptTokens': 1200, 'cachedTokens': 764, 'completionTokens': 45, 'reasoningTokens': 12}
    assert normalize_usage({'prompt_tokens': 900, 'prompt_tokens_details': {'cached_tokens': 512},
                            'completion_tokens': 100}) == {
        'promptTokens': 900, 'cachedTokens': 512, 'completionTokens': 100}
    assert normalize_usage(None) == {}


def test_complete_stream_emits_increments_and_reports_metrics():
    events = [
        {'choices': [{'delta': {'reasoning_content': '先想'}}]},
        {'choices': [{'delta': {'content': '{"mode":"solution","content":"答'}}]},
        {'choices': [{'delta': {'content': '案"}'}}]},
        {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
        {'choices': [], 'usage': {'prompt_tokens': 1200, 'prompt_cache_hit_tokens': 764,
                                  'completion_tokens': 45}},
    ]
    emitted = []

    async def emit(event):
        emitted.append(event)

    async def run():
        return await ai.complete_stream([ai.Message(role='user', content='q')], api_key=KEY,
            provider=resolve_provider(ProviderOptions(**CHAT)), transport=transport(events),
            structured=True, emit=emit)

    reply = asyncio.run(run())
    assert reply['content'] == '{"mode":"solution","content":"答案"}'
    assert reply['metrics']['promptTokens'] == 1200
    assert reply['metrics']['cachedTokens'] == 764
    assert reply['metrics']['tokensPerSecond'] > 0
    assert [event['type'] for event in emitted] == ['reasoning', 'text', 'text']
    assert ''.join(event['text'] for event in emitted if event['type'] == 'text') == '答案'


def test_search_pass_signals_status_then_resets_before_redrawing(monkeypatch):
    emitted, calls = [], []

    async def stream(messages, **kwargs):
        calls.append(messages)
        await kwargs['emit']({'type': 'text', 'text': '旧答复'})
        payload = {'mode': 'conversation', 'content': '新答复'}
        if len(calls) == 1:
            payload['searchQuery'] = '北京天气'
        return {'content': json.dumps(payload), 'finishReason': 'stop', 'provider': 'p', 'model': 'm', 'metrics': {}}

    async def search(query, *, api_key, provider):
        return [{'title': 'Forecast', 'url': 'https://example.com/w', 'content': '晴'}]

    async def unexpected(*args, **kwargs):
        raise AssertionError('the verification pass must not run for a normal answer')

    async def emit(event):
        emitted.append(event['type'] if event['type'] != 'status' else 'status:' + event['code'])

    monkeypatch.setattr(ai, 'complete_stream', stream)
    monkeypatch.setattr(ai, 'search_web', search)
    monkeypatch.setattr(ai, 'complete', unexpected)
    request = ai.ChatRequest(messages=[{'role': 'user', 'content': '北京天气'}],
                             keyMode='personal', provider=CHAT)
    reply = asyncio.run(ai.dispatch(request, KEY, 'system', structured=True, verify_homework=True, emit=emit))
    assert 'status:searching' in emitted
    assert 'reset' in emitted
    assert reply['sources'] == [{'title': 'Forecast', 'url': 'https://example.com/w'}]


def test_stream_endpoint_emits_events_and_a_final_reply(monkeypatch):
    async def dispatch(request, key, system, **kwargs):
        emit = kwargs['emit']
        await emit({'type': 'reasoning', 'text': '先想'})
        await emit({'type': 'text', 'text': '答案'})
        return {'content': json.dumps({'mode': 'conversation', 'content': '答案'}), 'finishReason': 'stop',
                'provider': 'compatible', 'model': 'm', 'sources': [], 'searchStatus': None,
                'metrics': {'promptTokens': 10, 'cachedTokens': 5, 'completionTokens': 2}}

    monkeypatch.setattr(ai, 'dispatch', dispatch)
    with TestClient(app).stream('POST', '/api/ai/chat/stream', headers={'X-AI-Api-Key': KEY},
            json={'messages': [{'role': 'user', 'content': 'hi'}], 'keyMode': 'personal', 'provider': CHAT}) as response:
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')
        body = ''.join(response.iter_text())
    assert 'event: reasoning' in body and 'event: text' in body and 'event: done' in body
    done = next(frame for frame in body.split('\n\n') if frame.startswith('event: done'))
    payload = json.loads(done.split('data: ', 1)[1])
    assert payload['content'] == '答案'
    assert payload['metrics']['promptTokens'] == 10


def test_stream_endpoint_reports_a_failure_as_an_error_event(monkeypatch):
    async def dispatch(request, key, system, **kwargs):
        raise ai.HTTPException(429, 'AI 当前请求较多，请稍后重试。')

    monkeypatch.setattr(ai, 'dispatch', dispatch)
    with TestClient(app).stream('POST', '/api/ai/chat/stream', headers={'X-AI-Api-Key': KEY},
            json={'messages': [{'role': 'user', 'content': 'hi'}], 'keyMode': 'personal', 'provider': CHAT}) as response:
        body = ''.join(response.iter_text())
    assert 'event: error' in body and '请稍后重试' in body
