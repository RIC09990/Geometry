import base64
import io
import json
import pytest
from PIL import Image,ImageDraw
from pypdf import PdfReader
from fastapi.testclient import TestClient
from server import ai,homework
from server.ai import ImageInput
from server.homework import Grading,parse_tutor_reply
from server.homework_pdf import build_homework_pdf,math_image
from server.main import app

def sample_homework():
    image=Image.new('RGB',(850,1050),'white');draw=ImageDraw.Draw(image)
    draw.text((70,80),'Homework rendering test',fill='black',font_size=34)
    draw.text((70,210),'1. AB = AC, BD = DC, AD = AD',fill='black',font_size=26)
    draw.text((70,250),'   triangle ABD congruent to ACD (SSS)',fill='black',font_size=26)
    draw.text((70,430),'2. 1/2 + 1/3 = 2/5',fill='black',font_size=26)
    output=io.BytesIO();image.save(output,format='PNG')
    picture=ImageInput(name='homework-test.png',dataUrl='data:image/png;base64,'+base64.b64encode(output.getvalue()).decode())
    grading=Grading.model_validate({'score':75,'maximum':100,'basis':'测试样张，非真实学生评分。第一题正确，第二题分母处理有误。',
      'items':[{'label':'第1题','verdict':'correct','studentWork':r'因为 \(AB=AC\)，\(BD=DC\)，\(AD=AD\)，所以两三角形全等。','feedback':'三组对应边分别相等，SSS 依据成立。','location':{'imageIndex':0,'x':.85,'y':.23}},
               {'label':'第2题','verdict':'incorrect','studentWork':r'\(\frac{1}{2}+\frac{1}{3}=\frac{2}{5}\)','feedback':'异分母分数相加应先通分，不能将分母直接相加。','correction':r'\[\frac{1}{2}+\frac{1}{3}=\frac{3}{6}+\frac{2}{6}=\frac{5}{6}\]','location':{'imageIndex':0,'x':.85,'y':.43}}]})
    content=r'''**作业得分：75/100**

在 \(\triangle ABD\) 与 \(\triangle ACD\) 中，

\[AB=AC,\quad BD=DC,\quad AD=AD.\]

所以 \(\triangle ABD\cong\triangle ACD\)（SSS）。

因此 \(\angle BAD=\angle DAC\)。

分数运算订正：

\[\frac{1}{2}+\frac{1}{3}=\frac{3}{6}+\frac{2}{6}=\frac{5}{6}.\]'''
    return grading,content,[picture]

def test_math_fractions_are_typeset_not_slash_text():
    image,w,h=math_image(r'\frac{a+b}{2}=\frac{5}{6}')
    assert image.startswith(b'\x89PNG') and w>20 and h>10

def test_real_report_contains_score_student_work_and_original_image():
    grading,content,images=sample_homework()
    data=build_homework_pdf(grading,content,images)
    document=PdfReader(io.BytesIO(data));text=''.join(p.extract_text() for p in document.pages)
    assert data.startswith(b'%PDF-') and '75 / 100' in text
    assert '逐项批注' in text and '学生作答' in text and '规范解答' in text
    assert len(document.pages)>=2 and len(data)<500000
    assert sum(len(p.images) for p in document.pages)>5

