"""Independent multi-point pressure problems with algebraically known answers.

These fixtures exercise trajectories, dependent points, strict regions, multiple
reflections and weighted sums. The expected answers come from geometric bounds,
not the implementation's numerical search or the user's screenshot.
"""
import math
import pytest
import sympy as sp
from server.models import Problem,Relation
from server.constraints import ConstraintSystem
from server.optimization import analyze_minimum,inversion_certificate,path_certificate,reflection_path_certificate,certify


def make_problem(name,points,moving,conditions,args,weights,triangles=(),distinct=False):
    fixed=[{'id':'fix-'+key,'kind':'fixed_point','args':[key],'coordinates':list(xy)} for key,xy in points.items() if key not in moving]
    return Problem.model_validate({'id':'custom-pressure-'+name,'title':name,'version':1,
        'points':[{'id':key,'x':xy[0],'y':xy[1]} for key,xy in points.items()],
        'conditions':fixed+conditions,'goal':{'id':'goal','kind':'minimize','args':list(args),'weights':weights},
        'nondegenerate':{'distinct':distinct,'triangles':[list(t) for t in triangles]}})


def double_circle(arc=False):
    points={'C':(-5,0),'D':(5,0),'O':(-2,0),'U':(-1,0),'V':(2,0),'W':(2,1),'P':(-2,1),'Q':(2,1),'A':(-6,-2),'B':(6,-2),'H':(0,5)}
    conditions=[{'id':'circle-p','kind':'on_circle','args':list('POU')},{'id':'circle-q','kind':'on_circle','args':list('QVW')},
        {'id':'inside-p','kind':'inside_triangle','args':list('PABH')},{'id':'inside-q','kind':'inside_triangle','args':list('QABH')},
        {'id':'same','kind':'same_side','args':list('PQAB')}]
    if arc:
        points['S']=(-2,1);conditions[0]={'id':'circle-p','kind':'on_arc','args':list('POUS')}
    return make_problem('双圆双动点路径'+('含弧端点' if arc else ''),points,'PQ',conditions,'CPPQQD',[2.5]*3,['ABH'])


def weighted_midpoint(radius=3,focus=1,other=(2,3)):
    k=radius/focus
    points={'O':(0,0),'U':(radius,0),'A':(-focus,0),'B':other,'P':(0,radius),'M':(-focus/2,radius/2)}
    conditions=[{'id':'circle','kind':'on_circle','args':list('POU')},{'id':'midpoint','kind':'midpoint','args':list('MPA')}]
    return make_problem('圆上动点中点联动六项加权和',points,'PM',conditions,'MAMPPAPBBPPB',[1,1,k-1,.25,.5,.25])


def ratio_midpoint():
    points={'A':(0,0),'B':(3,0),'D':(2,3),'P':(4,2),'M':(2,1)}
    conditions=[{'id':'apollonius','kind':'length_ratio','args':list('PAPB'),'value':2},
        {'id':'midpoint','kind':'midpoint','args':list('MPA')},{'id':'outside','kind':'outside_circle','args':list('PAB')},
        {'id':'inside','kind':'inside_circle','args':list('MAB')},{'id':'side','kind':'same_side','args':list('PDAB')}]
    return make_problem('阿氏圆与中点联动及内外区域加权和',points,'PM',conditions,'MAMD',[.5,1],['MAB'])


def reflections(count=2,weight=1):
    points={'A':(-3,0),'B':(9,0),'E':(6,-2),'F':(6,9),'C':(0,3),'D':(2,5),'P':(3.75,0),'Q':(6,1.8)}
    conditions=[{'id':'first','kind':'on_segment','args':list('PAB')},{'id':'second','kind':'on_segment','args':list('QEF')}]
    args='CPPQQD';moving='PQ'
    if count==3:
        points.update({'C':(0,2),'G':(-1,7),'H':(9,7),'P':(20/11,0),'Q':(6,4.6),'R':(42/11,7)})
        conditions.append({'id':'third','kind':'on_segment','args':list('RGH')});args='CPPQQRRD';moving='PQR'
    else:
        conditions.extend([{'id':'side','kind':'same_side','args':list('PQAC')},{'id':'outside','kind':'outside_circle','args':list('PCA')},{'id':'inside','kind':'inside_circle','args':list('QDE')}])
    return make_problem(f'{count}次反射与{count}动点加权折线',points,moving,conditions,args,[weight]*(count+1),['ACE'],True)


