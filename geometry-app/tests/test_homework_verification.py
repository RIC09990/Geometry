import asyncio
import base64
import io
import json

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from server import ai,homework
from server.ai_providers import PRESETS,ProviderOptions
from server.main import app
from tests.test_homework import _CAPTURED_HOMEWORK_REPLY,sample_homework


def contradictory_draft():
    draft=homework.parse_tutor_reply(_CAPTURED_HOMEWORK_REPLY).model_dump()
    draft['grading']['score']=100
    draft['grading']['items'][1]['verdict']='correct'
    draft['grading']['items'][1]['feedback']='The fraction calculation is correct.'
    draft['content']='作业得分：100/100。两题均正确。我无法生成 PDF。'
    return draft


def verified_reply():
    return homework.parse_tutor_reply(_CAPTURED_HOMEWORK_REPLY).model_dump()


@pytest.mark.parametrize('name',['deepseek','openai','anthropic','gemini'])
def test_contradictory_full_score_gets_one_independent_review_with_same_provider_and_key(name,monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    config=ProviderOptions(provider=name,baseUrl=PRESETS[name]['baseUrl'],protocol=PRESETS[name]['protocol'],model='selected-model',reasoningEffort='max' if name=='deepseek' else None)
    images=sample_homework()[2];calls=[]
    async def complete(messages,**kwargs):
        calls.append((messages,kwargs))
        assert kwargs['api_key']=='isolated-review-key' and kwargs['provider']==config
        assert any(message.images==images for message in messages)
        if len(calls)==1:return {'content':json.dumps(contradictory_draft()),'finishReason':'stop'}
        assert len(calls)==2 and kwargs['structured']
        prompt=kwargs['system']
        assert '独立重新核对原始作答' in prompt
        assert messages[-1].content=='Please grade both questions'
        assert '100/100' not in prompt and 'The fraction calculation is correct.' not in prompt
        assert 'frac{5}{6}' not in prompt  # No anchoring to the model's own correction.
        return {'content':json.dumps(verified_reply()),'finishReason':'stop'}
    monkeypatch.setattr(ai,'complete',complete)
    response=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'isolated-review-key'},json={
        'provider':config.model_dump(),'keyMode':'personal','messages':[{'role':'user','content':'Please grade both questions','images':[image.model_dump() for image in images]}]})
    assert response.status_code==200,response.text
    reply=response.json();assert len(calls)==2
    assert reply['grading']['score']==50 and reply['grading']['items'][1]['verdict']=='incorrect'
    assert '无法生成' not in reply['content'] and '100/100' not in reply['content']
    pdf=base64.b64decode(reply['reportPdf']['dataUrl'].split(',',1)[1])
    assert '50 / 100' in ''.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    assert 'isolated-review-key' not in response.text


@pytest.mark.parametrize('failure',['http','timeout','malformed','wrong_mode','truncated','inconsistent_score','repeated_contradiction','text_score'])
def test_failed_independent_review_never_publishes_draft_grade_or_pdf(failure,monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque());calls=[]
    async def complete(messages,**kwargs):
        calls.append(messages)
        if len(calls)==1:return {'content':json.dumps(contradictory_draft())}
        if failure=='http':raise ai.HTTPException(502,'private upstream details')
        if failure=='timeout':raise TimeoutError('private upstream details')
        if failure=='malformed':return {'content':'not a grading object'}
        if failure=='repeated_contradiction':return {'content':json.dumps(contradictory_draft())}
        result=verified_reply()
        if failure=='wrong_mode':result['mode']='solution'
        if failure=='inconsistent_score':result['grading']['score']=100
        if failure=='text_score':result['content']='作业得分：100/100。两题均正确。'
        return {'content':json.dumps(result),'finishReason':'length' if failure=='truncated' else 'stop'}
    monkeypatch.setattr(ai,'complete',complete)
    response=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'isolated-review-key'},json={
        'keyMode':'personal','messages':[{'role':'user','content':'My work: 1/2+1/3=2/5'}]})
    assert response.status_code==200,response.text
    reply=response.json()
    assert len(calls)==2 and reply['grading'] is None and 'reportPdf' not in reply
    assert '独立复核暂未完成' in reply['content']
    assert '100/100' not in reply['content'] and 'private upstream details' not in reply['content']


