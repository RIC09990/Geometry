"""Exact right-angle translation through the installed, unmocked Newclid."""
import pytest
import z3

from server.constraints import ConstraintSystem
from server.models import Problem,Relation
from server.proofs import newclid


def right_triangle():
    return Problem.model_validate({
        'id':'custom-right-angle','title':'直角三角形斜边中点','version':1,
        'points':[{'id':name,'x':x,'y':y} for name,x,y in [('D',0,0),('E',4,0),('F',0,3),('G',2,1.5)]],
        'conditions':[
            {'id':'right-angle','kind':'fixed_angle','args':['E','D','F'],'value':90},
            {'id':'hypotenuse-midpoint','kind':'midpoint','args':['G','E','F']},
        ],
        'goal':{'id':'goal','kind':'equal_length','args':['E','G','D','G']},
        'nondegenerate':{'distinct':False,'triangles':[]},
    })


@pytest.mark.parametrize('reversed_rays',[False,True])
def test_real_newclid_uses_exact_right_angle_to_prove_hypotenuse_midpoint(reversed_rays):
    problem=right_triangle()
    if reversed_rays:problem.conditions[0].args=['F','D','E']
    original=problem.model_dump()
    result=newclid(problem)
    assert result['status']=='found',result
    assert result['steps'] and result['raw'] and 'Z3' in result['verification']
    assert set(result['assumptionIds'])=={'right-angle','hypotenuse-midpoint'}
    assert any('right-angle' in node['premises'] and '⟂' in node['statement'] for node in result['assumptionNodes'])
    assert any('Hypotenuse is diameter' in step['rule'] for step in result['steps'])
    assert problem.model_dump()==original


def test_right_angle_goal_uses_existing_perpendicular_premise_without_new_assumptions():
    problem=right_triangle()
    problem.conditions=[Relation(id='given-perpendicular',kind='perpendicular',args=['E','D','D','F'])]
    problem.goal=Relation(id='goal',kind='fixed_angle',args=['E','D','F'],value=90)
    result=newclid(problem)
    assert result['status']=='found',result
    assert result['assumptionIds']==['given-perpendicular']


@pytest.mark.parametrize('degrees',[45,60,89,91,120])
def test_other_fixed_angles_remain_explicitly_unsupported(degrees):
    problem=right_triangle();problem.conditions[0].value=degrees
    result=newclid(problem)
    assert result['status']=='unsupported',result
    assert 'fixed_angle' in result['message']


def test_disabled_right_angle_is_not_reintroduced_from_the_drawing():
    problem=right_triangle();problem.conditions[0].enabled=False
    result=newclid(problem)
    assert result['status']!='found',result
    assert ConstraintSystem(problem).analyze()['outcome']=='counterexample'


def test_right_angle_and_perpendicular_encoding_are_equivalent_even_without_domain_guards():
    problem=right_triangle();problem.conditions=[]
    system=ConstraintSystem(problem,normalize=False)
    right=Relation(id='right',kind='fixed_angle',args=['E','D','F'],value=90)
    perp=Relation(id='perp',kind='perpendicular',args=['E','D','D','F'])
    system.solver.add(z3.Xor(system.encode(right),system.encode(perp)))
    assert system.solver.check()==z3.unsat


@pytest.mark.parametrize('collapsed',['E','F'])
def test_translated_right_angle_does_not_admit_a_zero_length_ray(collapsed):
    problem=right_triangle();problem.conditions=[]
    system=ConstraintSystem(problem,normalize=False)
    right=Relation(id='right',kind='fixed_angle',args=['E','D','F'],value=90)
    perp=Relation(id='perp',kind='perpendicular',args=['E','D','D','F'])
    system.solver.add(system.d2(collapsed,'D')==0)
    for relation in [right,perp]:
        system.solver.push();system.solver.add(system.encode(relation))
        assert system.solver.check()==z3.unsat
        system.solver.pop()
