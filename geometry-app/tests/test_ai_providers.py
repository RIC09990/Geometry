import asyncio
import json
import pytest
import httpx
from fastapi.testclient import TestClient
from server import ai
from server.ai_providers import ProviderOptions,PRESETS
from server.main import app
from tests.test_vision import image

@pytest.mark.parametrize('name',['deepseek','openai','anthropic','gemini','compatible'])
def test_provider_text_and_real_image_contracts_without_vendor_sdks(name):
    preset=PRESETS[name]
    options=ProviderOptions(provider=name,baseUrl=preset['baseUrl'] or 'https://api.example.com/v1',protocol=preset['protocol'],model=preset['model'] or 'test-model')
    def respond(request):
        body=json.loads(request.content);assert request.url.host in options.baseUrl
        assert ('deepseek' in str(request.url))==(name=='deepseek')
        if options.protocol=='anthropic':
            assert request.headers['x-api-key']=='test-provider-key'
            assert body['messages'][0]['content'][1]['source']['data']==image().dataUrl.split(',',1)[1]
            assert 'response_format' not in body
            data={'content':[{'type':'text','text':'test reply'}],'stop_reason':'end_turn'}
        elif options.protocol=='gemini':
            assert request.headers['x-goog-api-key']=='test-provider-key'
            assert body['contents'][0]['parts'][1]['inlineData']['data']==image().dataUrl.split(',',1)[1]
            assert body['generationConfig']['responseMimeType']=='application/json'
            data={'candidates':[{'content':{'parts':[{'text':'test reply'}]},'finishReason':'STOP'}]}
        elif options.protocol=='responses':
            assert request.headers['authorization']=='Bearer test-provider-key'
            assert body['input'][0]['content'][1]['image_url']==image().dataUrl
            assert body['store'] is False
            data={'output':[{'type':'message','content':[{'type':'output_text','text':'test reply'}]}],'incomplete_details':None}
        else:
            assert request.headers['authorization']=='Bearer test-provider-key'
            assert body['messages'][1]['content'][1]['image_url']['url']==image().dataUrl
            if name=='deepseek':
                assert body['thinking']=={'type':'enabled'} and body['reasoning_effort']=='max'
            else:assert 'thinking' not in body
            data={'choices':[{'message':{'content':'test reply'},'finish_reason':'stop'}]}
        return httpx.Response(200,json=data)
    reply=asyncio.run(ai.complete([ai.Message(role='user',content='test image',images=[image()])],api_key='test-provider-key',provider=options,structured=True,transport=httpx.MockTransport(respond)))
    assert reply['content']=='test reply' and reply['provider']==name

@pytest.mark.parametrize('protocol',['responses','anthropic','gemini'])
def test_native_search_uses_selected_provider_key_and_extracts_sources(protocol):
    name={'responses':'openai','anthropic':'anthropic','gemini':'gemini'}[protocol]
    options=ProviderOptions(provider=name,baseUrl=PRESETS[name]['baseUrl'],protocol=protocol,model='test-model')
    def respond(request):
        body=json.loads(request.content);assert request.url.host!='api.deepseek.com'
        assert body['tools']
        if protocol=='responses':data={'output':[{'type':'message','content':[{'type':'output_text','text':'found','annotations':[{'type':'url_citation','url':'https://example.com/math','title':'Source'}]}]}]}
        elif protocol=='anthropic':data={'content':[{'type':'text','text':'found','citations':[{'type':'web_search_result_location','url':'https://example.com/math','title':'Source'}]}]}
        else:data={'candidates':[{'content':{'parts':[{'text':'found'}]},'groundingMetadata':{'groundingChunks':[{'web':{'uri':'https://example.com/math','title':'Source'}}]}}]}
        return httpx.Response(200,json=data)
    sources=asyncio.run(ai.search_web('geometry answer',api_key='test-search-key',provider=options,transport=httpx.MockTransport(respond)))
    assert sources[0]['url']=='https://example.com/math' and 'found' in sources[0]['content']

