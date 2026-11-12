import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from server import ai
from server.ai_providers import PRESETS,ProviderOptions
from server.main import app


def options(name):
    return ProviderOptions(provider=name,baseUrl=PRESETS[name]['baseUrl'],protocol=PRESETS[name]['protocol'])


@pytest.mark.parametrize('name',['deepseek','openai','anthropic','gemini'])
def test_model_discovery_uses_only_selected_official_host_without_requiring_a_model(name):
    key='isolated-model-list-key'
    selected=options(name)
    seen=[]
    expected={'id':'gemini-test','name':'Gemini Test'} if name=='gemini' else {'id':'test-model','name':'Test Model'}
    def respond(request):
        seen.append(request)
        assert request.method=='GET'
        assert str(request.url).split('?')[0]==selected.baseUrl+'/models'
        assert not request.content
        if name=='gemini':
            assert request.headers['x-goog-api-key']==key
            assert request.url.params['pageSize']=='1000'
            payload={'models':[
                {'name':'models/gemini-test','displayName':'Gemini Test','supportedGenerationMethods':['generateContent'],'description':key},
                {'name':'models/embedding-test','supportedGenerationMethods':['embedContent']},
            ]}
        else:
            if name=='anthropic':
                assert request.headers['x-api-key']==key
                assert request.headers['anthropic-version']=='2023-06-01'
                assert request.url.params['limit']=='1000'
            else:assert request.headers['authorization']=='Bearer '+key
            payload={'data':[{'id':'test-model','display_name':'Test Model','description':key,'owned_by':'private-account'}]}
        return httpx.Response(200,json=payload)
    result=asyncio.run(ai.available_models(selected,key,transport=httpx.MockTransport(respond)))
    assert result=={'provider':name,'models':[expected]}
    assert len(seen)==1
    assert key not in json.dumps(result) and 'private-account' not in json.dumps(result)


@pytest.mark.parametrize('name',['anthropic','gemini'])
def test_model_discovery_follows_pagination_on_the_same_service(name):
    selected=options(name);seen=[]
    def respond(request):
        seen.append(request)
        assert request.url.host==httpx.URL(selected.baseUrl).host
        if name=='gemini':
            if len(seen)==1:
                return httpx.Response(200,json={'models':[{'name':'models/first','supportedGenerationMethods':['generateContent']}],'nextPageToken':'next-page'})
            assert request.url.params['pageToken']=='next-page'
            data={'models':[{'name':'models/second','supportedGenerationMethods':['generateContent']}]}
        else:
            if len(seen)==1:
                return httpx.Response(200,json={'data':[{'id':'first'}],'has_more':True,'last_id':'first'})
            assert request.url.params['after_id']=='first'
            data={'data':[{'id':'second'}],'has_more':False}
        return httpx.Response(200,json=data)
    result=asyncio.run(ai.available_models(selected,'isolated-list-key',transport=httpx.MockTransport(respond)))
    assert [m['id'] for m in result['models']]==['first','second']
    assert len(seen)==2


@pytest.mark.parametrize('selected',[
    ProviderOptions(provider='compatible',baseUrl='https://example.com/v1'),
    ProviderOptions(provider='openai',baseUrl='https://example.com/v1',protocol='responses'),
    ProviderOptions(provider='openai',baseUrl='https://api.openai.com/v1/custom',protocol='responses'),
])
def test_model_discovery_cannot_probe_or_redirect_a_key_to_custom_endpoints(selected,monkeypatch):
    async def unexpected_destination(*args,**kwargs):pytest.fail('Custom discovery must be rejected before DNS/network access')
    monkeypatch.setattr(ai,'check_destination',unexpected_destination)
    with pytest.raises(ai.HTTPException) as error:
        asyncio.run(ai.available_models(selected,'isolated-list-key'))
    assert error.value.status_code==422