def test_plain_question_does_not_receive_a_grade_or_report(monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    async def complete(messages,**kwargs):
        assert kwargs['structured']
        return {'content':json.dumps({'mode':'solution','content':r'答案：\(30^{\circ}\)。','grading':{'score':100,'maximum':100,'items':[]}})}
    monkeypatch.setattr(ai,'complete',complete)
    result=TestClient(app).post('/api/ai/chat',headers={'X-DeepSeek-Api-Key':'isolated-test-key'},json={'keyMode':'personal','messages':[{'role':'user','content':'求角度'}]}).json()
    assert result['grading'] is None and 'reportPdf' not in result
    assert '30' in result['content']

def test_homework_route_really_builds_a_pdf_and_never_persists_the_key(monkeypatch):
    grading,content,images=sample_homework()
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    async def complete(messages,**kwargs):
        assert kwargs['api_key']=='isolated-homework-key'
        return {'content':json.dumps({'mode':'homework','content':content,'grading':grading.model_dump()})}
    monkeypatch.setattr(ai,'complete',complete)
    result=TestClient(app).post('/api/ai/chat',headers={'X-DeepSeek-Api-Key':'isolated-homework-key'},json={'keyMode':'personal','messages':[{'role':'user','content':'请批改我的作业','images':[i.model_dump() for i in images]}]})
    assert result.status_code==200,result.text
    reply=result.json();assert 'isolated-homework-key' not in result.text
    assert reply['content'].startswith('**作业得分') and reply['grading']['score']==75
    pdf=base64.b64decode(reply['reportPdf']['dataUrl'].split(',',1)[1]);assert pdf.startswith(b'%PDF-')
    assert 'reportError' not in reply

@pytest.mark.parametrize('source',['current','previous','none'])
def test_followup_keeps_context_but_report_only_embeds_current_submission(source,monkeypatch):
    from server import homework_pdf
    grading,content,images=sample_homework();picture=images[0]
    upload=lambda name:picture.model_copy(update={'name':name}).model_dump()
    earlier=[upload('older.png')] if source!='none' else []
    previous=[upload('latest-page-1.png'),upload('latest-page-2.png')] if source!='none' else []
    current=[upload('current.png')] if source=='current' else []
    expected_context=current or previous
    expected=current
    monkeypatch.setattr(ai,'recent_requests',ai.deque());calls=[];rendered=[]
    async def complete(messages,**kwargs):
        calls.append(messages)
        assert [image.name for message in messages for image in message.images]==[image['name'] for image in expected_context]
        return {'content':json.dumps({'mode':'homework','content':content,'grading':grading.model_dump()})}
    real_build=homework_pdf.build_homework_pdf
    def build(grading,content,images,language):
        rendered.append([image.name for image in images])
        return real_build(grading,content,images,language)
    monkeypatch.setattr(ai,'complete',complete);monkeypatch.setattr(homework_pdf,'build_homework_pdf',build)
    response=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'isolated-followup-key'},json={'keyMode':'personal','messages':[
        {'role':'user','content':'An earlier worksheet','images':earlier},
        {'role':'assistant','content':'Earlier feedback.'},
        {'role':'user','content':'Please review this worksheet','images':previous},
        {'role':'assistant','content':'Previous feedback.'},
        {'role':'user','content':'Please grade the same worksheet again','images':current},
    ]})
    assert response.status_code==200,response.text
    reply=response.json();assert len(calls)==1 and rendered==[[image['name'] for image in expected]]
    assert reply['grading']['score']==75 and 'reportError' not in reply
    document=PdfReader(io.BytesIO(base64.b64decode(reply['reportPdf']['dataUrl'].split(',',1)[1])))
    text=''.join(page.extract_text() for page in document.pages)
    assert text.count('原作业 · 第 ')==len(expected)
    if expected:assert any(image.image.size==(850,1050) for page in document.pages for image in page.images)


def test_ordinary_markdown_reply_remains_readable_if_provider_ignores_json():
    assert parse_tutor_reply('这是一个普通回复。').content=='这是一个普通回复。'


def test_valid_json_and_correctly_escaped_formulas_are_not_repaired(monkeypatch):
    def unexpected(source):pytest.fail('Valid JSON must take the strict path')
    monkeypatch.setattr(homework,'_repair_json_string_escapes',unexpected)
    content=r'\(\frac{1}{2}+\theta\), \text{angle}, \begin{aligned}a&=b\end{aligned}'+'\nA tab\tand quote " and control\b\f\r'
    reply=parse_tutor_reply(json.dumps({'mode':'conversation','content':content}))
    assert reply.content==content and reply.grading is None


@pytest.mark.parametrize('command',['frac','theta','text','begin','triangle','because','therefore','times','ne','nabla','right','bar','nu','rho','to'])
def test_malformed_json_latex_commands_never_become_json_control_characters(command):
    formula=r'\('+chr(92)+command+r'{x}\)'
    source='{"mode":"solution","content":"'+formula+'"}'
    reply=parse_tutor_reply(source)
    assert reply.content==formula
    assert not any(ord(char)<32 for char in reply.content)


