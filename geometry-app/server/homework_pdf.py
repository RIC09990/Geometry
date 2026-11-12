"""Small in-memory ReportLab report; originals, marks, and typeset fractions."""
import base64
import io
import re
import copy
from html import escape
from threading import Lock
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Flowable, PageBreak, Table
from reportlab.lib.utils import ImageReader
from reportlab.lib.abag import ABag
from .homework import Grading

_render_lock=Lock()
pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))

def _tex_argument(formula,start):
    """Read a braced group or exactly one TeX token, preserving its meaning."""
    while start<len(formula) and formula[start].isspace():start+=1
    if start>=len(formula) or formula[start]=='}':return None
    if formula[start]=='{':
        depth=1;end=start+1
        while end<len(formula):
            if formula[end]=='\\':end+=2;continue
            if formula[end]=='{':depth+=1
            elif formula[end]=='}':
                depth-=1
                if depth==0:return formula[start:end+1],end+1
            end+=1
        return None
    if formula[start]=='\\':
        token=re.match(r'\\(?:[A-Za-z]+|.)',formula[start:])
        if not token:return None
        end=start+len(token.group())
    else:end=start+1
    return '{'+formula[start:end]+'}',end


def _explicit_fraction_arguments(formula):
    """Mathtext requires braces where TeX also permits one-token arguments."""
    # Normalize inner fractions first without moving earlier command offsets.
    for command in reversed(list(re.finditer(r'\\frac(?![A-Za-z])',formula))):
        numerator=_tex_argument(formula,command.end())
        denominator=_tex_argument(formula,numerator[1]) if numerator else None
        if numerator and denominator:
            formula=formula[:command.start()]+'\\frac'+numerator[0]+denominator[0]+formula[denominator[1]:]
    return formula


def _explicit_root_arguments(formula):
    # Do not group multiple unbraced digits: TeX's \sqrt16 means sqrt(1) * 6.
    for command in reversed(list(re.finditer(r'\\sqrt(?![A-Za-z])(?:\s*\[[^\]]*\])?',formula))):
        radicand=_tex_argument(formula,command.end())
        if radicand:
            formula=formula[:command.end()]+radicand[0]+formula[radicand[1]:]
    return formula


def _equation_annotations(formula):
    """Typeset equation numbers without exposing TeX-only layout commands."""
    numbers=[]
    for command in reversed(list(re.finditer(r'\\(tag\*?|label)(?![A-Za-z])',formula))):
        argument=_tex_argument(formula,command.end())
        if not argument:continue
        value,end=argument
        if command.group(1).startswith('tag'):
            number=value[1:-1]
            numbers.insert(0,number if command.group(1)=='tag*' else '('+number+')')
        formula=formula[:command.start()]+formula[end:]
    formula=re.sub(r'\\(?:notag|nonumber)(?![A-Za-z])','',formula)
    return formula+''.join(r'\qquad\mathrm{'+number+'}' for number in numbers)