@pytest.mark.parametrize('status',[301,401,403,429,500])
def test_model_discovery_errors_do_not_echo_provider_bodies_or_follow_redirects(status):
    key='isolated-secret-model-key';seen=[]
    def respond(request):
        seen.append(request)
        return httpx.Response(status,text=key,headers={'Location':'https://other.example.com/models'})
    with pytest.raises(ai.HTTPException) as error:
        asyncio.run(ai.available_models(options('openai'),key,transport=httpx.MockTransport(respond)))
    assert error.value.status_code==502 and key not in error.value.detail
    assert len(seen)==1


def test_model_discovery_timeout_is_safe():
    def respond(request):raise httpx.ReadTimeout('sensitive upstream error')
    with pytest.raises(ai.HTTPException) as error:
        asyncio.run(ai.available_models(options('gemini'),'isolated-list-key',transport=httpx.MockTransport(respond)))
    assert error.value.status_code==504
    assert 'sensitive' not in error.value.detail


@pytest.mark.parametrize('payload',[{}, {'data':None}, {'data':[None]}, {'error':{'message':'isolated-list-key'},'data':[]}])
def test_model_discovery_rejects_malformed_responses(payload):
    with pytest.raises(ai.HTTPException) as error:
        asyncio.run(ai.available_models(options('openai'),'isolated-list-key',transport=httpx.MockTransport(lambda _:httpx.Response(200,json=payload))))
    assert error.value.status_code==502
    assert 'isolated-list-key' not in error.value.detail


def test_models_route_requires_personal_key_and_never_falls_back_to_server_key(monkeypatch):
    monkeypatch.setattr(ai,'server_key',lambda:'server-only-key')
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    async def unexpected(*args,**kwargs):pytest.fail('Missing personal key must not query any provider')
    monkeypatch.setattr(ai,'available_models',unexpected)
    response=TestClient(app).post('/api/ai/models',json={'provider':options('openai').model_dump()})
    assert response.status_code==503
    assert 'server-only-key' not in response.text


def test_models_route_forwards_selected_provider_and_key_and_disables_cache(monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    async def available(selected,key):
        assert selected.provider=='anthropic' and not selected.model
        assert key=='isolated-route-key'
        return {'provider':'anthropic','models':[{'id':'test-model','name':'Test Model'}]}
    monkeypatch.setattr(ai,'available_models',available)
    response=TestClient(app).post('/api/ai/models',headers={'X-AI-Api-Key':'isolated-route-key'},json={'provider':options('anthropic').model_dump()})
    assert response.status_code==200 and response.json()['models'][0]['id']=='test-model'
    assert response.headers['cache-control']=='no-store'
    assert 'isolated-route-key' not in response.text


@pytest.mark.parametrize('key',['bad key','x'*4097])
def test_models_route_validates_keys_before_discovery(key,monkeypatch):
    async def unexpected(*args,**kwargs):pytest.fail('Invalid key must not query any provider')
    monkeypatch.setattr(ai,'available_models',unexpected)
    response=TestClient(app).post('/api/ai/models',headers={'X-AI-Api-Key':key},json={'provider':options('deepseek').model_dump()})
    assert response.status_code==422
    assert key not in response.text


def test_empty_gemini_search_candidates_fall_back_to_chat(monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    original_search=ai.search_web
    async def search(query,*,api_key,provider):
        return await original_search(query,api_key=api_key,provider=provider,transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'candidates':[],'promptFeedback':{'blockReason':'SAFETY'}})))
    async def complete(*args,**kwargs):return {'content':'{"content":"chat remains available"}'}
    monkeypatch.setattr(ai,'search_web',search);monkeypatch.setattr(ai,'complete',complete)
    selected=options('gemini').model_copy(update={'model':'gemini-test'})
    response=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'isolated-test-key'},json={
        'provider':selected.model_dump(),'keyMode':'personal','webSearch':True,'messages':[{'role':'user','content':'triangle'}]})
    assert response.status_code==200,response.text
    assert response.json()['searchStatus']=='unavailable'
    assert response.json()['content']=='chat remains available'
