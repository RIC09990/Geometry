"""A provider's blank JSON-mode output is not an unreadable student answer."""
import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from server.ai import Message,complete
from server.ai_providers import ProviderOptions,request_body,resolve_provider


@pytest.mark.parametrize('protocol',['chat','responses'])
def test_selected_max_reasoning_is_not_cut_off_by_the_old_short_answer_budget(protocol):
    options=resolve_provider(ProviderOptions(provider='deepseek',protocol=protocol))
    _,body=request_body([Message(role='user',content='Return one JSON answer')],options,'Tutor',True)
    assert not {'max_tokens','max_completion_tokens','max_output_tokens'}.intersection(body)
    assert (body.get('reasoning_effort') or body.get('reasoning',{}).get('effort'))=='max'


def test_blank_json_filter_gets_one_unfiltered_retry_without_changing_prompt_or_effort():
    calls=[]
    def respond(request):
        body=json.loads(request.content);calls.append(body)
        assert body['reasoning_effort']=='max' and 'max_tokens' not in body
        if len(calls)==1:
            assert body['response_format']=={'type':'json_object'}
            return httpx.Response(200,json={'choices':[{'message':{'content':'   \n  ','reasoning_content':'private reasoning'},'finish_reason':'stop'}]})
        assert len(calls)==2 and 'response_format' not in body
        assert body['messages']==calls[0]['messages']
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"routes":[],"answer":"The minimum is sqrt(10)."}'},'finish_reason':'stop'}]})
    reply=asyncio.run(complete([Message(role='user',content='Solve this problem as JSON')],api_key='test-filter-key',structured=True,transport=httpx.MockTransport(respond)))
    assert len(calls)==2 and json.loads(reply['content'])['answer']=='The minimum is sqrt(10).'
    assert 'private reasoning' not in str(reply)


def test_repeated_blank_output_does_not_create_a_retry_loop():
    calls=[]
    def respond(request):
        calls.append(1)
        return httpx.Response(200,json={'choices':[{'message':{'content':'  '},'finish_reason':'stop'}]})
    with pytest.raises(HTTPException) as error:
        asyncio.run(complete([Message(role='user',content='Return JSON')],api_key='test-filter-key',structured=True,transport=httpx.MockTransport(respond)))
    assert len(calls)==2 and error.value.status_code==502


def test_reasoning_only_length_result_never_becomes_an_answer_or_a_repeated_request():
    calls=[]
    def respond(request):
        calls.append(1)
        return httpx.Response(200,json={'choices':[{'message':{'content':None,'reasoning_content':'private unfinished reasoning'},'finish_reason':'length'}]})
    with pytest.raises(HTTPException) as error:
        asyncio.run(complete([Message(role='user',content='Return JSON')],api_key='test-filter-key',structured=True,transport=httpx.MockTransport(respond)))
    assert len(calls)==1 and '输出上限' in error.value.detail
    assert 'private unfinished reasoning' not in str(error.value.detail)
