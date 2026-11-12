"""Structured homework feedback. A question without student work is not graded."""
import json
import ast
import re
from fractions import Fraction
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class MarkLocation(BaseModel):
    imageIndex:int=Field(ge=0)
    x:float=Field(ge=0,le=1)
    y:float=Field(ge=0,le=1)

class HomeworkItem(BaseModel):
    label:str
    verdict:Literal['correct','incorrect','partial','unclear']
    studentWork:str=''
    feedback:str=''
    correction:str=''
    location:MarkLocation|None=None

class Grading(BaseModel):
    score:float|None=Field(default=None,ge=0)
    maximum:float|None=Field(default=100,gt=0)
    basis:str=''
    items:list[HomeworkItem]=Field(default_factory=list)

    @model_validator(mode='after')
    def score_range(self):
        if self.score is not None:
            if self.maximum is None:raise ValueError('提供得分时须同时提供满分')
            if self.score>self.maximum:raise ValueError('得分不能超过满分')
        return self

class TutorReply(BaseModel):
    mode:Literal['solution','homework','conversation']='solution'
    content:str
    grading:Grading|None=None
    searchQuery:str|None=Field(default=None,max_length=400)
    exportPdf:bool=False

def tutor_instructions(review=False):
    """A compact output contract; the real user message remains the last turn."""
    return (
        '按用户最新请求回答，只使用相关历史。普通问题正常回答；只发题目时给标准、完整的解答；'
        '发自己的解答时按数学含义检查，正确就认可，错误则指出具体原因并给出改正。'
        '等价变形和不同解法都应认可，不为挑错而挑错；结论正确与推理成立分别判断。'
        '不清楚的信息先问，不编造。需要实时资料时先返回 searchQuery 请求查询；地点等必要信息缺失时先询问。'
        +('本次明确要求检查学生作答。' if review else '')+
        '只返回一个JSON：{"mode":"conversation|solution|homework","content":"Markdown正文","searchQuery":null,"grading":null,"exportPdf":false}。'
        '请求查询时只填 searchQuery，正文留空；获得资料后直接回答并引用来源。公式用 LaTeX。'
        '仅当最新请求是在检查、批改或订正学生自己的作答时，mode填homework，并填写grading.items；'
        '普通提问、题目求解和知识讲解的mode填solution或conversation，grading为null，exportPdf为false。'
        '历史里曾批改过作业不代表本次仍需批改，不能复用历史的评分、题目或PDF。'
        '批改不要求分数时score为null；用户明确要求评分时才给分数。'
        '批改的grading格式：'
        '{"score":得分或null,"maximum":满分或null,"basis":"判断或评分依据","items":['
        '{"label":"题号","verdict":"correct|incorrect|partial|unclear","studentWork":"学生原答",'
        '"feedback":"判断依据","correction":"必要的订正","location":null}]}。'
        '图片批注位置可填 {"imageIndex":从0开始,"x":0到1,"y":0到1}，不能定位则null。'
        'PDF 文件由 Geometry 应用生成，不声称不能生成 PDF，不编造下载链接。'
    )


class TutorReplyFormatError(ValueError):
    """The provider returned a broken tutor envelope instead of an answer."""


def _tutor_json_source(content):
    source=content.strip()
    fenced=re.fullmatch(r'```(?:json)?[ \t]*\r?\n(.*?)\r?\n```',source,re.I|re.S)
    return fenced[1] if fenced else source


def homework_verification_instructions(draft:TutorReply):
    # Do not feed the model its own proposed correction as an answer to imitate.
    return ('这次批改的判断或评分未通过一致性检查。请独立重新核对原始作答，'
            '保留题号和学生原意，按数学含义判断；正确的等价表达不能扣分。'
            '不能确定就说明，不能猜分。正文、逐项判断和总分须一致。'
            '按原JSON格式返回；PDF由应用生成，不要声称不能生成 PDF。')


