import io
import re
import asyncio
import json

import pytest
from pypdf import PdfReader
from reportlab.lib.styles import ParagraphStyle

from server.homework import parse_tutor_reply
from server.homework_pdf import build_homework_pdf,math_image,math_paragraph
from tests.test_homework import _CAPTURED_HOMEWORK_REPLY,sample_homework


@pytest.mark.parametrize('newline',['\n','\r\n','\r'])
def test_source_newlines_are_tex_whitespace_without_changing_rendered_math(newline):
    lines=[r'\frac{1}{2}+\frac{1}{3}',r'=\frac{3}{6}+\frac{2}{6}',r'=\frac{5}{6}.']
    assert math_image(newline.join(lines))==math_image(' '.join(lines))


@pytest.mark.parametrize('formula',[r'\because AB=AC,',r'\therefore \angle C=\angle B=50^\circ.'])
def test_geometry_reasoning_symbols_still_render(formula):
    data,width,height=math_image(formula)
    assert data.startswith(b'\x89PNG') and width>20 and height>5


def test_inline_formula_can_cross_a_cjk_line_boundary():
    style=ParagraphStyle('Regression',fontName='STSong-Light',fontSize=11,leading=20,wordWrap='CJK',autoLeading='max')
    paragraph=math_paragraph('已知三角形的角度'+r'\(\angle A=180^\circ-50^\circ-50^\circ=80^\circ\)'+'，结论正确。',style,maximum_width=180)
    width,height=paragraph.wrap(180,800)
    assert width==180 and height>20


@pytest.mark.parametrize('short,explicit',[
    (r'\frac58',r'\frac{5}{8}'),
    (r'\frac1{8}',r'\frac{1}{8}'),
    (r'\frac{5}8',r'\frac{5}{8}'),
    (r'\dfrac 5 8',r'\frac{5}{8}'),
    (r'\frac{\frac12}3',r'\frac{\frac{1}{2}}{3}'),
    (r'\frac\alpha2',r'\frac{\alpha}{2}'),
    (r'\displaystyle DG^2=\frac58',r'DG^2=\frac{5}{8}'),
])
def test_standard_tex_fraction_shorthand_renders_as_explicit_mathtext(short,explicit):
    assert math_image(short)==math_image(explicit)


def test_no_midpoint_feedback_with_standard_short_fractions_builds_pdf():
    from server.homework import Grading
    content=r'''主要问题：当前条件没有“G是EF中点”，不能使用斜边中线定理。

取反例：\(D=(0,0),E=(0,1),F=(1,0),G=(\frac14,\frac34)\)。

\[\displaystyle DG^2=(\frac14)^2+(\frac34)^2=\frac58,\quad EG^2=(\frac14)^2+(\frac14)^2=\frac18.\]

所以 \(DG\ne EG\)，当前条件不能推出结论。

若补充中点条件，则 \(DG=\frac12 EF=EG\)。'''
    grading=Grading.model_validate({'score':30,'basis':'错误加入中点条件，核心推理不成立。','items':[
        {'label':'判断G为中点','verdict':'incorrect','studentWork':'G在线段EF上，所以G为中点。','correction':r'\(DG^2=\frac58,EG^2=\frac18\)。'},
        {'label':'使用斜边中线定理','verdict':'incorrect','feedback':'需要中点条件。'},
    ]})
    document=PdfReader(io.BytesIO(build_homework_pdf(grading,content)))
    text=''.join(page.extract_text() for page in document.pages)
    assert '30 / 100' in text and '当前条件没有' in text and '规范解答' in text
    assert sum(len(page.images) for page in document.pages)>=5


@pytest.mark.parametrize('formula',[
    r'G=\left(\frac14,\frac34\right),',
    'DG^2=\\left(\\frac14\\right)^2+\\left(\\frac34\\right)^2=\\frac{5}{8},\\qquad\n'
    'EG^2=\\left(\\frac14\\right)^2+\\left(\\frac14\\right)^2=\\frac18.',
    r'DG\neq EG',
    r'DG=\frac12 EF=EG,',
])
def test_exact_latex_captured_from_live_proof_review_renders(formula):
    # These are the four KaTeX annotations from the real no-midpoint review.
    data,width,height=math_image(formula)
    assert data.startswith(b'\x89PNG') and width>0 and height>0