def test_mixed_escaping_preserves_existing_json_escapes_and_repairs_only_strings():
    source=r'''{
      "mode":"solution",
      "content":"Raw \(\frac{1}{2}+\theta\), \text{x}, \begin{aligned}x=y\end{aligned}. Correct \\(\\frac{3}{4}\\).\nnext line\tspace, \"quote\", Unicode \u03b8 and \/."
    }'''
    reply=parse_tutor_reply(source)
    expected=r'Raw \(\frac{1}{2}+\theta\), \text{x}, \begin{aligned}x=y\end{aligned}. Correct \(\frac{3}{4}\).'
    assert reply.content==expected+'\nnext line\tspace, "quote", Unicode θ and /.'


def test_raw_newlines_and_tabs_inside_json_strings_are_repaired():
    source='{"content":"line one\nline two\r\nraw\ttab"}'
    assert parse_tutor_reply(source).content=='line one\nline two\r\nraw\ttab'


@pytest.mark.parametrize('grading',[
    {'score':150,'maximum':100},
    {'score':'not a score','maximum':100},
    {'score':10,'maximum':0},
    {'score':50,'items':[{'label':'1','verdict':'invented'}]},
    {'score':50,'items':[{'label':'1','verdict':'correct','location':{'imageIndex':0,'x':2,'y':.5}}]},
])
@pytest.mark.parametrize('malformed',[False,True])
def test_readable_content_survives_invalid_grading_without_a_fabricated_score(grading,malformed):
    content=r'Answer: \(\frac{5}{6}\).'
    source=json.dumps({'mode':'homework','content':content,'grading':grading})
    if malformed:source=source.replace(r'\\(',r'\(')
    reply=parse_tutor_reply(source)
    assert reply.content==content and reply.grading is None and reply.mode=='homework'


def test_invalid_grade_does_not_generate_a_pdf_or_show_protocol_json(monkeypatch):
    monkeypatch.setattr(ai,'recent_requests',ai.deque())
    async def complete(*args,**kwargs):
        return {'content':json.dumps({'mode':'homework','content':'Readable feedback.','grading':{'score':150,'maximum':100}})}
    monkeypatch.setattr(ai,'complete',complete)
    response=TestClient(app).post('/api/ai/chat',headers={'X-AI-Api-Key':'isolated-test-key'},json={
        'keyMode':'personal','messages':[{'role':'user','content':'Please review my work'}]})
    assert response.status_code==200,response.text
    reply=response.json()
    assert '独立复核暂未完成' in reply['content'] and reply['grading'] is None
    assert 'Readable feedback.' not in reply['content'] and '"grading"' not in reply['content']
    assert 'reportPdf' not in reply


def test_score_heading_is_not_duplicated_when_already_bold():
    source=json.dumps({'mode':'homework','content':'**作业得分：50/100**\n\nFeedback.','grading':{'score':50,'maximum':100}})
    assert parse_tutor_reply(source).content.count('作业得分')==1


def test_captured_mixed_latex_reply_recovers_actual_grade_and_builds_pdf():
    # Captured from the synthetic live worksheet; contains both one and two
    # backslashes in JSON strings, exactly as returned by the provider.
    with pytest.raises(json.JSONDecodeError):json.loads(_CAPTURED_HOMEWORK_REPLY)
    reply=parse_tutor_reply('```json\n'+_CAPTURED_HOMEWORK_REPLY+'\n```')
    assert reply.mode=='homework' and reply.grading is not None
    assert reply.grading.score==50 and reply.grading.maximum==100
    assert [item.verdict for item in reply.grading.items]==['correct','incorrect']
    assert reply.content.startswith('作业得分：50/100')
    assert r'\(\triangle ABC\)' in reply.content
    assert r'\frac{1}{2}+\frac{1}{3}=\frac{5}{6}' in reply.content
    assert not any(char in reply.content for char in ('\b','\f','\r','\t'))
    data=build_homework_pdf(reply.grading,reply.content,sample_homework()[2])
    document=PdfReader(io.BytesIO(data));text=''.join(page.extract_text() for page in document.pages)
    assert data.startswith(b'%PDF-') and '50 / 100' in text
    assert '逐项批注' in text and '规范解答' in text
    assert len(document.pages)>=2 and sum(len(page.images) for page in document.pages)>5