def has_grading_payload(content:str):
    """Distinguish optional feedback without scoring from malformed score data."""
    try:data=read_ai_json(_tutor_json_source(content))
    except (ValueError,TypeError):return False
    if not isinstance(data,dict):return False
    body=re.sub(r'[*#_]','',str(data.get('content','')))
    return data.get('grading') is not None or bool(_SCORE_CLAIM.search(body) or _LEADING_SCORE_CLAIM.match(body))


def checked_homework_reply(content:str,draft:TutorReply):
    reply=parse_tutor_reply(content,add_score=False)
    if reply.mode!='homework' or not reply.grading:
        raise ValueError('Independent homework review is incomplete')
    if not reply.grading.items:
        if reply.grading.score is not None:raise ValueError('Score has no supporting items')
        # Unscored prose is a valid review or PDF document, not a failed grade.
        verified_score_content(reply.content,reply.grading)
        reply.grading=None
        return reply
    if reply.grading.score is not None and reply.grading.score==reply.grading.maximum and any(item.verdict in ('incorrect','partial','unclear') for item in reply.grading.items):
        raise ValueError('Independent homework score contradicts item verdicts')
    if any(item.verdict=='correct' and false_numeric_equality(item.studentWork) for item in reply.grading.items):
        raise ValueError('Independent review accepted a false arithmetic equality')
    # The first model transcription and item labels are not mathematical facts.
    # A review may correct OCR or reorganize item labels; check its own content.
    reply.content=verified_score_content(reply.content,reply.grading)
    return reply


_SCORE_LABEL=r'(?:作业(?:得分|成绩)|总(?:得分|成绩|分)|最终(?:得分|成绩)|合计得分|(?:homework|total|overall|final)\s+(?:score|grade))'
_LEADING_SCORE_LABEL=rf'(?:{_SCORE_LABEL}|得分|成绩|score|grade)'
_SCORE_NUMBER=r'\d+(?:\.\d+)?'
_SCORE_VALUE=rf'(?P<score>{_SCORE_NUMBER})(?:\s*(?:/|out\s+of)\s*(?P<maximum>{_SCORE_NUMBER}))?(?P<percent>\s*[%％])?'
_SCORE_BOUNDARY=r'(?!\d|\.\d|\s*(?:[+/=\-]|\*(?!\*)))'
_SCORE_AFTER_LABEL=rf'\s*(?:(?:[:：=]|为|是|is|was)\s*)?'+_SCORE_VALUE+_SCORE_BOUNDARY
_SCORE_CLAIM=re.compile('(?P<label>'+_SCORE_LABEL+')'+_SCORE_AFTER_LABEL,re.I)
_LEADING_SCORE_CLAIM=re.compile(r'^\s*(?P<label>'+_LEADING_SCORE_LABEL+')'+_SCORE_AFTER_LABEL,re.I)
_SCORE_HEADING=re.compile(r'^\s*(?:#{1,6}\s*)?(?:\*\*|__)?'+_LEADING_SCORE_LABEL+rf'\s*[:：]?\s*(?:{_SCORE_VALUE}'+_SCORE_BOUNDARY+r'|暂无法评分|无法评分|not\s+(?:yet\s+)?(?:available|graded))\s*(?:\*\*|__)?[。.]?\s*',re.I)


