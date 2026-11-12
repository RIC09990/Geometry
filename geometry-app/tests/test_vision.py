import asyncio
import base64
import io
import json
import httpx
import pytest
from PIL import Image
from pydantic import ValidationError
from server import ai

def image():
    data=io.BytesIO();Image.new('RGB',(32,32),'white').save(data,format='PNG')
    return ai.ImageInput(name='手写证明.png',dataUrl='data:image/png;base64,'+base64.b64encode(data.getvalue()).decode())

def test_real_multimodal_request_keeps_pixels_and_text_without_ocr_placeholder():
    def respond(request):
        body=json.loads(request.content)
        assert body['model']=='deepseek-flash'
        assert body['messages'][0]['content']=='你是 Geometry小助手，英文名 Geometry Assistant。'
        parts=body['messages'][1]['content']
        assert parts[0]=={'type':'text','text':'请看看我的手写证明'}
        assert parts[1]['image_url']['url']==image().dataUrl
        assert parts[1]['image_url']['detail']=='original'
        return httpx.Response(200,json={'choices':[{'message':{'content':'图片批注'}}]})
    result=asyncio.run(ai.complete([ai.Message(role='user',content='请看看我的手写证明',images=[image()])],api_key='isolated-test',transport=httpx.MockTransport(respond)))
    assert result['content']=='图片批注'

def test_invalid_image_is_not_sent_as_if_it_were_recognized():
    with pytest.raises(ValidationError):ai.ImageInput(dataUrl='data:image/png;base64,aW52YWxpZA==')

def test_search_uses_official_api_with_same_key_and_returns_actual_sources():
    def respond(request):
        assert str(request.url)=='https://api.deepseek.com/v1/tools/search'
        assert request.headers['authorization']=='Bearer same-test-key'
        assert json.loads(request.content)['need_content']
        return httpx.Response(200,json={'results':[{'title':'Geometry reference','url':'https://example.com/math','content':'Reference text'}]})
    result=asyncio.run(ai.search_web('geometry',api_key='same-test-key',transport=httpx.MockTransport(respond)))
    assert result[0]['content']=='Reference text'

def test_image_only_student_submission_is_accepted_without_forced_step_format(monkeypatch):
    from fastapi.testclient import TestClient
    from server.main import app
    from tests.test_proof_review import problem
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    async def complete(messages,**kwargs):
        assert kwargs['system'].startswith(ai.SYSTEM) and len(kwargs['system'])<1400
        assert messages[-1].images
        return {'content':'批注','model':'test'}
    monkeypatch.setattr(ai,'complete',complete)
    response=TestClient(app).post('/api/ai/review-proof',json={'problem':problem(),'images':[image().model_dump()],'keyMode':'personal'},headers={'X-DeepSeek-Api-Key':'test-shared-key'})
    assert response.status_code==200,response.text
