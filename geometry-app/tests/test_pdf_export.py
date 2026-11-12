"""Export is a local document operation, independent of scoring and model access."""
import asyncio
import base64
import io
import json

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from server import ai,homework
from server.main import app


@pytest.fixture(autouse=True)
def isolated_limit(monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque())


def pdf_text(reply):
    pdf=base64.b64decode(reply['reportPdf']['dataUrl'].split(',',1)[1])
    assert pdf.startswith(b'%PDF-')
    return '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def test_export_existing_reply_needs_no_key_search_or_model(monkeypatch):
    async def forbidden(*args,**kwargs):pytest.fail('PDF export must be local')
    monkeypatch.setattr(ai,'complete',forbidden)
    monkeypatch.setattr(ai,'search_web',forbidden)
    response=TestClient(app).post('/api/ai/export-pdf',json={'content':'这是已有解答。\n\n结论正确。'})
    assert response.status_code==200,response.text
    text=pdf_text(response.json())
    assert '这是已有解答' in text and '结论正确' in text
    assert '作业得分' not in text and '暂无法评分' not in text
    assert response.headers['cache-control']=='no-store'


@pytest.mark.parametrize('mode',['conversation','solution','homework'])
def test_model_export_flag_without_current_grading_cannot_create_a_report(mode,monkeypatch):
    calls=[]
    async def complete(messages,**kwargs):
        calls.append(messages)
        assert messages[-1].content=='生成批改我答案的PDF'
        assert len(kwargs['system'])<1400
        return {'content':json.dumps({'mode':mode,'content':'已核对：两式等价。','exportPdf':True,'grading':None})}
    monkeypatch.setattr(ai,'complete',complete)
    response=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'isolated-pdf-key'},json={
        'keyMode':'personal','messages':[{'role':'user','content':'我的答案是2∠BOC=∠BAC+180°。'},
        {'role':'assistant','content':'两式等价，推导正确。'}, {'role':'user','content':'生成批改我答案的PDF'}]})
    assert response.status_code==200,response.text
    assert len(calls)==1
    reply=response.json()
    assert reply['grading'] is None and '两式等价' in reply['content']
    assert not reply['pdfEligible'] and 'reportPdf' not in reply
    assert 'isolated-pdf-key' not in response.text


def test_corrected_ocr_and_relabeled_review_are_not_anchored_to_first_pass():
    draft=homework.TutorReply(mode='homework',content='Draft',grading=homework.Grading(score=100,items=[
        homework.HomeworkItem(label='第1题',verdict='correct',studentWork='1/2+1/3=2/5')]))
    final={'mode':'homework','content':'已重新读取原文，算式是5/6。','grading':{'score':100,'maximum':100,
        'items':[{'label':'1','verdict':'correct','studentWork':'1/2+1/3=5/6'}]}}
    reviewed=homework.checked_homework_reply(json.dumps(final),draft)
    assert reviewed.grading.items[0].label=='1' and reviewed.grading.score==100
    final['grading']['items'][0]['studentWork']='1/2+1/3=2/5'
    with pytest.raises(ValueError,match='false arithmetic'):
        homework.checked_homework_reply(json.dumps(final),draft)


def test_empty_unscored_grading_is_treated_as_prose_and_can_export():
    result={'mode':'homework','content':'只导出批注，不评分。','exportPdf':True,
            'grading':{'score':None,'maximum':100,'items':[]}}
    reviewed=homework.checked_homework_reply(json.dumps(result),homework.TutorReply.model_validate(result))
    assert reviewed.grading is None and reviewed.exportPdf
    assert '暂无法评分' not in reviewed.content


