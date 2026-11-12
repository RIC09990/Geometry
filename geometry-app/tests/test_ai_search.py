import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from server import ai
from server.ai_providers import ProviderOptions
from server.main import app


OPTIONS=ProviderOptions(provider='anthropic',baseUrl='https://api.anthropic.com/v1',protocol='anthropic',model='test-model')
KEY='isolated-anthropic-search-key'


def search_result(url):
    return {'type':'web_search_tool_result','tool_use_id':'srvtoolu_test','content':[
        {'type':'web_search_result','url':url,'title':'Geometry reference','encrypted_content':'opaque-result-state'}]}


def paused(content=None):
    return {'stop_reason':'pause_turn','content':content or [
        {'type':'text','text':'Checking references.'},
        {'type':'server_tool_use','id':'srvtoolu_test','name':'web_search','input':{'query':'triangle geometry'}}]}


def tool_error(code):
    return {'stop_reason':'end_turn','content':[
        {'type':'text','text':'Upstream failure '+KEY},
        {'type':'web_search_tool_result','tool_use_id':'srvtoolu_test','content':{
            'type':'web_search_tool_result_error','error_code':code,'message':KEY,'url':'https://example.com/'+KEY}}]}


def test_anthropic_search_preserves_every_paused_response_and_earlier_sources():
    first=paused([search_result('https://example.com/first')])
    second=paused()
    final={'stop_reason':'end_turn','content':[search_result('https://example.com/last'),{'type':'text','text':'Completed reference summary.'}]}
    pages=[first,second,final];bodies=[]
    def respond(request):
        assert str(request.url)=='https://api.anthropic.com/v1/messages'
        assert request.headers['x-api-key']==KEY
        body=json.loads(request.content);bodies.append(body)
        assert body['model']==OPTIONS.model
        assert body['tools']==[{'type':'web_search_20250305','name':'web_search','max_uses':2}]
        assert body['messages']==[{'role':'user','content':'triangle'},*[
            {'role':'assistant','content':page['content']} for page in pages[:len(bodies)-1]]]
        return httpx.Response(200,json=pages[len(bodies)-1])
    sources=asyncio.run(ai.search_web('triangle',api_key=KEY,provider=OPTIONS,transport=httpx.MockTransport(respond)))
    assert len(bodies)==3
    assert {s['url'] for s in sources}=={'https://example.com/first','https://example.com/last'}
    assert all('Completed reference summary.' in source['content'] for source in sources)
    assert KEY not in json.dumps(sources) and 'opaque-result-state' not in json.dumps(sources)


@pytest.mark.parametrize('code',['unavailable','too_many_requests','invalid_tool_input','max_uses_exceeded'])
def test_anthropic_http_200_search_tool_errors_are_unavailable_without_raw_error_details(code):
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,json=tool_error(code))
    with pytest.raises(ai.HTTPException) as error:
        asyncio.run(ai.search_web('triangle',api_key=KEY,provider=OPTIONS,transport=httpx.MockTransport(respond)))
    assert error.value.status_code==502
    assert KEY not in error.value.detail and code not in error.value.detail
    assert len(calls)==1


def test_anthropic_genuine_empty_search_results_remain_empty():
    data={'stop_reason':'end_turn','content':[{'type':'web_search_tool_result','tool_use_id':'srvtoolu_test','content':[]}]}
    sources=asyncio.run(ai.search_web('triangle',api_key=KEY,provider=OPTIONS,transport=httpx.MockTransport(lambda _:httpx.Response(200,json=data))))
    assert sources==[]


@pytest.mark.parametrize('failure',['tool_error','pause_limit','continuation_error'])
def test_anthropic_search_failure_still_allows_chat_and_never_returns_error_content(failure,monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    original_search=ai.search_web;calls=[]
    def respond(request):
        calls.append(request)
        if failure=='tool_error':return httpx.Response(200,json=tool_error('unavailable'))
        if failure=='continuation_error' and len(calls)>1:return httpx.Response(401,text=KEY)
        return httpx.Response(200,json=paused([search_result('https://example.com/partial'),{'type':'text','text':'Partial summary.'}]))
    async def search(query,*,api_key,provider):
        return await original_search(query,api_key=api_key,provider=provider,transport=httpx.MockTransport(respond))
    async def complete(messages,**kwargs):
        assert not any('Partial summary.' in m.content or KEY in m.content for m in messages)
        return {'content':'{"content":"chat remains available"}'}
    monkeypatch.setattr(ai,'search_web',search);monkeypatch.setattr(ai,'complete',complete)
    response=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':KEY},json={
        'provider':OPTIONS.model_dump(),'keyMode':'personal','webSearch':True,'messages':[{'role':'user','content':'triangle'}]})
    assert response.status_code==200,response.text
    assert response.json()['searchStatus']=='unavailable' and response.json()['sources']==[]
    assert response.json()['content']=='chat remains available' and KEY not in response.text
    assert len(calls)=={'tool_error':1,'pause_limit':3,'continuation_error':2}[failure]


@pytest.mark.parametrize('data',[
    {'type':'error','error':{'message':KEY}},
    {'content':[KEY]},
    {'stop_reason':'pause_turn','content':[]},
    [KEY],
])
def test_malformed_search_response_is_handled_without_exposing_body(data):
    with pytest.raises(ai.HTTPException) as error:
        asyncio.run(ai.search_web('triangle',api_key=KEY,provider=OPTIONS,transport=httpx.MockTransport(lambda _:httpx.Response(200,json=data))))
    assert error.value.status_code==502 and KEY not in error.value.detail


def test_malformed_completion_blocks_are_handled_without_exposing_body():
    with pytest.raises(ai.HTTPException) as error:
        asyncio.run(ai.complete([ai.Message(role='user',content='triangle')],api_key=KEY,provider=OPTIONS,
            transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'content':[KEY]}))))
    assert error.value.status_code==502 and KEY not in error.value.detail