def pressure_cases():
    return [
        ('双圆双动点及严格内点',double_circle(),sp.Integer(25)),
        ('双圆圆弧含取等端点',double_circle(True),sp.Integer(25)),
        ('六项加权中点联动',weighted_midpoint(),sp.sqrt(130)),
        ('不同半径与权重的联动',weighted_midpoint(5,1,(4,2)),13*sp.sqrt(5)),
        ('阿氏圆区域约束与中点联动',ratio_midpoint(),sp.sqrt(37)/2),
        ('双动点连续反射',reflections(),2*sp.sqrt(41)),
        ('不同权重的连续反射',reflections(2,1.75),sp.Rational(7,2)*sp.sqrt(41)),
        ('三动点三次反射',reflections(3,1.25),sp.Rational(5,4)*sp.sqrt(221)),
    ]


@pytest.mark.parametrize('name,problem,expected',pressure_cases(),ids=lambda value:value if isinstance(value,str) else None)
def test_independent_pressure_problems_have_exact_global_bounds_and_attainment(name,problem,expected):
    result=analyze_minimum(problem)
    assert result['outcome']=='optimized',(name,result)
    optimization=result['optimization'];assert optimization['certificate']['verified']
    assert sp.simplify(sp.sympify(optimization['minimum'])-expected)==0
    assert optimization['value']==pytest.approx(float(expected),rel=1e-12)
    assert all(proof['status']=='verified' for proof in result['proofs'])


def test_multiple_moving_points_do_not_hide_any_region_or_endpoint_constraint():
    problem=double_circle(True)
    assert path_certificate(problem)['optimization']['value']==25
    problem.nondegenerate.distinct=True
    assert path_certificate(problem) is None  # P=U is excluded; an infimum is not an attained minimum.
    problem=double_circle();problem.conditions.append(Relation(id='opposite',kind='opposite_side',args=list('PQCD')))
    assert path_certificate(problem) is None


def test_deleting_the_link_or_a_fixed_endpoint_invalidates_the_old_certificate():
    problem=weighted_midpoint();next(r for r in problem.conditions if r.id=='midpoint').enabled=False
    assert inversion_certificate(problem) is None
    problem=double_circle();next(r for r in problem.conditions if r.id=='fix-C').enabled=False
    assert path_certificate(problem) is None
    problem=reflections();next(r for r in problem.conditions if r.id=='first').enabled=False
    assert reflection_path_certificate(problem) is None


def test_reflection_cannot_ignore_an_extra_original_condition_at_the_equality_point():
    problem=reflections();problem.conditions.append(Relation(id='exclude',kind='fixed_point',args=['P'],coordinates=[0,0]))
    assert reflection_path_certificate(problem) is None


def test_rational_rotation_translation_renaming_and_term_order_preserve_the_new_problem():
    problem=reflections(3,1.25);raw=problem.model_dump()
    # Use valid one-letter point names, all different from the original order.
    names={p.id:chr(ord('Z')-i) for i,p in enumerate(problem.points)}
    def transform(x,y):return (31+3*x/5-4*y/5,-17+4*x/5+3*y/5)
    for point in raw['points']:
        point['id']=names[point['id']];point['x'],point['y']=transform(point['x'],point['y'])
    for r in raw['conditions']:
        r['args']=[names[name] for name in r['args']]
        if r['kind']=='fixed_point':r['coordinates']=list(transform(*r['coordinates']))
    pairs=[raw['goal']['args'][i:i+2] for i in range(0,len(raw['goal']['args']),2)]
    raw['goal']['args']=[names[name] for pair in pairs[::-1] for name in pair[::-1]]
    raw['nondegenerate']['triangles']=[[names[name] for name in triangle] for triangle in raw['nondegenerate']['triangles']]
    result=analyze_minimum(Problem.model_validate(raw))
    assert result['outcome']=='optimized',result
    # The transformed decimals are exactly those declared in the new premises.
    assert result['optimization']['value']==pytest.approx(5*math.sqrt(221)/4,abs=1e-10)


def test_a_nearby_guessed_radical_is_rejected_by_exact_global_certification():
    problem=ratio_midpoint()
    assert certify(problem,sp.sqrt(37)/2)['verified']
    assert not certify(problem,sp.sqrt(37)/2+sp.Rational(1,10**8))['verified']
    assert not certify(problem,sp.sqrt(37)/2-sp.Rational(1,10**8))['verified']