@pytest.mark.parametrize('draft_score',[None,150,'unreadable'])
def test_failed_review_never_echoes_scores_from_invalid_draft_metadata(draft_score,monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque());calls=[]
    draft={'mode':'homework','content':'作业得分：100/100。两题都正确，获得满分。',
           'grading':None if draft_score is None else {'score':draft_score,'maximum':100}}
    async def complete(*args,**kwargs):
        calls.append(1)
        if len(calls)==1:return {'content':json.dumps(draft)}
        raise ai.HTTPException(502,'private upstream details')
    monkeypatch.setattr(ai,'complete',complete)
    reply=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'isolated-review-key'},json={
        'keyMode':'personal','messages':[{'role':'user','content':'Please grade my work'}]}).json()
    assert len(calls)==2 and reply['grading'] is None and 'reportPdf' not in reply
    assert reply['content']=='作业的独立复核暂未完成，本次不提供评分和批改报告，请重试。'


@pytest.mark.parametrize('content',[
    '**作业得分：100/100**\n\n第二题错误。',
    'Homework score: 100/100. The second answer is incorrect.',
    '第二题错误。\n\n总得分：100分。',
    'The second answer is incorrect. Overall score is 100 out of 100.',
    r'总分：\(\frac{100}{100}\)。',
    '最终得分：50/200。',
    'Score: 100/100\nThe second answer is incorrect.', '得分：100/100\n第二题错误。',
])
def test_explicit_overall_score_must_agree_with_verified_structure(content):
    draft=homework.TutorReply.model_validate(contradictory_draft());result=verified_reply();result['content']=content
    with pytest.raises(ValueError,match='text contradicts'):
        homework.checked_homework_reply(json.dumps(result),draft)


@pytest.mark.parametrize('heading',[
    '', '**作业得分：50/100**\n\n', '## 作业得分：50 / 100\n\n', '得分：50/100\n\n',
    'Homework score: 50 out of 100.\n\n',
])
def test_verified_heading_is_canonical_without_changing_item_scores_or_math(heading):
    result=verified_reply();body='第1题得50分，第2题得0分。\n\n'+r'\(\frac{1}{2}+\frac{1}{3}=\frac{5}{6}\)。'
    result['content']=heading+body
    reply=homework.checked_homework_reply(json.dumps(result),homework.TutorReply.model_validate(contradictory_draft()))
    assert reply.content==('**Homework score: 50/100**' if heading.startswith('Homework') else '**作业得分：50/100**')+'\n\n'+body
    assert reply.grading.score==50


def test_unscorable_review_cannot_announce_a_numeric_score():
    result=verified_reply();result['grading']['score']=None;result['content']='作业得分：50/100。'
    draft=homework.TutorReply.model_validate(contradictory_draft())
    with pytest.raises(ValueError,match='text contradicts'):homework.checked_homework_reply(json.dumps(result),draft)
    result['content']='暂无法看清第二题，需要重新上传。'
    reply=homework.checked_homework_reply(json.dumps(result),draft)
    assert reply.content=='暂无法看清第二题，需要重新上传。' and reply.grading.score is None


def test_maximum_description_and_total_arithmetic_are_not_misread_as_wrong_scores():
    result=verified_reply();result['content']='总得分50+0=50分。试卷总分100分。'
    reply=homework.checked_homework_reply(json.dumps(result),homework.TutorReply.model_validate(contradictory_draft()))
    assert reply.content=='**作业得分：50/100**\n\n'+result['content']
    result['content']='Homework score: 50/100\nThe maximum overall score is 100.'
    reply=homework.checked_homework_reply(json.dumps(result),homework.TutorReply.model_validate(contradictory_draft()))
    assert reply.content=='**Homework score: 50/100**\n\nThe maximum overall score is 100.'


def test_general_prose_ocr_correction_is_not_blocked_by_numeric_guard():
    draft=verified_reply();draft['grading']['items']=draft['grading']['items'][:1]
    draft['grading']['items'][0]['studentWork']='手写角A可能为8O度。'
    result=verified_reply();result['grading']['items']=result['grading']['items'][:1]
    result['grading']['items'][0]['studentWork']='角A为80度。'
    assert homework.checked_homework_reply(json.dumps(result),homework.TutorReply.model_validate(draft)).grading.items[0].verdict=='correct'


