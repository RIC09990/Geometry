"""Recognize complete, unambiguous coordinate statements in older imports.

Never mine numbers from arbitrary prose: a partial match could discard an
additional mathematical condition. Anything outside this grammar stays text.
"""
import math
import re

NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
COORDINATE = re.compile(
    rf'(?:(?:已知)?(?:定点|点))?\s*([A-Z][0-9]?)\s*'
    rf'(?:(?:的)?坐标(?:为|是))?\s*(?:=|为)?\s*'
    rf'\(\s*({NUMBER})\s*,\s*({NUMBER})\s*\)\s*[。.;；]?'
)


def coordinate_statement(description):
    text = str(description).strip().translate(str.maketrans({'（':'(', '）':')', '，':',', '−':'-', '–':'-'}))
    if text.startswith('\\(') and text.endswith('\\)'):text=text[2:-2].strip()
    elif text.startswith('$') and text.endswith('$'):text=text.strip('$').strip()
    text=text.replace('\\left','').replace('\\right','')
    match=COORDINATE.fullmatch(text)
    if not match:return None
    coordinates=[float(match[2]),float(match[3])]
    if not all(math.isfinite(v) and abs(v)<=10000 for v in coordinates):return None
    return match[1],coordinates