def math_image(expression):
    from matplotlib.mathtext import math_to_image
    from matplotlib.font_manager import FontProperties
    formula=_equation_annotations(expression.strip()).replace('\\dfrac','\\frac').replace('\\tfrac','\\frac')
    formula=_explicit_fraction_arguments(formula)
    formula=_explicit_root_arguments(formula)
    aliases={'ge':'geq','le':'leq','ne':'neq'}
    formula=re.sub(r'\\(ge|le|ne)(?![A-Za-z])',lambda match:'\\'+aliases[match.group(1)],formula)
    formula=re.sub(r'\\displaystyle(?![A-Za-z])','',formula)
    formula=formula.replace('\\begin{aligned}','').replace('\\end{aligned}','').replace('&','')
    formula=formula.replace('∠','\\angle ').replace('△','\\triangle ').replace('°',r'^{\circ}')
    # TeX treats source newlines as whitespace. Mathtext instead rejects an
    # internal newline inside $...$, even when the equation itself is valid.
    # Explicit TeX row breaks are handled separately by math_paragraph.
    formula=re.sub(r'[\r\n]+',' ',formula)
    boxed=re.fullmatch(r'\\boxed\{([\s\S]*)\}',formula)
    if boxed:formula=boxed.group(1)
    output=io.BytesIO()
    math_to_image('$'+formula+'$',output,prop=FontProperties(size=11,math_fontfamily='stix'),dpi=288,format='png',color='#252a30')
    from PIL import Image,ImageOps,ImageDraw
    if boxed:
        picture=Image.open(io.BytesIO(output.getvalue())).convert('RGBA')
        picture=ImageOps.expand(picture,border=12,fill='white')
        ImageDraw.Draw(picture).rectangle((2,2,picture.width-3,picture.height-3),outline='#252a30',width=2)
        output=io.BytesIO();picture.save(output,format='PNG')
    width,height=Image.open(io.BytesIO(output.getvalue())).size
    return output.getvalue(),width/4,height/4


_MATH_PIECES=r'(\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$[^$\n]+\$)'


def _text_markup(text,ascii_font='Times-Roman'):
    """CJK CID fallback fonts have different Latin metrics in PDF viewers."""
    output=[]
    for part in re.split(r'([\x20-\x7e\u00a0-\u00ff]+)',text):
        value=escape(part)
        if part and re.fullmatch(r'[\x20-\x7e\u00a0-\u00ff]+',part):
            value='<font name="'+ascii_font+'">'+value+'</font>'
        output.append(value)
    return ''.join(output).replace('\n','<br/>')


def _prose_markup(text):
    parts=re.split(r'(\*\*[^\n]*?\*\*)',text)
    return ''.join('<b>'+_text_markup(part[2:-2])+'</b>' if index%2 else _text_markup(part)
                   for index,part in enumerate(parts))


def _math_lines(expression):
    """Only split layout environments whose rows are independent equations."""
    aligned=re.fullmatch(r'\s*\\begin\{(aligned|align\*?|gathered)\}([\s\S]*)\\end\{\1\}\s*',expression)
    if aligned:
        return [re.sub(r'(?<!\\)&','',line) for line in aligned.group(2).split('\\\\') if line.strip()]
    # Arrays and cases have delimiters/column semantics; do not invent separate
    # equations by splitting their rows.
    if '\\begin{' in expression:return [expression]
    return [line for line in expression.split('\\\\') if line.strip()]

def math_paragraph(text,style,maximum_width=477):
    # TeX is rendered before XML escaping; raw model HTML is never executed.
    pieces=re.split(_MATH_PIECES,text)
    fragments=[]
    for i,piece in enumerate(pieces):
        if i%2:
            expression=piece[2:-2] if piece.startswith(('$$','\\[','\\(')) else piece[1:-1]
            lines=_math_lines(expression)
            for line_index,line in enumerate(lines):
                if not line.strip():continue
                if line_index:fragments.extend(Paragraph('<br/>',style).frags)
                try:
                    # The math font does not contain CJK. Preserve such text in
                    # the embedded Chinese font instead of producing tofu boxes.
                    if re.search(r'[\u3400-\u9fff]',line):raise ValueError('CJK formula needs text fallback')
                    image,width,height=math_image(line)
                except (ValueError,RuntimeError,OverflowError):
                    # A report is for reading: never dump raw TeX into it. Keep
                    # an explicit placeholder if a formula truly cannot render,
                    # rather than silently deleting a mathematical premise.
                    label=('This formula could not be typeset. Please view it on the webpage.'
                           if getattr(style,'reportLanguage','zh')=='en' else '此公式暂未完成排版，请查看网页中的对应公式。')
                    prefix='<br/>' if fragments and not getattr(fragments[-1],'lineBreak',False) else ''
                    following=pieces[i+1] if i+1<len(pieces) else ''
                    suffix='<br/>' if following and not following.startswith(('\r','\n')) else ''
                    fragments.extend(Paragraph(prefix+'<font color="#626c75">'+_text_markup(label)+'</font>'+suffix,style).frags)
                    continue
                scale=min(1,maximum_width/max(width,1))
                # CJK line breaking calls ord() on each layout character. Give
                # the inline image an object placeholder instead of an empty
                # string; its cbDefn draws the image, never this placeholder.
                fragment=copy.copy(Paragraph('X',style).frags[0]);fragment.text='\ufffc'
                fragment.cbDefn=ABag(kind='img',image=ImageReader(io.BytesIO(image)),width=width*scale,height=height*scale,valign='middle')
                fragments.append(fragment)
        else:
            value=_prose_markup(piece)
            if value:fragments.extend(Paragraph(value,style).frags)
    return Paragraph(None,style,frags=fragments)

