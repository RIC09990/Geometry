"""Coordinate givens are real constraints; incomplete diagrams never pass validation."""
import math
import pytest
import sympy as sp
from fastapi.testclient import TestClient
from pydantic import ValidationError
from server.algebra import holds
from server.constraints import ConstraintSystem
from server.coordinate_conditions import coordinate_statement
from server.main import app
from server.models import Point, Problem, Relation


def problem():
    return Problem.model_validate({
        'id':'coordinate-regression','title':'坐标给定的圆上动点','version':1,
        'points':[{'id':name,'x':x,'y':y} for name,x,y in [('O',0,0),('Q',1,0),('P',0,1),('A',-1,2),('B',2,0)]],
        'conditions':[
            {'id':'origin','kind':'fixed_point','args':['O'],'coordinates':[0,0]},
            {'id':'radius','kind':'fixed_length','args':['O','Q'],'value':1},
            {'id':'circle','kind':'on_circle','args':['P','O','Q']},
            {'id':'a','kind':'free_text','description':'定点 A(-1,2)'},
            {'id':'b','kind':'free_text','description':'B(2,0)'},
        ],
        'goal':{'id':'goal','kind':'minimize','args':['P','A','P','B'],'weights':[1,.5]},
        'nondegenerate':{'distinct':False,'triangles':[]},
    })


@pytest.mark.parametrize('text,name,xy',[
    ('定点 A(-1,2)','A',[-1,2]),
    ('定点 A(–1,2)','A',[-1,2]),
    ('已知点 B 的坐标为（2，0）。','B',[2,0]),
    (r'\(Q1=\left(-.5, +2e-1\right)\)','Q1',[-.5,.2]),
])
def test_coordinate_parser_recognizes_complete_statements(text,name,xy):
    assert coordinate_statement(text)==(name,xy)


@pytest.mark.parametrize('text',[
    'A(-1,2)，且 AB=3', 'A(-1,2) 或 A(1,2)', '若 A(-1,2)',
    'A(-1,2), B(2,0)', 'A(1/3,2)', 'A(NaN,2)', 'A(1e999,2)',
])
def test_partial_or_ambiguous_coordinate_statements_stay_unencoded(text):
    assert coordinate_statement(text) is None
    assert Relation(id='r',kind='free_text',description=text).kind=='free_text'


def test_old_import_coordinates_become_constraints_at_every_request_boundary():
    p=problem()
    assert p.conditions[3].kind=='fixed_point'
    p.points[3].x=50
    result=TestClient(app).post('/api/validate',json={'problem':p.model_dump()}).json()
    assert result['status']=='sat',result
    xy={q['id']:(q['x'],q['y']) for q in result['points']}
    assert xy['A']==(-1,2) and xy['B']==(2,0) and xy['O']==(0,0)
    assert math.dist(xy['P'],xy['O'])==pytest.approx(1)


def test_drag_does_not_override_coordinate_givens():
    p=problem()
    result=ConstraintSystem(p,normalize=False).layout(Point(id='A',x=-.9,y=2))
    assert result['status']=='unsat' and 'points' not in result


def test_unknown_retained_condition_blocks_whole_layout_but_disabled_one_does_not():
    p=problem()
    p.conditions.append(Relation(id='unknown',kind='free_text',description='某个尚未编码的关系'))
    client=TestClient(app)
    result=client.post('/api/validate',json={'problem':p.model_dump()}).json()
    assert result['status']=='unverified'
    assert result['unverifiedConditions']==['unknown'] and 'points' not in result
    p.conditions[-1].enabled=False
    assert client.post('/api/validate',json={'problem':p.model_dump()}).json()['status']=='sat'


def test_coordinate_givens_disable_wlog_translation_rotation_scale():
    p=problem()
    p.nondegenerate.triangles=[['O','A','B']]
    # Use an exact 2-unit distance, not a floating irrational equality.
    p.goal=Relation(id='goal',kind='fixed_length',args=['O','B'],value=2)
    assert ConstraintSystem(p).analyze()['outcome']=='proven'
    p.goal=Relation(id='goal',kind='fixed_length',args=['O','B'],value=3)
    result=ConstraintSystem(p).analyze()
    assert result['outcome']=='counterexample' and result['counterexample']['verified']


def test_independent_witness_verifier_checks_coordinates():
    condition=Relation(id='a',kind='fixed_point',args=['A'],coordinates=[-1,2])
    assert holds({'A':(sp.Integer(-1),sp.Integer(2))},condition)
    assert not holds({'A':(sp.Integer(1),sp.Integer(2))},condition)


@pytest.mark.parametrize('xy',[[1],[],[math.nan,0],[0,math.inf],[10001,0]])
def test_fixed_point_rejects_missing_nonfinite_and_out_of_range_coordinates(xy):
    with pytest.raises(ValidationError):Relation(id='a',kind='fixed_point',args=['A'],coordinates=xy)


def test_fixed_angle_without_triangle_domain_has_no_crashing_frame_fallback():
    p=problem()
    p.conditions=[Relation(id='angle',kind='fixed_angle',args=['O','A','B'],value=40)]
    result=ConstraintSystem(p,normalize=False,timeout=100).layout()
    assert result['status'] in ('sat','unknown')


def test_numeric_optimization_cannot_offer_a_point_excluded_by_another_condition():
    from server.optimization import locus_candidate
    p=problem()
    p.conditions.append(Relation(id='pinned-position',kind='fixed_point',args=['P'],coordinates=[0,1]))
    # The unconstrained objective reaches its first-locus minimum elsewhere.
    assert locus_candidate(p) is None
