"""Exporting a readable reply must not depend on a score or one TeX feature."""
import io
import re

import pytest
from PIL import Image
from pypdf import PdfReader
from reportlab.lib.styles import ParagraphStyle

from server.homework_pdf import build_homework_pdf, math_image, math_paragraph
from tests.test_homework import sample_homework


def document(data):
    reader=PdfReader(io.BytesIO(data))
    return reader, '\n'.join(page.extract_text() for page in reader.pages)


def test_unscored_reply_exports_without_inventing_a_score_or_feedback_items():
    data=build_homework_pdf(None, '## 解答\n这行不能因为标题后没有空行而消失。\n结论成立。')
    reader,text=document(data)
    assert data.startswith(b'%PDF-') and len(reader.pages)==1
    assert 'Geometry · AI 解答' in text
    assert '这行不能因为标题后没有空行而消失' in text and '结论成立' in text
    assert '作业得分' not in text and '暂无法评分' not in text and '逐项批注' not in text


def test_unscored_export_keeps_original_image_pixels_without_grading_marks():
    picture=sample_homework()[2][0]
    reader,text=document(build_homework_pdf(None, '已检查原图中的解答。', [picture]))
    assert '原始附件 · 第 1 页' in text and '已检查原图中的解答' in text
    assert any(image.image.size==(850,1050) for page in reader.pages for image in page.images)
    assert '作业得分' not in text


@pytest.mark.parametrize('formula', [
    r'f(x)=\begin{cases}x^2,&x\ge0\\-x,&x<0\end{cases}',
    r'A=\begin{array}{cc}1&2\\3&4\end{array}',
    r'\notAMathtextCommand{a+b}=c',
    r'x=1\quad\text{当条件成立时}',
])
def test_unrenderable_formula_never_dumps_tex_source_or_silently_disappears(formula):
    reader,text=document(build_homework_pdf(None, '前文。\n\n\\['+formula+'\\]\n\n后文完整保留。'))
    assert reader.pages and '前文' in text and '后文完整保留' in text
    assert '此公式暂未完成排版' in text
    assert '公式原文' not in text and '排版兼容' not in text and '\\' not in text


def test_boxed_result_is_typeset_with_a_visible_border():
    unboxed,_,_=math_image(r'\sqrt{10}')
    boxed,_,_=math_image(r'\boxed{\sqrt{10}}')
    base=Image.open(io.BytesIO(unboxed));picture=Image.open(io.BytesIO(boxed)).convert('RGB')
    assert picture.width==base.width+24 and picture.height==base.height+24
    assert picture.getpixel((2,2))==(37,42,48)
    _,text=document(build_homework_pdf(None,r'最终答案：\(\boxed{\sqrt{10}}\)。'))
    assert '公式原文' not in text


def test_aligned_equations_use_separate_lines_and_keep_formula_images():
    style=ParagraphStyle('Test',fontName='STSong-Light',fontSize=11,leading=20,wordWrap='CJK',autoLeading='max')
    one=math_paragraph(r'\[x=1\]',style)
    two=math_paragraph(r'\[\begin{aligned}x&=1\\y&=2\end{aligned}\]',style)
    assert two.wrap(477,720)[1]>=one.wrap(477,720)[1]+15
    reader,text=document(build_homework_pdf(None,r'\[\begin{aligned}x&=1\\y&=2\end{aligned}\]'))
    assert sum(len(page.images) for page in reader.pages)==2
    assert '公式原文' not in text


def test_blank_lines_within_display_math_do_not_erase_formula_delimiters():
    reader,text=document(build_homework_pdf(None,'Before.\n\n\\[\n\\frac{1}{2}\n\n+\\frac{1}{3}=\\frac{5}{6}\n\\]\n\nAfter.','',language='en'))
    assert 'Before.' in text and 'After.' in text
    assert 'Formula source' not in text and sum(len(page.images) for page in reader.pages)==1


def test_export_escapes_model_html_and_preserves_the_text_instead_of_executing_it():
    _,text=document(build_homework_pdf(None,'<img src="https://example.com/private.png"/>\n<script>alert(1)</script>'))
    assert '<script>alert(1)</script>' in text


def test_existing_scored_report_still_contains_marks_score_and_solution():
    grading,content,images=sample_homework()
    reader,text=document(build_homework_pdf(grading,content,images))
    assert '75 / 100' in text and '逐项批注' in text and '规范解答' in text
    assert len(reader.pages)>=2 and sum(len(page.images) for page in reader.pages)>5


@pytest.mark.parametrize(('short','explicit'),[
    (r'\sqrt6',r'\sqrt{6}'),
    (r'\sqrt 6',r'\sqrt{6}'),
    (r'\sqrt\alpha',r'\sqrt{\alpha}'),
    (r'\sqrt[3]8',r'\sqrt[3]{8}'),
    (r'\sqrt[3] 8',r'\sqrt[3]{8}'),
    (r'\sqrt16',r'\sqrt{1}6'),
    (r'\sqrt{\sqrt6}',r'\sqrt{\sqrt{6}}'),
    (r'\frac{6-\sqrt6}{10}',r'\frac{6-\sqrt{6}}{10}'),
    (r'x\ge0',r'x\geq0'),
    (r'x\le0',r'x\leq0'),
    (r'x\ne0',r'x\neq0'),
])
def test_standard_tex_root_arguments_and_relation_aliases_keep_exact_notation(short,explicit):
    assert math_image(short)==math_image(explicit)