def markdown_flow(text,style):
    output=[]
    # Keep display equations intact when splitting paragraphs.
    blocks=[];pending=[]
    for index,piece in enumerate(re.split(_MATH_PIECES,text.strip())):
        if index%2:pending.append(piece);continue
        for part_index,part in enumerate(re.split(r'\n\s*\n',piece)):
            if part_index:
                blocks.append(''.join(pending));pending=[]
            pending.append(part)
    blocks.append(''.join(pending))
    for block in blocks:
        if not block:continue
        heading=re.match(r'^#{1,4}\s+(.+)',block)
        # Removing heading markup must not discard the following lines when
        # Markdown omits the optional blank line after a heading.
        value=re.sub(r'^#{1,4}[ \t]+','',block,count=1) if heading else block
        paragraph=math_paragraph(value,style);spacer=Spacer(1,7 if heading else 5)
        if (heading and '\n' not in value) or re.fullmatch(r'\*\*[^*\n]+\*\*',block):
            # Keep a standalone question heading with its following paragraph,
            # including the spacer, instead of leaving it at the foot of a page.
            paragraph.keepWithNext=spacer.keepWithNext=1
        output.extend([paragraph,spacer])
    return output

def draw_mark(canvas,x,y,verdict,size=9):
    canvas.setLineWidth(1.8)
    if verdict=='correct':
        canvas.setStrokeColor(colors.HexColor('#187553'))
        p=canvas.beginPath();p.moveTo(x-size*.65,y);p.lineTo(x-size*.15,y-size*.4);p.lineTo(x+size*.7,y+size*.65);canvas.drawPath(p)
    elif verdict=='incorrect':
        canvas.setStrokeColor(colors.HexColor('#b33f35'))
        canvas.line(x-size*.55,y-size*.55,x+size*.55,y+size*.55);canvas.line(x-size*.55,y+size*.55,x+size*.55,y-size*.55)
    else:
        canvas.setStrokeColor(colors.HexColor('#aa7829'));canvas.circle(x,y,size*.6,stroke=1,fill=0)

class MarkedPage(Flowable):
    def __init__(self,image,marks,width,height):
        super().__init__();self.reader=ImageReader(io.BytesIO(image));w,h=self.reader.getSize();scale=min(width/w,height/h)
        self.width=w*scale;self.height=h*scale;self.marks=marks
    def draw(self):
        c=self.canv;c.drawImage(self.reader,0,0,width=self.width,height=self.height,preserveAspectRatio=True)
        for number,item in self.marks:
            x=item.location.x*self.width;y=(1-item.location.y)*self.height
            draw_mark(c,x,y,item.verdict)
            c.setFont('Helvetica',8);c.setFillColor(colors.HexColor('#6b443d'));c.drawString(min(self.width-12,x+11),y,str(number))

class MarkIcon(Flowable):
    def __init__(self,verdict):super().__init__();self.verdict=verdict;self.width=18;self.height=20
    def draw(self):draw_mark(self.canv,8,9,self.verdict,size=7)

