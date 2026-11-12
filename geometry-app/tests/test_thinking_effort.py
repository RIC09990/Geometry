"""Model effort must reach the wire without changing questions or image pixels."""
import asyncio
import json

import httpx
import pytest

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


@pytest.mark.parametrize(('provider','url'), [
    ('deepseek','https://custom.example.com/v1'),('openai','https://api.openai.com/v1'),
    ('compatible','https://custom.example.com/v1')])
def test_other_services_do_not_inherit_the_deepseek_effort(provider,url):
    options=resolve_provider(ProviderOptions(provider=provider,baseUrl=url,model='selected-model',reasoningEffort='max'))
    _,body=request_body([ai.Message(role='user',content='Question')],options,'System',False)
    assert not {'reasoning','reasoning_effort','thinking'} & body.keys()


def test_thinking_metadata_is_not_fed_back_as_user_content():
    message=ai.Message.model_validate({'role':'assistant','content':'Answer','reasoningEffort':'max'})
    assert message.content=='Answer' and not hasattr(message,'reasoningEffort')


def test_invalid_effort_is_rejected_instead_of_silently_ignored():
    with pytest.raises(ValueError):ProviderOptions(reasoningEffort='turbo')
