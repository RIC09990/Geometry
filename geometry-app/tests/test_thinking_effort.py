"""Model effort must reach the wire without changing questions or image pixels."""
import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from server import ai
from server.ai_providers import ProviderOptions, request_body, resolve_provider
from tests.test_vision import image


@pytest.mark.parametrize('protocol', ['chat', 'responses'])
def test_legacy_open_pages_receive_flash_max_and_keep_native_image_input(protocol):
    options=resolve_provider(ProviderOptions(provider='deepseek',baseUrl='https://api.deepseek.com',
        model='deepseek-flash',protocol=protocol))
    calls=[]
    original=ai.Message(role='user',content='请检查原图中的推导。',images=[image()])
    def respond(request):
        calls.append(request)
        body=json.loads(request.content)
        assert body['model']=='deepseek-flash'
        if protocol=='chat':
            assert body['thinking']=={'type':'enabled'}
            assert body['reasoning_effort']=='max'
            assert body['messages'][-1]['content'][0]['text']==original.content
            assert body['messages'][-1]['content'][1]['image_url']['url']==original.images[0].dataUrl
            result={'choices':[{'message':{'content':'原图已检查。'},'finish_reason':'stop'}]}
        else:
            assert body['reasoning']=={'effort':'max'}
            assert 'thinking' not in body and 'reasoning_effort' not in body
            assert body['input'][-1]['content'][0]['text']==original.content
            assert body['input'][-1]['content'][1]['image_url']==original.images[0].dataUrl
            result={'output':[{'type':'message','content':[{'type':'output_text','text':'原图已检查。'}]}]}
        return httpx.Response(200,json=result)
    result=asyncio.run(ai.complete([original],api_key='isolated-effort-key',provider=options,
        transport=httpx.MockTransport(respond)))
    assert len(calls)==1  # No OCR round trip, Pro fallback, or rewritten image input.
    assert result['model']=='deepseek-flash' and result['reasoningEffort']=='max'
    assert 'isolated-effort-key' not in json.dumps(result)


@pytest.mark.parametrize(('selected','wire'), [('low','low'),('medium','high'),('high','high'),('max','max')])
def test_explicit_choices_are_not_overridden_by_the_maximum_default(selected,wire):
    options=resolve_provider(ProviderOptions(baseUrl='https://api.deepseek.com',
        model='deepseek-flash',reasoningEffort=selected))
    _,body=request_body([ai.Message(role='user',content='Original question')],options,'System',True)
    assert body['reasoning_effort']==wire
    assert body['messages'][-1]['content']=='Original question'


@pytest.mark.parametrize(('model','thinking'), [
    ('deepseek-v4.1-flash',{'type':'enabled'}),('gpt-4.1',None)])
def test_explicit_levels_reach_openai_compatible_services(model,thinking):
    options=resolve_provider(ProviderOptions(provider='compatible',baseUrl='https://relay.example.com/v1',
        model=model,protocol='chat',reasoningEffort='max'))
    _,body=request_body([ai.Message(role='user',content='Question')],options,'System',False)
    assert body['reasoning_effort']=='max'
    assert body.get('thinking')==thinking


def test_responses_endpoints_receive_the_effort_in_the_responses_format():
    options=resolve_provider(ProviderOptions(provider='compatible',baseUrl='https://relay.example.com/v1',
        model='selected-model',protocol='responses',reasoningEffort='max'))
    _,body=request_body([ai.Message(role='user',content='Question')],options,'System',False)
    assert body['reasoning']=={'effort':'max'}
    assert not {'reasoning_effort','thinking'} & body.keys()


def test_third_party_services_are_not_given_a_level_unless_the_user_selects_one():
    for provider,url in (('deepseek','https://custom.example.com/v1'),('openai','https://api.openai.com/v1'),
                         ('compatible','https://relay.example.com/v1')):
        options=resolve_provider(ProviderOptions(provider=provider,baseUrl=url,model='selected-model'))
        _,body=request_body([ai.Message(role='user',content='Question')],options,'System',False)
        assert not {'reasoning','reasoning_effort','thinking'} & body.keys()


@pytest.mark.parametrize('protocol',['anthropic','gemini'])
def test_protocols_without_an_effort_field_reject_an_explicit_level(protocol):
    options=ProviderOptions(provider=protocol,baseUrl='https://api.example.com/v1',model='selected-model',
        protocol=protocol,reasoningEffort='max')
    with pytest.raises(HTTPException) as error:
        request_body([ai.Message(role='user',content='Question')],options,'System',False)
    assert error.value.status_code==422


def test_thinking_metadata_is_not_fed_back_as_user_content():
    message=ai.Message.model_validate({'role':'assistant','content':'Answer','reasoningEffort':'max'})
    assert message.content=='Answer' and not hasattr(message,'reasoningEffort')


def test_invalid_effort_is_rejected_instead_of_silently_ignored():
    with pytest.raises(ValueError):ProviderOptions(reasoningEffort='turbo')