def build_homework_pdf(grading:Grading|None,content:str,images=(),language='zh'):
    # Matplotlib font caches are shared; serialize just document rendering.
    with _render_lock:
        buffer=io.BytesIO();doc=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=48,leftMargin=48,topMargin=44,bottomMargin=42,title='Geometry - Homework review' if grading else 'Geometry - AI answer',author='Geometry Assistant')
        body=ParagraphStyle('Body',fontName='STSong-Light',fontSize=11,leading=20,textColor=colors.HexColor('#252a30'),wordWrap='CJK',alignment=TA_LEFT,spaceAfter=4,autoLeading='max')
        body.reportLanguage=language
        title=ParagraphStyle('Title',parent=body,fontSize=24,leading=32,spaceAfter=15)
        small=ParagraphStyle('Small',parent=body,fontSize=9,leading=15,textColor=colors.HexColor('#626c75'))
        english=language=='en'
        if grading:
            heading=(('Homework score: ' if english else '作业得分：')+f'{grading.score:g} / {grading.maximum:g}') if grading.score is not None else ('Homework feedback' if english else '作业批改')
            flow=[Paragraph(_text_markup(heading,'Helvetica'),title),Paragraph(_text_markup('Geometry Assistant - AI reference feedback' if english else 'Geometry 小助手 · AI 参考批改'),small)]
            if grading.basis:flow+=markdown_flow(grading.basis,body)
        else:
            flow=[Paragraph(_text_markup('Geometry · AI Answer' if english else 'Geometry · AI 解答','Helvetica'),title)]
        for image_index,image in enumerate(images):
            if image_index:flow.append(PageBreak())
            label=('Original work - Page ' if grading else 'Attachment - Page ') if english else ('原作业 · 第 ' if grading else '原始附件 · 第 ')
            flow.extend([Spacer(1,10),Paragraph(_text_markup(label+str(image_index+1)+('' if english else ' 页')),small),Spacer(1,8)])
            data=base64.b64decode(image.dataUrl.split(',',1)[1])
            marks=[(i+1,item) for i,item in enumerate(grading.items if grading else []) if item.location and item.location.imageIndex==image_index]
            flow.append(MarkedPage(data,marks,499,560))
        if images:flow.append(PageBreak())
        if grading:flow.extend([Paragraph(_text_markup('Feedback by item' if english else '逐项批注','Helvetica'),title),Spacer(1,6)])
        labels={'correct':'Correct','incorrect':'Incorrect','partial':'Partly correct','unclear':'Unclear'} if english else {'correct':'正确','incorrect':'有误','partial':'部分正确','unclear':'无法判断'}
        for i,item in enumerate(grading.items if grading else []):
            color='#187553' if item.verdict=='correct' else '#b33f35' if item.verdict=='incorrect' else '#aa7829'
            flow.append(Table([[MarkIcon(item.verdict),Paragraph(f'<font color="{color}">'+_text_markup(f'{i+1}. {item.label} · {labels[item.verdict]}')+'</font>',body)]],colWidths=[22,477],style=[('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0)]))
            if item.studentWork:flow+=markdown_flow(('Student work: ' if english else '学生作答：')+item.studentWork,body)
            if item.feedback:flow+=markdown_flow(item.feedback,body)
            if item.correction:flow+=markdown_flow(('Correction: ' if english else '订正：')+item.correction,body)
            flow.append(Spacer(1,9))
        if grading:
            flow.extend([Spacer(1,10),Paragraph(_text_markup('Worked solution' if english else '规范解答','Helvetica'),title)])
            content=re.sub(r'^\s*(?:\*\*)?(?:作业得分|Homework score)[^\n]*\n*','',content,flags=re.I)
        flow+=markdown_flow(content,body)
        def footer(canvas,document):
            canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#76808a'))
            canvas.drawString(48,24,'Geometry Assistant');canvas.drawRightString(A4[0]-48,24,str(document.page))
        doc.build(flow,onFirstPage=footer,onLaterPages=footer)
        return buffer.getvalue()