def verified_score_content(content:str,grading:Grading):
    """Keep explicit overall score claims consistent with the checked grade."""
    plain=re.sub(r'\\[()[\]]|\*\*|__|[$#]','',content)
    plain=re.sub(r'\\(?:frac|dfrac|tfrac)\{('+_SCORE_NUMBER+r')\}\{('+_SCORE_NUMBER+r')\}',r'\1/\2',plain)
    claims=list(_SCORE_CLAIM.finditer(plain))
    leading=_LEADING_SCORE_CLAIM.match(plain)
    if leading:claims.append(leading)
    for claim in claims:
        # Bare 总分 can describe the worksheet's maximum, not earned marks.
        if claim['label']=='总分' and not claim['maximum'] and not claim['percent']:continue
        score=Fraction(claim['score']);maximum=Fraction(claim['maximum']) if claim['maximum'] else None
        expected=Fraction(str(grading.score)) if grading.score is not None else None
        if re.search(r'\b(?:maximum(?:\s+possible)?|full[- ]mark)\s*$',plain[:claim.start()],re.I):
            expected=Fraction(str(grading.maximum))
        if claim['percent'] and expected is not None:expected=expected/Fraction(str(grading.maximum))*100
        if expected is None or score!=expected or (maximum is not None and maximum!=Fraction(str(grading.maximum))):
            raise ValueError('Independent review text contradicts its score')
    english=bool(re.match(r'\s*(?:[#*_]\s*)*(?:(?:homework|total|overall|final)\s+)?(?:score|grade)',content,re.I))
    score=f'{grading.score:g}/{grading.maximum:g}' if grading.score is not None else ('Not yet graded' if english else '暂无法评分')
    heading=('Homework score: ' if english else '作业得分：')+score
    body=_SCORE_HEADING.sub('',content,count=1).strip()
    if grading.score is None:return body
    return '**'+heading+'**'+ ('\n\n'+body if body else '')


def false_numeric_equality(work:str):
    """Reject demonstrably false pure arithmetic, without evaluating model code.

    Anything involving prose, variables or unsupported notation is left to the
    independent reviewer. This guard never invents a corrected score.
    """
    if len(work)>500 or re.search(r'\.{2,}|…|⋯|\\(?:ldots|cdots|dots)\b',work):return False
    expression=work.strip().rstrip('。.')
    for marker in ('\\(','\\)','\\[','\\]','$','\\left','\\right'):
        expression=expression.replace(marker,'')
    for _ in range(12):
        expanded=re.sub(r'\\(?:frac|dfrac|tfrac)\{([^{}]+)\}\{([^{}]+)\}',r'((\1)/(\2))',expression)
        if expanded==expression:break
        expression=expanded
    for marker,value in (('\\times','*'),('\\cdot','*'),('\\div','/'),('×','*'),('÷','/'),('−','-')):
        expression=expression.replace(marker,value)
    if '=' not in expression or not re.fullmatch(r'[0-9+*/().=\s-]+',expression):return False
    def rational(source):
        source=source.strip();tree=ast.parse(source,mode='eval')
        if sum(1 for _ in ast.walk(tree))>80:raise ValueError('Arithmetic expression too complex')
        def number(node):
            if isinstance(node,ast.Constant) and type(node.value) in (int,float):return Fraction(ast.get_source_segment(source,node))
            if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
                value=number(node.operand);return -value if isinstance(node.op,ast.USub) else value
            if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
                left,right=number(node.left),number(node.right)
                if isinstance(node.op,ast.Add):return left+right
                if isinstance(node.op,ast.Sub):return left-right
                if isinstance(node.op,ast.Mult):return left*right
                return left/right
            raise ValueError('Not pure arithmetic')
        return number(tree.body)
    try:
        values=[rational(part) for part in expression.split('=')]
        return any(value!=values[0] for value in values[1:])
    except (ValueError,TypeError,SyntaxError,ZeroDivisionError,OverflowError):return False

# These TeX commands begin with a valid JSON escape character. In an already
# malformed JSON string, treating them as \b, \f, \n, \r or \t destroys formulas.
_LATEX_JSON_ESCAPE_WORDS=set('''
    backslash bar because begin beta big bigg binom bmod boldsymbol bot boxed breve bullet
    fbox flat forall frac
    nabla ne neg neq not nu
    rangle rbrace rceil rfloor rho right rm roman
    tau text textbf textit textnormal textrm textsf textstyle texttt tfrac therefore
    theta tilde times tiny to top triangle triangleq tt
'''.split())


