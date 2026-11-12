"""Exercise app routing and context boundaries without assuming an LLM is infallible."""
import json

import pytest
from fastapi.testclient import TestClient

from server import ai
from server.ai_providers import ProviderOptions, request_body
from server.main import app


KEY = 'isolated-chat-routing-key'
OPTIONS = ProviderOptions(
    provider='deepseek', baseUrl='https://api.deepseek.com',
    protocol='chat', model='user-selected-model', reasoningEffort='max',
)


@pytest.fixture(autouse=True)
def isolated_rate_limit(monkeypatch):
    monkeypatch.setattr(ai, 'recent_requests', ai.deque())


def post(messages, **extra):
    response = TestClient(app).post('/api/ai/chat',
        headers={'X-AI-Api-Key': KEY},
        json={'messages': messages, 'keyMode': 'personal',
              'provider': OPTIONS.model_dump(), **extra})
    assert response.status_code == 200, response.text
    assert KEY not in response.text
    return response.json()


def completion(content, *, mode='conversation', **extra):
    return {'content': json.dumps({'mode': mode, 'content': content,
                                  'grading': None, **extra}), 'finishReason': 'stop'}


def assert_request_configuration(kwargs):
    assert kwargs['api_key'] == KEY
    assert kwargs['provider'] == OPTIONS
    assert kwargs['structured'] is True
    assert len(kwargs['system']) < 1400


@pytest.mark.parametrize(('question', 'mode', 'answer'), [
    ('解释一下为什么海水是咸的。', 'conversation', '海水中的盐来自岩石风化等过程。'),
    ('已知三角形两角为50度和60度，求第三角。', 'solution', '第三角为70度。'),
    ('我写成2∠BOC=∠BAC+180°，与题目给的式子相同吗？', 'homework',
     '两边同除以2，两式等价。这一变形成立。'),
])
def test_normal_questions_solutions_and_feedback_use_one_unbiased_turn(
        question, mode, answer, monkeypatch):
    calls = []

    async def complete(messages, **kwargs):
        calls.append(messages)
        assert_request_configuration(kwargs)
        assert messages[-1].role == 'user' and messages[-1].content == question
        assert [m.role for m in messages] == ['user', 'assistant', 'user']
        return completion(answer, mode=mode)

    async def search(*args, **kwargs):
        pytest.fail('Stable questions must not search merely because the app is a tutor')

    monkeypatch.setattr(ai, 'complete', complete)
    monkeypatch.setattr(ai, 'search_web', search)
    reply = post([
        {'role': 'user', 'content': '刚才那道题帮我看看。'},
        {'role': 'assistant', 'content': '上一次的解题回复。',
         'grading': {'score': 0}, 'reportPdf': {'dataUrl': 'not-context'}},
        {'role': 'user', 'content': question},
    ])
    assert len(calls) == 1
    assert reply['content'] == answer
    assert reply['grading'] is None and 'reportPdf' not in reply
    assert reply['sources'] == []


def test_weather_without_a_city_can_ask_a_normal_clarifying_question(monkeypatch):
    calls = []

    async def complete(messages, **kwargs):
        calls.append(messages)
        assert messages[-1].content == '今天天气怎么样？'
        return completion('你想查哪个城市的天气？')

    async def search(*args, **kwargs):
        pytest.fail('The app must not invent a location or force a weather query')

    monkeypatch.setattr(ai, 'complete', complete)
    monkeypatch.setattr(ai, 'search_web', search)
    reply = post([{'role': 'user', 'content': '今天天气怎么样？'}])
    assert len(calls) == 1
    assert reply['content'] == '你想查哪个城市的天气？'
    assert reply['grading'] is None and reply['sources'] == []


@pytest.mark.parametrize(('question', 'query', 'fact'), [
    ('北京明天会下雨吗？', '北京 明天 天气预报', '预报降水概率20%。'),
    ('请查最新的火星探测任务进展。', '最新 火星探测 任务进展', '任务已完成新的观测。'),
])
def test_model_requested_current_information_searches_without_checkbox(
        question, query, fact, monkeypatch):
    calls, searches = [], []

    async def complete(messages, **kwargs):
        assert_request_configuration(kwargs)
        assert messages[-1].content == question
        calls.append(messages)
        if len(calls) == 1:
            return completion('', searchQuery=query)
        assert len(calls) == 2
        assert any(fact in m.content for m in messages)
        return completion(fact + ' [来源](https://example.com/current)')

    async def search(search_query, *, api_key, provider):
        searches.append(search_query)
        assert api_key == KEY and provider == OPTIONS
        return [{'title': 'Current source', 'url': 'https://example.com/current',
                 'content': fact}]

    monkeypatch.setattr(ai, 'complete', complete)
    monkeypatch.setattr(ai, 'search_web', search)
    reply = post([{'role': 'user', 'content': question}])
    assert len(calls) == 2 and searches == [query]
    assert fact in reply['content'] and reply['searchStatus'] == 'found'
    assert reply['sources'] == [{'title': 'Current source', 'url': 'https://example.com/current'}]
    assert reply['grading'] is None and 'reportPdf' not in reply


@pytest.mark.parametrize('failure', ['unavailable', 'empty'])
def test_failed_automatic_search_cannot_publish_guessed_weather_or_scores(failure, monkeypatch):
    calls = []
    guessed_answer = '北京今天99度，作业得分100/100。'

    async def complete(messages, **kwargs):
        calls.append(messages)
        assert len(calls) == 1
        return completion(guessed_answer, mode='homework', searchQuery='北京 今日天气',
            grading={'score': 100, 'maximum': 100, 'items': []})

    async def search(*args, **kwargs):
        if failure == 'unavailable':
            raise ai.HTTPException(502, 'private upstream detail ' + KEY)
        return []

    monkeypatch.setattr(ai, 'complete', complete)
    monkeypatch.setattr(ai, 'search_web', search)
    reply = post([{'role': 'user', 'content': '北京今天天气怎么样？'}])
    assert guessed_answer not in reply['content']
    assert '100/100' not in reply['content'] and 'private upstream' not in reply['content']
    assert reply['content'].strip()
    assert reply['grading'] is None and 'reportPdf' not in reply
    assert reply['sources'] == [] and reply['searchStatus'] == failure