def test_alias_normalization_does_not_replace_prefix_of_unknown_command():
    formula=r'x\nefarious{a+b}'
    _,text=document(build_homework_pdf(None,'\\['+formula+'\\]'))
    assert '此公式暂未完成排版' in text and 'nefarious' not in text


def test_formula_placeholder_delimiter_whitespace_does_not_add_empty_lines():
    style=ParagraphStyle('Test',fontName='STSong-Light',fontSize=11,leading=20,wordWrap='CJK',autoLeading='max')
    compact=math_paragraph('前文。\n\\[\\unknown{x}\\]\n后文。',style)
    spaced=math_paragraph('前文。\n\\[\n\n\\unknown{x}\n\n\\]\n后文。',style)
    assert compact.wrap(477,720)[1]==spaced.wrap(477,720)[1]


@pytest.mark.parametrize(('numbered','rendered'),[
    (r'\angle BAC+2x+2y=180^\circ.\tag{1}',r'\angle BAC+2x+2y=180^\circ.\qquad\mathrm{(1)}'),
    (r'2x+2y+2\angle BOC=360^\circ.\tag{2}',r'2x+2y+2\angle BOC=360^\circ.\qquad\mathrm{(2)}'),
    (r'\frac{a+b}{2}=5\tag*{A}',r'\frac{a+b}{2}=5\qquad\mathrm{A}'),
    (r'x=1\label{eq:first}\tag{3}',r'x=1\qquad\mathrm{(3)}'),
    (r'x=1\notag',r'x=1'),
    (r'x=1\nonumber',r'x=1'),
])
def test_equation_numbers_render_as_math_instead_of_exposing_source(numbered,rendered):
    assert math_image(numbered)==math_image(rendered)


def test_screenshot_angle_bisector_derivation_keeps_all_numbered_equations():
    content=r'''你的证明整体是正确的。

\[\angle BAC+2x+2y=180^\circ.\tag{1}\]

在三角形BOC中，\(x+y+\angle BOC=180^\circ\)。两边乘以2，得

\[2x+2y+2\angle BOC=360^\circ.\tag{2}\]

用（2）减（1），得

\[2\angle BOC-\angle BAC=180^\circ,\]

即\(\angle BOC=90^\circ+\frac12\angle BAC\)。'''
    reader,text=document(build_homework_pdf(None,content))
    assert '整体是正确的' in text and '用（2）减（1）' in text
    assert '公式原文' not in text and '\\tag' not in text and '暂未完成排版' not in text
    assert sum(len(page.images) for page in reader.pages)==5


def test_english_unrenderable_formula_has_no_source_dump():
    _,text=document(build_homework_pdf(None,r'Before. \[\unknown{x}\] After.',language='en'))
    assert 'could not be typeset' in text and 'Before.' in text and 'After.' in text
    assert 'Formula source' not in text and '\\unknown' not in text


# Actual Flash Max reply captured during export acceptance, 2026-11-10.
_CAPTURED_FLASH_MAX_REPLY=r'''### 原题解答

设 \(M=(x,y)\)，则 \(x^2+y^2=1\)。取辅助点 \(P=(-2,0)\)。计算：
\[
MA^2=\left(x+\frac12\right)^2+y^2=x^2+y^2+x+\frac14=\frac54+x,
\]
\[
MP^2=(x+2)^2+y^2=x^2+y^2+4x+4=5+4x=4\left(\frac54+x\right)=4MA^2.
\]
所以 \(MP=2MA\)，从而
\[
2|MA|+|MB|=|MP|+|MB|\ge |PB|.
\]
当且仅当 \(P,M,B\) 共线且 \(M\) 在线段 \(PB\) 上时取等号。线段 \(PB\) 与单位圆确实有交点：令 \(M=(-2+3t,t)\)，代入 \(x^2+y^2=1\) 得
\[
10t^2-12t+3=0,
\]
在 \(0<t<1\) 中有根 \(t=\frac{6-\sqrt6}{10}\)，故最小值可以取到。因此
\[
\min(2|MA|+|MB|)=|PB|=\sqrt{(1+2)^2+(1-0)^2}=\sqrt{10}.
\]
答案：\(\boxed{\sqrt{10}}\)。

### 两个检查

① 在通常角度（或弧度）取实数意义下，两者等价。因为由
\[
2\angle BOC=\angle BAC+180^\circ
\]
两边同除以 \(2\)，得
\[
\angle BOC=\frac{\angle BAC+180^\circ}{2}=90^\circ+\frac12\angle BAC.
\]
反过来，将第二式两边同乘 \(2\) 即得第一式。若另有“角度取模 \(360^\circ\)”等特殊约定，则要结合该约定判断；按常规几何角度，二者等价。

② 不正确。通分计算为
\[
\frac12+\frac13=\frac36+\frac26=\frac56\ne\frac25.
\]
\(\frac25\) 相当于错误地把分子、分母分别相加，不能这样算。'''


def test_actual_flash_max_reply_typesets_every_formula_without_source_fallback():
    reader,text=document(build_homework_pdf(None,_CAPTURED_FLASH_MAX_REPLY))
    assert '公式原文' not in text and 'layout compatibility' not in text
    assert '原题解答' in text and '两个检查' in text and '不能这样算' in text
    assert sum(len(page.images) for page in reader.pages)>=20