def test_plain_solution_uses_only_one_completion(monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque());calls=[]
    async def complete(messages,**kwargs):
        calls.append(messages);return {'content':json.dumps({'mode':'solution','content':'The answer is 80 degrees.'})}
    monkeypatch.setattr(ai,'complete',complete)
    reply=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'isolated-review-key'},json={
        'keyMode':'personal','messages':[{'role':'user','content':'Find the angle'}]}).json()
    assert len(calls)==1 and reply['grading'] is None and 'reportPdf' not in reply


def test_server_verification_keeps_configuration_even_if_settings_change_between_passes(monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    initial=ProviderOptions(provider='openai',baseUrl=PRESETS['openai']['baseUrl'],protocol='responses',model='original-model')
    changed=ProviderOptions(provider='gemini',baseUrl=PRESETS['gemini']['baseUrl'],protocol='gemini',model='different-model')
    monkeypatch.setattr(ai,'server_key',lambda:'original-server-key')
    monkeypatch.setattr(ai,'resolve_provider',lambda _:initial)
    calls=[]
    async def complete(messages,**kwargs):
        calls.append(kwargs)
        assert kwargs['provider']==initial and kwargs['api_key']=='original-server-key'
        if len(calls)==1:
            monkeypatch.setattr(ai,'server_key',lambda:'different-server-key')
            monkeypatch.setattr(ai,'resolve_provider',lambda _:changed)
            return {'content':json.dumps(contradictory_draft())}
        return {'content':json.dumps(verified_reply())}
    monkeypatch.setattr(ai,'complete',complete)
    reply=asyncio.run(ai.dispatch(ai.ChatRequest(messages=[ai.Message(role='user',content='grade work')]),None,structured=True,verify_homework=True))
    assert len(calls)==2 and homework.parse_tutor_reply(reply['content']).grading.score==50


def test_proof_review_also_performs_independent_homework_verification(monkeypatch):
    from tests.test_topics import problem
    monkeypatch.setattr(ai,'recent_requests',ai.deque());calls=[]
    async def complete(messages,**kwargs):
        calls.append(messages);return {'content':json.dumps(contradictory_draft() if len(calls)==1 else verified_reply())}
    monkeypatch.setattr(ai,'complete',complete)
    response=TestClient(app).post('/api/ai/review-proof',headers={'X-AI-Api-Key':'isolated-review-key'},json={
        'problem':problem().model_dump(),'proofText':'Student proof and fraction work','keyMode':'personal'})
    assert response.status_code==200,response.text
    assert len(calls)==2 and response.json()['grading']['score']==50


def test_prompt_leaves_pdf_generation_to_application():
    assert 'PDF 文件由 Geometry 应用' in homework.tutor_instructions()
    assert '不要声称不能生成 PDF' in homework.homework_verification_instructions(homework.TutorReply.model_validate(contradictory_draft()))


@pytest.mark.parametrize('work',[
    '1/2 + 1/3 = (1+1)/(2+3) = 2/5。',
    r'\(\frac{1}{2}+\frac{1}{3}=\frac{2}{5}\)',
    '180-50-50=90',
])
def test_pure_arithmetic_contradictions_are_rejected_even_if_reviewer_repeats_them(work):
    assert homework.false_numeric_equality(work)


@pytest.mark.parametrize('work',[
    '1/2+1/3=5/6', '0.1+0.2=0.3', '0.123456789012345678901+0.1=0.223456789012345678901',
    r'\(\frac{1}{2}+\frac{1}{3}=\frac{5}{6}\)',
    '学生指出 1/2+1/3=2/5 是错误的。',
    'x+1=2', '__import__("os").system("echo bad")=0',
    '1/3=0.333...', '1/3=0.333…', '1/3=0.333⋯', r'\(1/3=0.333\ldots\)',
])
def test_arithmetic_guard_does_not_evaluate_code_or_guess_about_general_reasoning(work):
    assert not homework.false_numeric_equality(work)