def test_review_can_return_valid_unscored_pdf_without_requiring_a_new_score(monkeypatch):
    calls=[]
    async def complete(messages,**kwargs):
        calls.append(messages)
        if len(calls)==1:return {'content':json.dumps({'mode':'homework','content':'初始评分格式不完整。',
            'exportPdf':True,'grading':{'score':100,'items':[]}})}
        return {'content':json.dumps({'mode':'homework','content':'重新核对后：正确的计算结果是5/6。',
            'exportPdf':True,'grading':None})}
    monkeypatch.setattr(ai,'complete',complete)
    response=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'isolated-pdf-key'},json={
        'keyMode':'personal','messages':[{'role':'user','content':'生成批改PDF，不需要打分。'}]})
    assert response.status_code==200,response.text
    reply=response.json()
    assert len(calls)==2 and reply['grading'] is None
    assert '5/6' in reply['content'] and '独立复核暂未完成' not in reply['content']
    assert not reply['pdfEligible'] and 'reportPdf' not in reply


def test_truncated_pdf_reply_is_not_published_as_a_complete_file():
    result=asyncio.run(ai.tutor_response({'content':json.dumps({'mode':'homework','content':'尚未完成','grading':{
        'score':None,'items':[{'label':'1','verdict':'unclear','studentWork':'答案尚未读完'}]}}),
        'finishReason':'length'},[],'zh'))
    assert 'reportPdf' not in result and '完整' in result['reportError']


@pytest.mark.parametrize('content',['','   '])
def test_empty_export_is_rejected_with_a_clear_client_error(content):
    response=TestClient(app).post('/api/ai/export-pdf',json={'content':content})
    assert response.status_code==422


def test_ordinary_reply_cannot_inherit_a_preceding_report_or_model_export_flag():
    result=asyncio.run(ai.tutor_response({'content':json.dumps({'mode':'solution','content':'CURRENT-SOLUTION',
        'exportPdf':True}),'reportPdf':{'name':'old.pdf','dataUrl':'old'},'reportError':'old error',
        'pdfEligible':True},[],'zh'))
    assert result['content']=='CURRENT-SOLUTION' and result['grading'] is None
    assert not result['pdfEligible'] and 'reportPdf' not in result and 'reportError' not in result


def test_grading_then_solution_then_new_text_grading_never_exports_historical_work(monkeypatch):
    from server import homework_pdf
    from tests.test_homework import sample_homework
    picture=sample_homework()[2][0].model_dump()
    rendered=[];real_build=homework_pdf.build_homework_pdf
    def build(grading,content,images,language):
        rendered.append((content,[image.name for image in images]))
        return real_build(grading,content,images,language)
    async def complete(messages,**kwargs):
        latest=messages[-1].content
        if latest=='普通解题：求一个新的角度':
            return {'content':json.dumps({'mode':'solution','content':'NEW-ANGLE-SOLUTION','exportPdf':True})}
        marker='FIRST-WORK' if latest=='批改这张作业' else 'CURRENT-WORK'
        return {'content':json.dumps({'mode':'homework','content':marker+' 已检查并订正。','grading':{
            'score':None,'maximum':100,'items':[{'label':marker,'verdict':'incorrect',
                'studentWork':marker+' 1/2+1/3=2/5','feedback':'需要通分','correction':'5/6'}]}})}
    monkeypatch.setattr(ai,'complete',complete);monkeypatch.setattr(homework_pdf,'build_homework_pdf',build)
    client=TestClient(app);history=[];headers={'X-AI-Api-Key':'isolated-turn-bound-report'}
    for content,images in [('批改这张作业',[picture]),('普通解题：求一个新的角度',[]),('批改本次文本：1/2+1/3=2/5',[])]:
        history.append({'role':'user','content':content,'images':images})
        response=client.post('/api/ai/chat',headers=headers,json={'keyMode':'personal','messages':history})
        assert response.status_code==200,response.text
        reply=response.json();history.append({'role':'assistant','content':reply['content']})
        if content.startswith('普通'):
            assert not reply['pdfEligible'] and 'reportPdf' not in reply and reply['grading'] is None
        else:
            text=pdf_text(reply);assert reply['pdfEligible']
            marker='FIRST-WORK' if images else 'CURRENT-WORK'
            assert marker in text
            if not images:assert 'FIRST-WORK' not in text and '原作业 · 第' not in text
    assert len(rendered)==2 and rendered[0][1]==[picture['name']] and rendered[1][1]==[]