def test_older_chat_reply_metadata_no_longer_breaks_the_next_message(monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    async def complete(messages,**kwargs):
        assert messages[1].role=='assistant'
        assert not hasattr(messages[1],'sources')
        return {'content':json.dumps({'content':'message accepted','mode':'conversation'})}
    monkeypatch.setattr(ai,'complete',complete)
    response=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'test-key'},json={'keyMode':'personal','messages':[
        {'role':'user','content':'original question'},
        {'role':'assistant','content':'previous answer','sources':[],'searchStatus':'found','reportPdf':{'dataUrl':'not sent to model'}},
        {'role':'user','content':'follow-up'}]})
    assert response.status_code==200,response.text
    assert response.json()['content']=='message accepted'

def test_new_provider_settings_are_used_by_actual_chat_route(monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    async def complete(messages,**kwargs):
        assert kwargs['provider'].provider=='anthropic' and kwargs['provider'].model=='selected-model'
        assert kwargs['api_key']=='selected-provider-key'
        return {'content':json.dumps({'content':'ok'})}
    monkeypatch.setattr(ai,'complete',complete)
    response=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'selected-provider-key'},json={'provider':{**PRESETS['anthropic'],'provider':'anthropic','model':'selected-model'},'keyMode':'personal','messages':[{'role':'user','content':'test'}]})
    assert response.status_code==200,response.text

def test_search_and_reply_use_the_same_selected_configuration(monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    options=ProviderOptions(provider='deepseek',baseUrl='https://custom.example.com/v1',model='custom-model')
    seen=[]
    async def search(query,*,api_key,provider):
        assert api_key=='selected-provider-key' and provider==options
        seen.append('search')
        return []
    async def complete(messages,**kwargs):
        assert kwargs['api_key']=='selected-provider-key' and kwargs['provider']==options
        seen.append('reply')
        return {'content':json.dumps({'content':'ok'})}
    monkeypatch.setattr(ai,'search_web',search);monkeypatch.setattr(ai,'complete',complete)
    response=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'selected-provider-key'},json={
        'provider':options.model_dump(),'keyMode':'personal','webSearch':True,'messages':[{'role':'user','content':'test'}]})
    assert response.status_code==200,response.text
    assert seen==['search','reply']


def test_custom_chat_endpoint_cannot_send_its_key_to_the_default_search_vendor():
    options=ProviderOptions(provider='deepseek',baseUrl='https://custom.example.com/v1',model='custom-model')
    def unexpected(request):
        pytest.fail('A custom endpoint key must not be sent to a different service')
    with pytest.raises(ai.HTTPException) as error:
        asyncio.run(ai.search_web('geometry',api_key='custom-key',provider=options,transport=httpx.MockTransport(unexpected)))
    assert error.value.status_code==502


def test_server_credentials_cannot_be_redirected_by_a_visitors_provider_setting(monkeypatch):
    monkeypatch.setenv('AI_API_KEY','server-only-key');monkeypatch.setattr(ai,'recent_requests',ai.deque())
    async def complete(messages,**kwargs):
        assert kwargs['api_key']=='server-only-key' and kwargs['provider'].baseUrl!='https://example.com/v1'
        return {'content':'ok'}
    monkeypatch.setattr(ai,'complete',complete)
    response=TestClient(app).post('/api/ai/chat',json={'provider':{'provider':'compatible','baseUrl':'https://example.com/v1','model':'test'},'messages':[{'role':'user','content':'test'}]})
    assert response.status_code==200,response.text

@pytest.mark.parametrize('url',['http://127.0.0.1:8001','https://127.0.0.1','https://user:password@example.com','https://localhost','https://example.com?key=secret'])
def test_custom_endpoint_does_not_turn_the_public_site_into_a_private_network_proxy(url):
    with pytest.raises(ValueError):ProviderOptions(provider='compatible',baseUrl=url,model='test')
