"""Concrete routing edges: incomplete scores and one refined search query."""
import asyncio
import json

import pytest

from server import ai
from server.ai_providers import ProviderOptions


OPTIONS = ProviderOptions(provider='deepseek', baseUrl='https://api.deepseek.com',
                          protocol='chat', model='selected-model', reasoningEffort='max')
KEY = 'isolated-edge-test-key'


@pytest.fixture(autouse=True)
def isolated_rate_limit(monkeypatch):
    monkeypatch.setattr(ai, 'recent_requests', ai.deque())


def request(*, search=False):
    return ai.ChatRequest(messages=[ai.Message(role='user', content='original question')],
                          keyMode='personal', provider=OPTIONS, webSearch=search)


def completion(content='', **fields):
    return {'content': json.dumps({'mode': 'conversation', 'content': content, **fields}),
            'finishReason': 'stop'}


def grade(*, finish='stop'):
    return {'finishReason': finish, 'content': json.dumps({
        'mode': 'homework', 'content': 'The first answer is correct.',
        'grading': {'score': 100, 'maximum': 100, 'items': [
            {'label': '1', 'verdict': 'correct', 'studentWork': '1+1=2'}]},
    })}


def source(text):
    return [{'title': text, 'url': 'https://example.com/' + text, 'content': text}]


def test_closed_json_from_a_truncated_score_gets_exactly_one_retry(monkeypatch):
    calls = []

    async def complete(messages, **kwargs):
        calls.append((messages, kwargs))
        assert kwargs['provider'] == OPTIONS and kwargs['api_key'] == KEY
        if len(calls) == 1:
            assert messages[-1].content == 'original question'
            return grade(finish='length')
        assert len(calls) == 2
        assert messages[-2].content == 'original question'
        assert '独立重新核对原始作答' in messages[-1].content
        result = grade()
        data = json.loads(result['content'])
        # The untruncated pass can include items missing from the first output.
        data['grading']['score'] = 50
        data['grading']['items'].append({'label': '2', 'verdict': 'incorrect', 'studentWork': '1+1=3'})
        data['content'] = 'The first answer is correct; the second needs correction.'
        return {**result, 'content': json.dumps(data)}

    monkeypatch.setattr(ai, 'complete', complete)
    reply = asyncio.run(ai.dispatch(request(), KEY, structured=True, verify_homework=True))
    parsed = ai.parse_tutor_reply(reply['content'])
    assert len(calls) == 2
    assert reply['finishReason'] == 'stop'
    assert parsed.grading.score == 50 and len(parsed.grading.items) == 2


@pytest.mark.parametrize('failure', ['truncated', 'upstream'])
def test_failed_retry_never_publishes_an_initial_truncated_score(monkeypatch, failure):
    calls = []

    async def complete(messages, **kwargs):
        calls.append(messages)
        assert len(calls) <= 2
        if len(calls) == 2 and failure == 'upstream':
            raise ai.HTTPException(502, 'private upstream detail')
        return grade(finish='length')

    monkeypatch.setattr(ai, 'complete', complete)
    reply = asyncio.run(ai.dispatch(request(), KEY, structured=True, verify_homework=True))
    parsed = ai.parse_tutor_reply(reply['content'])
    assert len(calls) == 2
    assert parsed.grading is None
    assert '100/100' not in parsed.content and 'private upstream' not in parsed.content
    assert '独立复核暂未完成' in parsed.content


@pytest.mark.parametrize('initial_result', ['found', 'empty', 'unavailable'])
def test_explicit_search_can_be_refined_once_and_uses_only_new_evidence(monkeypatch, initial_result):
    calls, queries = [], []

    async def search(query, **kwargs):
        queries.append(query)
        assert kwargs['provider'] == OPTIONS and kwargs['api_key'] == KEY
        if len(queries) == 1:
            if initial_result == 'unavailable':raise ai.HTTPException(502, 'Unavailable')
            return source('broad-evidence') if initial_result == 'found' else []
        assert len(queries) == 2 and query == 'refined query'
        return source('specific-evidence')

    async def complete(messages, **kwargs):
        calls.append(messages)
        assert messages[-1].content.startswith('original question')
        if len(calls) == 1:return completion(searchQuery='refined query')
        assert len(calls) == 2
        evidence = '\n'.join(message.content for message in messages)
        assert 'specific-evidence' in evidence and 'broad-evidence' not in evidence
        assert '本轮未获取到实时检索资料' not in kwargs['system']
        return completion('Answer using the specific evidence.')

    monkeypatch.setattr(ai, 'search_web', search)
    monkeypatch.setattr(ai, 'complete', complete)
    reply = asyncio.run(ai.dispatch(request(search=True), KEY, structured=True))
    assert queries == ['original question', 'refined query'] and len(calls) == 2
    assert reply['searchStatus'] == 'found'
    assert reply['sources'] == [{'title': 'specific-evidence', 'url': 'https://example.com/specific-evidence'}]


def test_same_query_does_not_repeat_checkbox_search(monkeypatch):
    calls, queries = [], []

    async def search(query, **kwargs):
        queries.append(query)
        return source('evidence')

    async def complete(messages, **kwargs):
        calls.append(messages)
        return completion(searchQuery=' original question ') if len(calls) == 1 else completion('Answer.')

    monkeypatch.setattr(ai, 'search_web', search)
    monkeypatch.setattr(ai, 'complete', complete)
    reply = asyncio.run(ai.dispatch(request(search=True), KEY, structured=True))
    assert queries == ['original question'] and len(calls) == 2
    assert reply['searchStatus'] == 'found'


def test_second_refinement_is_stopped_without_starting_a_search_loop(monkeypatch):
    calls, queries = [], []

    async def search(query, **kwargs):
        queries.append(query)
        return source('evidence')

    async def complete(messages, **kwargs):
        calls.append(messages)
        assert len(calls) <= 2
        return completion(searchQuery='refinement ' + str(len(calls)))

    monkeypatch.setattr(ai, 'search_web', search)
    monkeypatch.setattr(ai, 'complete', complete)
    reply = asyncio.run(ai.dispatch(request(search=True), KEY, structured=True))
    assert queries == ['original question', 'refinement 1'] and len(calls) == 2
    assert reply['sources'] == [] and reply['searchStatus'] == 'unavailable'
    assert ai.parse_tutor_reply(reply['content']).content