def test_pdf_failure_diagnostic_logs_exception_class_without_private_content(monkeypatch,caplog):
    from server import ai,homework_pdf
    grading,content,images=sample_homework()
    def fail(*args,**kwargs):raise ValueError('private student formula and credential must not be logged')
    monkeypatch.setattr(homework_pdf,'build_homework_pdf',fail)
    reply=asyncio.run(ai.tutor_response({'content':json.dumps({'mode':'homework','content':content,'grading':grading.model_dump()})},images,'zh'))
    assert reply['grading']['score']==75 and 'reportError' in reply and 'reportPdf' not in reply
    assert 'Homework PDF generation failed (ValueError)' in caplog.text
    assert 'private student' not in caplog.text and 'credential' not in caplog.text


def test_every_formula_in_actual_live_display_content_renders():
    formulas=re.findall(r'\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)',_CAPTURED_RENDER_CONTENT)
    assert len(formulas)>10
    assert any('\n=' in (display or inline) for display,inline in formulas)
    for display,inline in formulas:
        data,width,height=math_image(display or inline)
        assert data.startswith(b'\x89PNG') and width>0 and height>0


def test_actual_live_display_content_builds_complete_scored_report():
    grading=parse_tutor_reply(_CAPTURED_HOMEWORK_REPLY).grading
    data=build_homework_pdf(grading,_CAPTURED_RENDER_CONTENT,sample_homework()[2])
    document=PdfReader(io.BytesIO(data))
    text=''.join(page.extract_text() for page in document.pages)
    assert data.startswith(b'%PDF-') and '50 / 100' in text
    assert '逐项批注' in text and '规范解答' in text and '评分依据' in text
    assert '\ufffc' not in text
    assert len(document.pages)>=2 and sum(len(page.images) for page in document.pages)>10
    for page in document.pages:
        lines=[line.strip() for line in page.extract_text().splitlines() if line.strip() and not line.strip().isdigit() and line.strip()!='Geometry Assistant']
        assert not lines[-1].startswith('第 2 题：')


_CAPTURED_RENDER_CONTENT='本篇为两题，每题各 50 分。本次没有独立的评分标准，因此按每题 50 分的参考分值，并根据答案与推理的正确性给分。\n\n**第 1 题：正确，得 50 分。**\n\n学生作答：\\( \\angle C = 50^\\circ \\)，所以 \\( \\angle A = 180^\\circ - 50^\\circ - 50^\\circ = 80^\\circ \\)。\n\n判断：结论与推理均正确。由“等边对等角”，\\( AB=AC \\) 得 \\( \\angle C = \\angle B = 50^\\circ \\)，再由三角形内角和求出 \\( \\angle A = 80^\\circ \\)。建议补充“因为 \\( AB=AC \\)”这一依据。\n\n规范过程：\n\n已知：在 \\( \\triangle ABC \\) 中，\\( AB=AC \\)，\\( \\angle B=50^\\circ \\)。\n\n推导：\n\n\\[\n\\because AB=AC,\n\\]\n\n\\[\n\\therefore \\angle C=\\angle B=50^\\circ.\n\\]\n\n\\[\n\\angle A=180^\\circ-\\angle B-\\angle C\n=180^\\circ-50^\\circ-50^\\circ=80^\\circ.\n\\]\n\n结论：\\( \\angle A=80^\\circ \\)。\n\n**第 2 题：错误，得 0 分。**\n\n学生作答：\\( \\frac{1}{2}+\\frac{1}{3}=\\frac{1+1}{2+3}=\\frac{2}{5} \\)。\n\n判断：异分母分数不能把分子、分母分别相加，必须先通分，化成同分母分数后再相加。\n\n规范过程：\n\n\\[\n\\frac{1}{2}+\\frac{1}{3}\n=\\frac{1\\times 3}{2\\times 3}+\\frac{1\\times 2}{3\\times 2}\n=\\frac{3}{6}+\\frac{2}{6}\n=\\frac{5}{6}.\n\\]\n\n结论：\\( \\frac{1}{2}+\\frac{1}{3}=\\frac{5}{6} \\)。\n\n**评分依据：** 第 1 题过程和结果均正确，得 50 分；第 2 题计算错误，得 0 分。总分 \\( 50+0=50 \\) 分。'
