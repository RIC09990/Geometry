"""Display placement stays near a user's drag despite decimal round-off."""
import json
from pathlib import Path
import math
from server.models import LayoutRequest,Problem,Point
from server.constraints import ConstraintSystem

DATA=json.loads((Path(__file__).resolve().parents[1]/'data/cases.json').read_text(encoding='utf8'))
def preset(index):
    return Problem.model_validate({k:v for k,v in DATA[index].items() if k not in ['description','tag']})

def test_midpoints_do_not_send_the_figure_offscreen_after_a_decimal_drag():
    p=preset(1)
    p.points[-1].x=1.573813375092
    # The positions below mimic a JSXGraph drag and native midpoint updates.
    positions={'A':(.127346017,3.53628181),'B':(-3.,-1.5),'C':(3.147626750184,-.570019832)}
    positions['D']=tuple((a+b)/2 for a,b in zip(positions['A'],positions['B']))
    positions['E']=tuple((a+b)/2 for a,b in zip(positions['A'],positions['C']))
    # Deliberately include the last-bit error introduced by screen conversion.
    positions['E']=(positions['E'][0]+1e-14,positions['E'][1])
    p.points=[Point(id=id,x=xy[0],y=xy[1]) for id,xy in positions.items()]
    result=ConstraintSystem(p,normalize=False).layout(next(q for q in p.points if q.id=='C'))
    assert result['status']=='sat'
    for q in result['points']:
        assert math.dist((q['x'],q['y']),positions[q['id']])<.0001
    assert ConstraintSystem(p).analyze()['outcome']=='proven'

def test_isosceles_keeps_all_vertices_near_the_released_shape():
    p=preset(0)
    b=(-3.13103947,-1.500019)
    c=(3.576189,-.929191)
    m=tuple((u+v)/2 for u,v in zip(b,c));dx=c[0]-b[0];dy=c[1]-b[1]
    a=(m[0]-dy*.75,m[1]+dx*.75)
    positions={'A':a,'B':b,'C':c,'D':m}
    p.points=[Point(id=id,x=xy[0],y=xy[1]) for id,xy in positions.items()]
    result=ConstraintSystem(p,normalize=False).layout(next(q for q in p.points if q.id=='C'))
    assert result['status']=='sat'
    assert all(math.dist((q['x'],q['y']),positions[q['id']])<.0001 for q in result['points'])

def test_display_tolerance_never_weakens_a_theorem_condition():
    p=preset(0)
    for r in p.conditions:
        if r.id in ['midpoint','altitude']:r.enabled=False
    result=ConstraintSystem(p).analyze()
    assert result['outcome']=='counterexample'
    assert result['counterexample']['verified']

def test_fixed_display_anchors_remain_exact_but_are_not_proof_premises():
    p=preset(1)
    p.points[0]=Point(id='A',x=.197133,y=3.891919)
    a,b,c=p.points[:3]
    p.points[3]=Point(id='D',x=(a.x+b.x)/2,y=(a.y+b.y)/2)
    p.points[4]=Point(id='E',x=(a.x+c.x)/2,y=(a.y+c.y)/2)
    result=ConstraintSystem(p,normalize=False).layout(a,['B','C'])
    assert result['status']=='sat'
    for fixed in [b,c]:
        q=next(q for q in result['points'] if q['id']==fixed.id)
        assert q['x']==fixed.x and q['y']==fixed.y

def test_circle_glider_roundoff_accepts_a_nearby_exact_layout_without_moving_fixed_points():
    p=preset(0)
    # Rotate B on the circle centred at A through C, then round screen coordinates.
    a,b,c,d=p.points;radius=math.dist((a.x,a.y),(c.x,c.y));theta=-2.2
    b.x=round(a.x+radius*math.cos(theta),12);b.y=round(a.y+radius*math.sin(theta),12)
    d.x=(b.x+c.x)/2;d.y=(b.y+c.y)/2
    result=ConstraintSystem(p,normalize=False).layout(b,['A','C'],.00001)
    assert result['status']=='sat',result
    for q in result['points']:
        before=next(v for v in p.points if v.id==q['id'])
        assert math.dist((q['x'],q['y']),(before.x,before.y))<.0001

def test_full_placement_verifies_more_than_eight_vertices():
    p=preset(0)
    p.points.extend(Point(id=id,x=10+i,y=2) for i,id in enumerate('EFGHIJK'))
    request=LayoutRequest(problem=p,fixedPoints=[point.id for point in p.points],pinTolerance=.00001)
    result=ConstraintSystem(request.problem,normalize=False).layout(fixed_points=request.fixedPoints,pin_tolerance=request.pinTolerance)
    assert result['status']=='sat',result
    assert len(result['points'])==11
