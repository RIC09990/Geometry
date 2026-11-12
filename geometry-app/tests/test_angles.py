import math
import pytest
import z3
from fastapi.testclient import TestClient
from server.angles import cosine_constant
from server.models import Problem, Relation
from server.constraints import ConstraintSystem
from server.main import app
from server.topics import decode_import
import json


def angle_problem():
    return Problem.model_validate({'id':'angle-test','title':'角度与等长关系','version':1,
        'points':[{'id':'A','x':.5924,'y':.342},{'id':'B','x':0,'y':0},
                  {'id':'C','x':1,'y':0},{'id':'D','x':.5321,'y':0}],
        'segments':[{'id':s,'points':list(s)} for s in ['AB','AC','BC','AD']],
        'conditions':[{'id':'c40','kind':'fixed_angle','args':['A','C','B'],'value':40},
                      {'id':'a60','kind':'fixed_angle','args':['C','A','D'],'value':60},
                      {'id':'equal','kind':'equal_length','args':['B','D','A','C']},
                      {'id':'inside','kind':'on_segment','args':['D','B','C']}],
        'goal':{'id':'goal','kind':'angle_value','args':['A','B','C']},
        'nondegenerate':{'distinct':True,'triangles':[['A','B','C']]}})


def test_exact_cosine_has_unique_correct_root():
    ctx=z3.Context();c=cosine_constant(40,ctx)
    assert z3.is_algebraic_value(c)
    assert z3.is_true(z3.simplify(8*c**3-6*c+1==0))
    assert z3.is_true(z3.simplify(c>z3.RealVal('3/4',ctx=ctx)))


def test_angle_question_has_verified_thirty_degree_answer():
    result=ConstraintSystem(angle_problem(),timeout=15000).analyze()
    assert result['outcome']=='proven',result
    assert result['angleAnswer']['value']==30


def test_angle_display_satisfies_every_given():
    p=angle_problem()
    result=ConstraintSystem(p,timeout=10000,normalize=False).layout()
    assert result['status']=='sat',result
    xy={p['id']:(p['x'],p['y']) for p in result['points']}
    def angle(a,b,c):
        u=[xy[a][i]-xy[b][i] for i in [0,1]];v=[xy[c][i]-xy[b][i] for i in [0,1]]
        return math.degrees(math.acos(sum(x*y for x,y in zip(u,v))/(math.hypot(*u)*math.hypot(*v))))
    assert angle('A','C','B')==pytest.approx(40,abs=1e-7)
    assert angle('C','A','D')==pytest.approx(60,abs=1e-7)
    assert math.dist(xy['B'],xy['D'])==pytest.approx(math.dist(xy['A'],xy['C']),abs=1e-8)


def test_removing_equal_length_does_not_reuse_old_angle_answer():
    p=angle_problem();p.conditions[2].enabled=False
    result=ConstraintSystem(p).analyze()
    assert result['outcome']=='unknown',result
    assert 'angleAnswer' not in result


def test_wrong_angle_and_obtuse_supplement_are_not_proven():
    p=angle_problem()
    for value in [60,150]:
        p.goal=Relation(id='goal',kind='fixed_angle',args=['A','B','C'],value=value)
        system=ConstraintSystem(p,timeout=10000)
        assert system.solver.check()==z3.sat
        assert not system.entails(p.goal)


def test_import_normalizes_only_unambiguous_angle_spelling():
    raw=angle_problem().model_dump()
    raw['goal']['kind']='angle';raw['conditions'][0]['kind']='angle'
    reply=decode_import(json.dumps({'recognizedText':'求角B','problem':raw}))
    assert reply.problem is not None
    assert reply.problem.goal.kind=='angle_value'
    assert reply.problem.conditions[0].kind=='fixed_angle'


def test_drag_along_segment_with_rounded_angle_anchors():
    p=angle_problem()
    p.conditions[1].enabled=False;p.conditions[2].enabled=False
    # Actual rounded display from the reported custom topic. The 40° angle is
    # algebraic, so pinning every displayed decimal exactly is inconsistent.
    from server.models import Point
    values={'A':(-75.8045018441136,114.25594098836481),'B':(-80,-20),'C':(80,-25),'D':(0,-22.5)}
    p.points=[Point(id=name,x=xy[0],y=xy[1],fixed=name!='D') for name,xy in values.items()]
    for x in (29.23,60,-40):
        pinned=Point(id='D',x=x,y=-20-(x+80)/32)
        result=ConstraintSystem(p,normalize=False).layout(pinned,['A','B','C'],.00001)
        assert result['status']=='sat',result
        output={q['id']:q for q in result['points']}
        assert output['D']['x']==pytest.approx(x,abs=.00001)
        assert output['D']['y']==pytest.approx(pinned.y,abs=.00001)
        for name in ['A','B','C']:
            assert output[name]['fixed'] is True
            assert output[name]['x']==pytest.approx(values[name][0],abs=.00001)
            assert output[name]['y']==pytest.approx(values[name][1],abs=.00001)
    invalid=ConstraintSystem(p,normalize=False).layout(Point(id='D',x=0,y=5),['A','B','C'],.00001)
    assert invalid['status']=='unsat'