def test_repeated_search_request_stops_instead_of_looping(monkeypatch):
    calls, searches = [], []

    async def complete(messages, **kwargs):
        calls.append(messages)
        return completion('', searchQuery='北京天气')

    async def search(*args, **kwargs):
        searches.append(args)
        return [{'title': 'Weather', 'url': 'https://example.com/weather', 'content': 'Forecast'}]

    monkeypatch.setattr(ai, 'complete', complete)
    monkeypatch.setattr(ai, 'search_web', search)
    reply = post([{'role': 'user', 'content': '北京天气'}])
    assert len(calls) == 2 and len(searches) == 1
    assert reply['content'].strip() and reply['grading'] is None
    assert reply['sources'] == [] and 'reportPdf' not in reply


def test_explicit_search_uses_the_question_and_bounded_nonduplicate_evidence(monkeypatch):
    question = '请搜索当前火星探测进展。'
    repeated = 'REPEATED-SUMMARY:' + 'a' * 12000
    sources = [
        {'title': f'Source {i}', 'url': f'https://example.com/{i}',
         'content': repeated if i < 3 else str(i) * 12000}
        for i in range(8)
    ]
    calls, queries = [], []

    async def search(query, *, api_key, provider):
        queries.append(query)
        assert api_key == KEY and provider == OPTIONS
        return sources

    async def complete(messages, **kwargs):
        calls.append(messages)
        assert_request_configuration(kwargs)
        assert messages[-1].content == question
        evidence = '\n'.join(m.content for m in messages[:-1])
        assert len(evidence) < 8000
        assert evidence.count('REPEATED-SUMMARY:') == 1
        assert 'https://example.com/0' in evidence
        assert 'https://example.com/7' not in evidence
        return completion('检索结果已归纳。')

    monkeypatch.setattr(ai, 'complete', complete)
    monkeypatch.setattr(ai, 'search_web', search)
    reply = post([{'role': 'user', 'content': question}], webSearch=True)
    assert queries == [question] and len(calls) == 1
    assert reply['searchStatus'] == 'found' and reply['grading'] is None


def test_greeting_recovers_from_conflicting_json_without_searching(monkeypatch):
    calls=[]

    async def complete(messages, **kwargs):
        calls.append(kwargs)
        assert kwargs['api_key']==KEY and kwargs['provider']==OPTIONS
        assert not kwargs['structured'] and 'JSON' not in kwargs['system']
        assert messages[-1].content=='hi hi!'
        if len(calls)==1:
            return {'content':'{"mode":"conversation","content":"Hello"}'
                              '{"mode":"conversation","content":"Hi"}','finishReason':'stop'}
        assert len(calls)==2
        return completion('Hi! How can I help?',searchQuery='hi')

    async def search(*args, **kwargs):
        pytest.fail('A standalone greeting does not use web search')

    monkeypatch.setattr(ai,'complete',complete)
    monkeypatch.setattr(ai,'search_web',search)
    reply=post([{'role':'user','content':'hi hi!'}],webSearch=True)
    assert len(calls)==2
    assert reply['content']=='Hi! How can I help?'
    assert reply['sources']==[] and reply['searchStatus'] is None
    assert reply['mode']=='conversation' and not reply['pdfEligible']


@pytest.mark.parametrize('recover',[True,False])
def test_bad_reply_after_search_is_retried_without_repeating_the_search(monkeypatch,recover):
    calls,queries=[],[]
    question='请查北京今天的天气。'
    evidence={'title':'Forecast','url':'https://example.com/beijing','content':'北京天气资料'}
    malformed='{"id":"message","mode":"conversation","content":"unfinished'

    async def search(query, **kwargs):
        queries.append(query)
        return [evidence]

    async def complete(messages, **kwargs):
        calls.append(messages)
        if len(calls)==1:
            return completion('',searchQuery='北京 今日天气预报')
        assert len(calls)<=3
        assert messages[-1].content==question
        assert any(evidence['url'] in message.content for message in messages)
        if len(calls)==3 and recover:
            return completion('预报为晴。')
        return {'content':malformed,'finishReason':'stop'}

    monkeypatch.setattr(ai,'complete',complete)
    monkeypatch.setattr(ai,'search_web',search)
    response=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':KEY},json={
        'messages':[{'role':'user','content':question}], 'keyMode':'personal',
        'provider':OPTIONS.model_dump(),
    })
    assert len(calls)==3 and queries==['北京 今日天气预报']
    if recover:
        assert response.status_code==200
        assert response.json()['content']=='预报为晴。'
        assert response.json()['sources']==[{'title':evidence['title'],'url':evidence['url']}]
    else:
        assert response.status_code==502
        assert set(response.json())=={'detail'}
        assert evidence['url'] not in response.text and 'unfinished' not in response.text


@pytest.mark.parametrize('structured', [False, True])
def test_provider_adapter_does_not_force_the_selected_models_thinking_off(structured):
    _, body = request_body([ai.Message(role='user', content='Check this calculation.')],
                           OPTIONS, 'Answer the user.', structured)
    assert body['model'] == OPTIONS.model
    assert body['thinking']=={'type':'enabled'}
    assert body['reasoning_effort']=='max'
