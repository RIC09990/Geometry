import pytest

from server.models import Problem, Relation
from server.topics import IdeasReply, check_ideas, same_goal_relation


def relation(kind, args, **parameters):
    return Relation(id='claim', kind=kind, args=args, **parameters)


def checked_route(conclusion, goal):
    problem = Problem.model_validate({
        'id': 'goal-semantics', 'title': 'Goal semantics', 'version': 1,
        'points': [
            {'id': 'A', 'x': 1, 'y': 0}, {'id': 'B', 'x': -1, 'y': 0},
            {'id': 'O', 'x': 0, 'y': 0}, {'id': 'P', 'x': 0, 'y': 1},
        ],
        'conditions': [conclusion.model_copy(update={'id': 'given'}).model_dump()],
        'goal': goal.model_copy(update={'id': 'goal'}).model_dump(),
        'nondegenerate': {'distinct': True, 'triangles': []},
    })
    reply = IdeasReply.model_validate({'routes': [{'title': 'Known relation', 'steps': [{
        'id': 's1', 'statement': 'Restate the given relation', 'premises': ['given'],
        'conclusion': conclusion.model_dump(),
    }]}]})
    return check_ideas(problem, reply)[0]


@pytest.mark.parametrize('conclusion,goal', [
    (relation('fixed_length', ['A', 'B'], value=1),
     relation('fixed_length', ['A', 'B'], value=2)),
    (relation('fixed_angle', ['A', 'O', 'B'], value=90),
     relation('fixed_angle', ['A', 'O', 'B'], value=120)),
    (relation('length_ratio', ['P', 'A', 'P', 'B'], value=2),
     relation('length_ratio', ['P', 'A', 'P', 'B'], value=3)),
    (relation('fixed_point', ['A'], coordinates=[1, 2]),
     relation('fixed_point', ['A'], coordinates=[1, 3])),
    (relation('on_arc', ['P', 'O', 'A', 'B'], orientation='ccw'),
     relation('on_arc', ['P', 'O', 'A', 'B'], orientation='cw')),
])
def test_proven_different_claim_does_not_certify_requested_goal(conclusion, goal):
    route = checked_route(conclusion, goal)
    assert route['steps'][0]['checkStatus'] == 'verified'
    assert route['status'] == 'candidate'


def test_minimum_weights_are_part_of_the_goal():
    first = relation('minimize', ['P', 'A', 'P', 'B'], weights=[1, 2])
    different = relation('minimize', ['P', 'A', 'P', 'B'], weights=[2, 1])
    assert not same_goal_relation(first, different)
    assert same_goal_relation(first, first.model_copy(update={'id': 'goal'}))


def test_exact_values_do_not_use_drawing_tolerance():
    first = relation('fixed_length', ['A', 'B'], value=1)
    different = relation('fixed_length', ['A', 'B'], value=1.000000001)
    assert not same_goal_relation(first, different)


@pytest.mark.parametrize('conclusion', [
    relation('fixed_length', ['A', 'B'], value=1),
    relation('fixed_point', ['A'], coordinates=[1, 2]),
    relation('on_arc', ['P', 'O', 'A', 'B'], orientation='ccw'),
])
def test_identical_claim_with_different_display_metadata_remains_verified(conclusion):
    goal = conclusion.model_copy(update={
        'id': 'target', 'description': 'A different label',
        'toggleable': False, 'enabled': False,
    })
    assert same_goal_relation(conclusion, goal)
    assert checked_route(conclusion, goal)['status'] == 'verified'


def test_unused_arc_orientation_does_not_change_a_length_claim():
    first = relation('fixed_length', ['A', 'B'], value=1)
    assert same_goal_relation(first, first.model_copy(update={'orientation': 'cw'}))