def test_condition_removal_preserves_valid_angle_drawing():
    p=angle_problem()
    original=ConstraintSystem(p,normalize=False).layout()
    assert original['status']=='sat',original
    from server.models import Point
    p.points=[Point.model_validate(q) for q in original['points']]
    p.conditions[1].enabled=False;p.conditions[2].enabled=False
    result=ConstraintSystem(p,normalize=False).layout()
    assert result['status']=='sat',result
    for before,after in zip(p.points,result['points']):
        assert after['x']==pytest.approx(before.x,abs=.00001)
        assert after['y']==pytest.approx(before.y,abs=.00001)


def test_reported_angle_problem_with_both_triangles_and_abd_goal():
    p=angle_problem();p.nondegenerate.triangles.append(['A','C','D']);p.goal.args=['A','B','D']
    result=ConstraintSystem(p).analyze()
    assert result['outcome']=='proven',result
    assert result['angleAnswer']=={'value':30,'args':['A','B','D']}


def test_angle_drag_timeout_uses_a_condition_preserving_layout_without_moving_anchors(monkeypatch):
    from server.models import Point
    p=angle_problem()
    result=ConstraintSystem(p,normalize=False).layout()
    assert result['status']=='sat',result
    p.points=[Point.model_validate(q) for q in result['points']]
    moved=next(q for q in p.points if q.id=='D')
    system=ConstraintSystem(p,normalize=False)
    monkeypatch.setattr(system.solver,'check',lambda:z3.unknown)
    result=system.layout(moved,['A','B','C'],.00001)
    assert result['status']=='sat',result
    for actual,expected in zip(result['points'],p.points):
        assert actual['id']==expected.id
        assert actual['x']==pytest.approx(expected.x,abs=.00001)
        assert actual['y']==pytest.approx(expected.y,abs=.00001)
    # The fallback cannot accept an inconsistent drag by silently relocating it.
    system=ConstraintSystem(p,normalize=False)
    monkeypatch.setattr(system.solver,'check',lambda:z3.unknown)
    result=system.layout(Point(id='D',x=.9,y=0),['A','B','C'],.00001)
    assert result['status']=='unknown' and result['message']!='unknown'


def test_internal_unknown_status_is_never_a_user_facing_message(monkeypatch):
    p=angle_problem();system=ConstraintSystem(p)
    monkeypatch.setattr(system.solver,'check',lambda:z3.unknown)
    monkeypatch.setattr(system.solver,'reason_unknown',lambda:'unknown')
    result=system.analyze()
    assert result['outcome']=='unknown' and '未完成' in result['message']
    assert result['solverReason']=='unknown'


@pytest.mark.parametrize('given',['shape','coordinates','length'])
def test_layout_verifies_a_mirrored_angle_drawing_in_its_display_frame(given):
    problem=angle_problem()
    # Triangle ABC has angles 30°, 40°, 110° and a unit base. The sine
    # rule gives the coordinates and the length of AC independently.
    angle=math.radians
    ab=math.sin(angle(40))/math.sin(angle(110))
    ac=math.sin(angle(30))/math.sin(angle(110))
    model={'A':ab*complex(math.cos(angle(30)),math.sin(angle(30))),
           'B':0j,'C':1+0j,'D':ac+0j}
    rotation=75+30j if given!='length' else 3+4j
    for point in problem.points:
        value=complex(232,-450)+rotation*model[point.id].conjugate()
        point.x,point.y=value.real,value.imag
    if given=='coordinates':
        problem.conditions.extend(
            Relation(id='coordinate-'+p.id,kind='fixed_point',args=[p.id],coordinates=[p.x,p.y])
            for p in problem.points if p.id in ('B','C')
        )
    elif given=='length':
        problem.conditions.append(Relation(id='metric-base',kind='fixed_length',args=['B','C'],value=5))

    pin=next(p for p in problem.points if p.id=='D')
    with TestClient(app) as client:
        response=client.post('/api/validate',json={
            'problem':problem.model_dump(),
            'pinned':pin.model_dump(),
            'fixedPoints':['A','B','C'],
            'pinTolerance':0.0002,
        })
    assert response.status_code==200
    result=response.json()
    assert result['status']=='sat',result
    xy={p['id']:complex(p['x'],p['y']) for p in result['points']}
    for p in problem.points:
        assert xy[p.id].real==pytest.approx(p.x,abs=0.0002,rel=0)
        assert xy[p.id].imag==pytest.approx(p.y,abs=0.0002,rel=0)
    assert abs(xy['A']-xy['C'])==pytest.approx(abs(xy['B']-xy['D']),abs=1e-9)
    if given=='coordinates':
        assert xy['B']==complex(232,-450)
        assert xy['C']==complex(307,-420)
    if given=='length':
        assert abs(xy['B']-xy['C'])==pytest.approx(5,abs=1e-9)