_CAPTURED_HOMEWORK_REPLY='{"mode":"homework","content":"作业得分：50/100\\n\\n**第 1 题（满分 50 分）：正确，得 50 分。**\\n\\n学生由 \\(AB=AC\\) 得出 \\(\\angle C=\\angle B=50^{\\circ}\\)，再利用三角形内角和 \\(180^{\\circ}\\) 求出 \\(\\angle A=80^{\\circ}\\)，推理完整。补充说明：等边对等角这一步最好写明“\\(\\because AB=AC\\)”。规范过程如下：\\n\\n已知：\\(\\triangle ABC\\) 中，\\(AB=AC\\)，\\(\\angle B=50^{\\circ}\\)。\\n\\n推导：\\n\\\\[\\n\\\\because AB=AC,\\\\quad \\\\therefore \\\\angle C=\\\\angle B=50^{\\\\circ}.\\n\\\\]\\n\\\\[\\n\\\\angle A=180^{\\\\circ}-\\\\angle B-\\\\angle C=180^{\\\\circ}-50^{\\\\circ}-50^{\\\\circ}=80^{\\\\circ}.\\n\\\\]\\n\\n结论：\\\\(\\\\angle A=80^{\\\\circ}\\\\)。\\n\\n**第 2 题（满分 50 分）：错误，得 0 分。**\\n\\n学生的错误在于把分子、分母分别相加：\\\\(\\\\frac{1}{2}+\\\\frac{1}{3}\\\\ne\\\\frac{1+1}{2+3}\\\\)。异分母分数相加必须先通分，使分数单位相同。\\n\\n规范过程：\\n\\\\[\\n\\\\frac{1}{2}+\\\\frac{1}{3}=\\\\frac{1\\\\times 3}{2\\\\times 3}+\\\\frac{1\\\\times 2}{3\\\\times 2}=\\\\frac{3}{6}+\\\\frac{2}{6}=\\\\frac{5}{6}.\\n\\\\]\\n\\n结论：\\\\(\\\\frac{1}{2}+\\\\frac{1}{3}=\\\\frac{5}{6}\\\\)。\\n\\n**评分依据**：两题各 50 分，合计 100 分。第 1 题结论与推理均正确，给满分 50 分；第 2 题结果错误，给 0 分。总得分 \\\\(50+0=50\\\\) 分。\\n\\n**分数加法规则资料**：异分母分数相加须先通分（取分母的最小公倍数），再将分子相加、分母不变。可参考 Khan Academy 的分数加法讲解：\\n- https://www.khanacademy.org/math/arithmetic/fraction-arithmetic/arith-review-add-sub-fractions/a/adding-fractions-review\\n- https://www.mathsisfun.com/fractions_addition.html\\n\\n以上资料均说明：同分母时分子相加；异分母时先化为同分母，不能直接把分子与分子、分母与分母相加。","grading":{"score":50,"maximum":100,"basis":"两题各50分，共100分。第1题等角与内角和推理正确得50分；第2题异分母加法错误得0分。","items":[{"label":"第1题","verdict":"correct","studentWork":"角 C = 50°，所以角 A = 180° - 50° - 50° = 80°。","feedback":"由 AB=AC 得角C=角B，再用内角和求角A，结论与推理均正确。","correction":"\\\\[\\\\because AB=AC,\\\\ \\\\angle C=\\\\angle B=50^{\\\\circ};\\\\quad \\\\angle A=180^{\\\\circ}-50^{\\\\circ}-50^{\\\\circ}=80^{\\\\circ}.\\\\]","location":{"imageIndex":0,"x":0.44,"y":0.34}},{"label":"第2题","verdict":"incorrect","studentWork":"1/2 + 1/3 = (1+1)/(2+3) = 2/5。","feedback":"异分母分数不能分子相加、分母相加，须先通分。","correction":"\\\\[\\\\frac{1}{2}+\\\\frac{1}{3}=\\\\frac{3}{6}+\\\\frac{2}{6}=\\\\frac{5}{6}.\\\\]","location":{"imageIndex":0,"x":0.42,"y":0.80}}]}}'
