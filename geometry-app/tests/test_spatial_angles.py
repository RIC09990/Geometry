import json
import math
from pathlib import Path
import pytest
import sympy as sp
import z3
from server.models import Problem,Relation
from server.constraints import ConstraintSystem
from server.algebra import holds
from server.topics import decode_import
from server.spatial_conditions import spatial_statement
from server.angle_construction import exact_angle_models,analyze_constructed_angle


def angle_grid(angles=(30,40,20,50)):
    return Problem.model_validate({'id':'custom-angle-grid','title':'多射线角约束','version':1,
        'points':[{'id':i,'x':x,'y':y} for i,x,y in [('A',0,3),('B',-2,0),('C',2,0),('D',-.5,1)]],
        'conditions':[{'id':f'a{i}','kind':'fixed_angle','args':list(a),'value':v} for i,(a,v) in enumerate(zip(['ABD','DBC','BCD','DCA'],angles))]+[{'id':'inside','kind':'inside_triangle','args':list('DABC')}],
        'goal':{'id':'goal','kind':'angle_value','args':list('DAC')},'nondegenerate':{'distinct':True,'triangles':[list('ABC')]}})


def measured(points,args):
    xy={p['id']:(p['x'],p['y']) for p in points};a,b,c=args
    u=[xy[a][i]-xy[b][i] for i in (0,1)];v=[xy[c][i]-xy[b][i] for i in (0,1)]
    return math.degrees(math.atan2(abs(u[0]*v[1]-u[1]*v[0]),u[0]*v[0]+u[1]*v[1]))


@pytest.mark.parametrize('sentence',['D在△ABC内部','点 D 位于三角形 A B C 的内部。',r'\(D在\triangle ABC内\)','“D在△ABC内部”无法用当前已定义的几何关系直接精确表达，已用 free_text 条件保留。'])
def test_complete_interior_statements_upgrade_every_boundary(sentence):
    assert spatial_statement(sentence)=={'kind':'inside_triangle','args':list('DABC')}
    relation=Relation(id='inside',kind='free_text',args=[],description=sentence)
    assert relation.kind=='inside_triangle' and relation.args==list('DABC')


@pytest.mark.parametrize('sentence',['D在△ABC内部，且 AD=BD','D在△ABC内部或边上','假设D在△ABC内部，那么角A为30°','D在△ABC内部？','D在△ABA内部'])
def test_extra_conditions_or_ambiguity_are_never_discarded(sentence):
    assert spatial_statement(sentence) is None


def test_old_unsupported_notice_does_not_become_a_second_hidden_premise():
    raw=angle_grid().model_dump();raw['conditions'][-1]={'id':'inside','kind':'free_text','args':[],'description':'D在△ABC内部'}
    warning='“D在△ABC内部”无法用当前已定义的几何关系直接精确表达，已用 free_text 条件保留。'
    raw['conditions'].append({'id':'old-warning','kind':'free_text','args':[],'description':warning})
    problem=Problem.model_validate(raw)
    assert [r.id for r in problem.conditions if r.kind=='inside_triangle']==['inside']
    reply=decode_import(json.dumps({'recognizedText':'角格点','problem':raw,'unsupported':[warning]},ensure_ascii=False))
    assert reply.problem and not reply.unsupported
    assert [r.id for r in reply.problem.conditions if r.kind=='inside_triangle']==['inside']


@pytest.mark.parametrize('kind,args,valid,invalid',[
    ('inside_triangle','PABC',(1,1),(4,4)),('inside_circle','POA',(1,1),(5,0)),
    ('outside_circle','POA',(5,0),(1,1)),('same_side','PQAB',(1,1),(1,-1)),('opposite_side','PQAB',(1,-1),(1,1)),
])
def test_spatial_relations_have_matching_exact_encoders(kind,args,valid,invalid):
    coords={'O':(0,0),'A':(4,0),'B':(0,0),'C':(0,4),'P':valid,'Q':(1,2)}
    # For the side predicates, AB is horizontal and Q is above it.
    p=Problem.model_validate({'id':'spatial','title':'空间条件','version':1,'points':[{'id':k,'x':x,'y':y} for k,(x,y) in coords.items()],
        'conditions':[],'goal':{'id':'goal','kind':kind,'args':list(args)},'nondegenerate':{'distinct':False,'triangles':[]}})
    relation=p.goal
    for position,expected in [(valid,True),(invalid,False)]:
        current={**coords,'P':position};exact={k:tuple(sp.Rational(str(x)) for x in v) for k,v in current.items()}
        assert bool(holds(exact,relation)) is expected
        system=ConstraintSystem(p,normalize=False)
        substitutions=[(variable,z3.RealVal(str(value),ctx=system.ctx)) for name,point in current.items() for variable,value in zip(system.xy[name],point)]
        assert z3.is_true(z3.simplify(z3.substitute(system.encode(relation),*substitutions))) is expected


@pytest.mark.parametrize('reflect,rotate,scale',[(False,0,1),(True,.43,7),(False,1.1,.2)])
def test_grid_constructs_all_original_conditions_without_sketch_premises(reflect,rotate,scale):
    p=angle_grid()
    for point in p.points:
        x,y=point.x,(-point.y if reflect else point.y)
        point.x=17+scale*(x*math.cos(rotate)-y*math.sin(rotate));point.y=-11+scale*(x*math.sin(rotate)+y*math.cos(rotate))
    result=ConstraintSystem(p).analyze()
    assert result['outcome']=='proven' and result['angleAnswer']['value']==30
    assert result['angleCertificate']['verified']
    display=ConstraintSystem(p,normalize=False).layout()
    assert display['status']=='sat',display
    for r in p.conditions:
        if r.kind=='fixed_angle':assert measured(display['points'],r.args)==pytest.approx(r.value,abs=1e-8)


