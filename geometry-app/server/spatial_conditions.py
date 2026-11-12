"""Complete spatial statements, including old explicit unsupported notices.

Never discard a trailing condition or infer an interior point from its sketch.
"""
import re

POINT=r'[A-Z][0-9]?'
INTERIOR=re.compile(rf'(?:已知\s*)?(?:点\s*)?({POINT})\s*(?:在|位于)\s*(?:△|Δ|三角形)\s*({POINT})\s*({POINT})\s*({POINT})\s*(?:的)?\s*(?:内部|内)(?:\s*[（(]不含边界[）)])?\s*[。.;；]?')
NOTICE=re.compile(r'[“「"](.+?)[”」"]\s*(?:无法用当前已定义的几何关系直接精确表达，已用\s*free_text\s*条件保留|当前没有直接的内点关系，已用\s*free_text\s*保留)\s*[。.;；]?')

def spatial_statement(description):
    text=str(description).strip()
    notice=NOTICE.fullmatch(text)
    if notice:text=notice[1].strip()
    if text.startswith('\\(') and text.endswith('\\)'):text=text[2:-2].strip()
    elif text.startswith('$') and text.endswith('$'):text=text.strip('$').strip()
    text=text.replace('\\triangle','△')
    match=INTERIOR.fullmatch(text)
    if match and len(set(match.groups()))==4:return {'kind':'inside_triangle','args':list(match.groups())}
    return None