def _repair_json_string_escapes(source):
    """Repair string escapes only; never infer JSON structure or execute content."""
    output=[];in_string=False;i=0
    while i<len(source):
        char=source[i]
        if char=='"':
            in_string=not in_string;output.append(char);i+=1;continue
        if not in_string:
            output.append(char);i+=1;continue
        if ord(char)<32:
            output.append(json.dumps(char)[1:-1]);i+=1;continue
        if char!='\\':
            output.append(char);i+=1;continue
        following=source[i+1:i+2]
        end=i+1
        while end<len(source) and source[end].isascii() and source[end].isalpha():end+=1
        word=source[i+1:end]
        valid_unicode=following=='u' and len(source[i+2:i+6])==4 and all(c in '0123456789abcdefABCDEF' for c in source[i+2:i+6])
        if following and (following in '"\\/' or (following in 'bfnrt' and word not in _LATEX_JSON_ESCAPE_WORDS) or valid_unicode):
            # Consume a pair together so escaped quotes and double backslashes
            # cannot change string boundaries or be escaped a second time.
            output.append(source[i:i+2]);i+=2
        else:
            output.append('\\\\');i+=1
    return ''.join(output)


def read_ai_json(source):
    """Decode one reply, also accepting exact repeated copies from a provider.

    Never combine fields or choose between conflicting answers. Preserve the
    strict JSON path so valid escaped text and control characters are unchanged.
    """
    try:return json.loads(source)
    except (ValueError,TypeError):pass
    decoder=json.JSONDecoder()
    for candidate in (source,_repair_json_string_escapes(source)):
        try:
            first,end=decoder.raw_decode(candidate.lstrip())
            remaining=candidate.lstrip()[end:].strip()
            if not remaining:return first
            if not isinstance(first,dict):continue
            for _ in range(7):
                repeated,end=decoder.raw_decode(remaining)
                if repeated!=first:raise ValueError('Conflicting AI reply objects')
                remaining=remaining[end:].strip()
                if not remaining:return first
        except (ValueError,TypeError):pass
    raise ValueError('Incomplete or conflicting AI JSON')


def parse_tutor_reply(content,*,add_score=True):
    source=_tutor_json_source(content)
    try:data=read_ai_json(source)
    except (ValueError,TypeError):
        # Never promote a broken envelope to assistant text. Ordinary Markdown
        # (including fenced code that is itself the answer) remains readable.
        if re.match(r'^\s*(?:\{\s*(?:"|$)|\[\s*\{)',source) or (
                re.match(r'```(?:json)?[ \t]*\r?\n',source,re.I)
                and re.search(r'"(?:mode|content|grading|searchQuery|exportPdf)"\s*:',source)):
            raise TutorReplyFormatError('Invalid tutor JSON') from None
        if not source.strip():
            raise TutorReplyFormatError('Empty tutor reply') from None
        return TutorReply(content=content)
    if not isinstance(data,dict):
        if isinstance(data,list) and any(isinstance(item,dict) and 'content' in item for item in data):
            raise TutorReplyFormatError('Multiple tutor replies')
        return TutorReply(content=content)
    try:
        reply=TutorReply.model_validate({'content':'',**data})
    except (ValueError,TypeError):
        # A bad grade must not hide an otherwise readable answer or create a
        # fabricated score/report. Preserve only validated user-facing content.
        if not isinstance(data.get('content'),str):
            raise TutorReplyFormatError('Invalid tutor content') from None
        mode=data.get('mode')
        reply=TutorReply(content=data['content'],mode=mode if mode in ('solution','homework','conversation') else 'solution',exportPdf=data.get('exportPdf') is True)
    if reply.searchQuery is not None:
        reply.searchQuery=reply.searchQuery.strip() or None
    if not reply.content.strip() and not reply.searchQuery:
        raise TutorReplyFormatError('Empty tutor reply')
    if reply.mode!='homework':reply.grading=None
    if reply.grading and reply.grading.score is not None and add_score:
        g=reply.grading
        score=f'{g.score:g}/{g.maximum:g}' if g.score is not None else '暂无法评分'
        if not reply.content.lstrip().lstrip('*').lstrip().startswith(('作业得分','Homework score')):
            reply.content='**作业得分：'+score+'**\n\n'+reply.content
    return reply