def test_point_renaming_and_relations_in_another_order_do_not_change_the_solver():
    raw=angle_grid().model_dump();rename=dict(zip('ABCD','WXYZ'))
    for point in raw['points']:point['id']=rename[point['id']]
    for r in [*raw['conditions'],raw['goal']]:r['args']=[rename[a] for a in r['args']]
    raw['conditions']=raw['conditions'][::-1]
    raw['nondegenerate']['triangles']=[[rename[a] for a in t] for t in raw['nondegenerate']['triangles']]
    result=ConstraintSystem(Problem.model_validate(raw)).analyze()
    assert result['angleAnswer']=={'value':30,'args':list('ZWY')}


@pytest.mark.parametrize('angles',[(20,30,40,50),(40,20,30,40),(30,30,30,30),(10,20,30,40)])
def test_other_multi_angle_frameworks_are_solved_from_their_conditions(angles):
    p=angle_grid(angles);p.goal.args=list('BAC')
    result=ConstraintSystem(p).analyze()
    assert result['outcome']=='proven',result
    assert result['angleAnswer']['value']==180-sum(angles)


def test_extra_constraints_filter_every_branch_and_contradictions_cannot_be_proven():
    p=angle_grid();p.conditions.append(Relation(id='outside',kind='opposite_side',args=list('ADBC')))
    result=ConstraintSystem(p).analyze()
    assert result['outcome']=='inconsistent',result
    p=angle_grid();p.conditions[-1].enabled=False
    constructed=exact_angle_models(p)
    assert constructed is not None and len(constructed['models'])>2
    result=analyze_constructed_angle(p)
    assert result['outcome']=='unknown' and 'angleAnswer' not in result


def test_incomplete_construction_and_metric_conditions_use_the_general_solver():
    p=angle_grid();p.conditions[0].enabled=False
    assert exact_angle_models(p) is None
    p=angle_grid();p.conditions.append(Relation(id='length',kind='fixed_length',args=list('BC'),value=7))
    assert exact_angle_models(p) is None


def nested_angle_framework():
    p=angle_grid()
    from server.models import Point
    p.points.extend([Point(id='E',x=-.5,y=.5),Point(id='F',x=0,y=.4),Point(id='G',x=-.8,y=1.6)])
    for id,args,value in [('e1','EBC',20),('e2','BCE',30),('f1','FBC',10),('f2','BCF',40),('g1','GBD',15),('g2','GCD',10)]:
        p.conditions.append(Relation(id=id,kind='fixed_angle',args=list(args),value=value))
    for point in 'EFG':p.conditions.append(Relation(id='inside'+point,kind='inside_triangle',args=list(point+'ABC')))
    p.conditions.extend([Relation(id='branch-b',kind='same_side',args=list('GABD')),Relation(id='branch-c',kind='same_side',args=list('GACD'))])
    p.goal.args=list('GBE')
    return p


def test_seven_point_nested_framework_checks_unused_points_and_both_branch_conditions():
    p=nested_angle_framework();result=ConstraintSystem(p).analyze()
    assert result['outcome']=='proven',result
    assert result['angleAnswer']['value']==35
    display=ConstraintSystem(p,normalize=False).layout();assert display['status']=='sat',display
    for r in p.conditions:
        if r.kind=='fixed_angle':assert measured(display['points'],r.args)==pytest.approx(r.value,abs=1e-8)


def test_seven_point_display_verifies_the_current_mirrored_branch(monkeypatch):
    cases=json.loads((Path(__file__).parent/'fixtures'/'competition-geometry.json').read_text(encoding='utf8'))
    p=Problem.model_validate(next(case['problem'] for case in cases if case['name']=='七点多重角度与区域约束'))
    for point in p.points:point.y=-point.y
    p.points[-1].x+=.000001
    system=ConstraintSystem(p,normalize=False)
    monkeypatch.setattr(system.solver,'check',lambda:z3.unknown)
    result=system.layout(fixed_points=[point.id for point in p.points],pin_tolerance=.00001)
    assert result['status']=='sat',result
    actual={point['id']:point for point in result['points']}
    for point in p.points:
        assert actual[point.id]['x']==pytest.approx(point.x,abs=.00001)
        assert actual[point.id]['y']==pytest.approx(point.y,abs=.00001)
    for r in p.conditions:
        if r.kind=='fixed_angle':assert measured(result['points'],r.args)==pytest.approx(r.value,abs=1e-8)


def test_switching_a_region_changes_the_answer_instead_of_reusing_the_old_result():
    p=nested_angle_framework();next(r for r in p.conditions if r.id=='branch-b').kind='opposite_side'
    result=ConstraintSystem(p).analyze();assert result['outcome']=='proven',result
    assert result['angleAnswer']['value']==5
    p=nested_angle_framework();next(r for r in p.conditions if r.id=='branch-b').enabled=False
    result=ConstraintSystem(p).analyze();assert result['outcome']=='unknown' and 'angleAnswer' not in result,result
