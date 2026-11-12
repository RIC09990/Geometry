"""Exact ratio and mirror-agnostic triangle similarity regressions."""
import sympy as sp
import pytest
import z3
from pydantic import ValidationError

from server.algebra import holds
from server.constraints import ConstraintSystem
from server.models import Problem, Relation
from server.proofs import newclid


def relation(kind, args, **extra):
    return Relation(id='test', kind=kind, args=args, **extra)


def coordinates(values):
    return {name: tuple(map(sp.Rational, xy)) for name, xy in values.items()}


@pytest.mark.parametrize('value', [None, 0, -1, float('nan'), float('inf')])
def test_ratio_requires_a_finite_positive_value(value):
    with pytest.raises(ValidationError):
        relation('length_ratio', ['A', 'B', 'C', 'D'], value=value)


def test_exact_ratio_is_not_confused_with_its_square_or_inverse():
    xy=coordinates({'A':(0,0),'B':(3,0),'C':(0,2),'D':(2,2)})
    assert holds(xy,relation('length_ratio',['A','B','C','D'],value=1.5))
    assert not holds(xy,relation('length_ratio',['A','B','C','D'],value=2.25))
    assert not holds(xy,relation('length_ratio',['A','B','C','D'],value=2/3))
    assert not holds(xy,relation('length_ratio',['A','B','C','C'],value=1.5))


@pytest.mark.parametrize('reflected',[False,True])
def test_similarity_keeps_correspondence_and_allows_both_orientations(reflected):
    xy=coordinates({'A':(0,0),'B':(2,0),'C':(0,1),'D':(5,5),'E':(9,5),'F':(5,3 if reflected else 7)})
    assert holds(xy,relation('similar_triangles',['A','B','C','D','E','F']))
    assert not holds(xy,relation('similar_triangles',['A','B','C','D','F','E']))
    xy['F']=(sp.Rational(7),sp.Rational(5))
    assert not holds(xy,relation('similar_triangles',['A','B','C','D','E','F']))


def nested_triangles(reflected=False):
    values={'A':(0,4),'B':(0,0),'C':(-4 if reflected else 4,0),
            'D':(0,2),'E':(-2 if reflected else 2,2)}
    return Problem(id='similarity-general',title='中点构造子母型相似',version=1,
        points=[{'id':name,'x':x,'y':y} for name,(x,y) in values.items()],
        segments=[{'id':a+b,'points':[a,b]} for a,b in [('A','B'),('A','C'),('B','C'),('D','E')]],
        conditions=[{'id':'mid-ab','kind':'midpoint','args':['D','A','B']},
                    {'id':'mid-ac','kind':'midpoint','args':['E','A','C']}],
        goal={'id':'goal','kind':'similar_triangles','args':['A','D','E','A','B','C']},
        nondegenerate={'distinct':True,'triangles':[['A','B','C']]})


@pytest.mark.parametrize('reflected',[False,True])
def test_midpoint_child_triangle_is_similar_without_assuming_the_target(reflected):
    problem=nested_triangles(reflected)
    system=ConstraintSystem(problem)
    assert system.analyze()['outcome']=='proven'
    problem.conditions[0].enabled=False
    assert ConstraintSystem(problem).analyze()['outcome']!='proven'


def test_ratio_constraint_excludes_zero_denominator_in_z3():
    problem=nested_triangles()
    problem.conditions=[Relation(id='ratio',kind='length_ratio',args=['A','B','D','D'],value=1.5)]
    assert ConstraintSystem(problem).solver.check()==z3.unsat


def test_similarity_does_not_guess_a_scale_from_the_display_coordinates():
    problem=nested_triangles()
    problem.conditions=[relation('similar_triangles',['A','D','E','A','B','C'])]
    problem.goal=Relation(id='goal',kind='length_ratio',args=['A','D','A','B'],value=.5)
    assert ConstraintSystem(problem).analyze()['outcome']!='proven'


def test_newclid_search_checks_the_complete_similarity_goal():
    result=newclid(nested_triangles())
    assert result['status']=='found',result
    assert result['steps'] or result['assumptionNodes']
    assert set(result['assumptionIds'])=={'mid-ab','mid-ac'}


def test_newclid_uses_the_official_constant_ratio_predicate():
    problem=nested_triangles()
    problem.goal=Relation(id='goal',kind='length_ratio',args=['A','D','A','B'],value=.5)
    # Unlike coordinates, the exact ratio is an actual premise in this check.
    problem.conditions=[Relation(id='given-ratio',kind='length_ratio',args=problem.goal.args,value=.5)]
    result=newclid(problem)
    assert result['status']=='found',result
    assert result['assumptionIds']==['given-ratio']

