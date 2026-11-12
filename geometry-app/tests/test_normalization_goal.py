import pytest

from server.constraints import ConstraintSystem
from server.algebra import verify_witness
from server.models import Problem
from server.topics import IdeasReply, check_ideas


def problem(goal, conditions=()):
    return Problem.model_validate({
        'id': 'coordinate-invariance', 'title': '坐标归一化不得预设结论', 'version': 1,
        'points': [{'id': name, 'x': x, 'y': y} for name, x, y in
                   [('A', 0, 1), ('B', -1, 0), ('C', 1, 0), ('O', 0, 0)]],
        'conditions': list(conditions), 'goal': {'id': 'goal', **goal},
        'nondegenerate': {'distinct': True, 'triangles': [['A', 'B', 'C']]},
    })


@pytest.mark.parametrize('goal', [
    {'kind': 'fixed_length', 'args': ['B', 'C'], 'value': 1},
    {'kind': 'fixed_point', 'args': ['B'], 'coordinates': [0, 0]},
])
def test_coordinate_frame_cannot_prove_absolute_target(goal):
    result = ConstraintSystem(problem(goal)).analyze()
    assert result['outcome'] == 'counterexample', result
    assert result['counterexample']['verified']


def test_reflection_cannot_choose_target_semicircle():
    p = problem({'kind': 'on_arc', 'args': ['A', 'O', 'C', 'B'], 'orientation': 'ccw'}, [
        {'id': 'center', 'kind': 'midpoint', 'args': ['O', 'B', 'C']},
        {'id': 'circle', 'kind': 'on_circle', 'args': ['A', 'O', 'B']},
    ])
    result = ConstraintSystem(p).analyze()
    # Z3 may choose an algebraic model that our rational witness exporter
    # cannot yet represent. It must still never certify the reflected goal.
    assert result['outcome'] in ('counterexample', 'unknown'), result
    assert verify_witness(p, {'A': ['0', '-1'], 'B': ['-1', '0'],
                              'C': ['1', '0'], 'O': ['0', '0']})['verified']


def test_actual_absolute_premise_still_proves_target():
    goal = {'kind': 'fixed_length', 'args': ['B', 'C'], 'value': 2}
    p = problem(goal, [{'id': 'known', **goal}])
    assert ConstraintSystem(p).analyze()['outcome'] == 'proven'


def test_intermediate_step_cannot_borrow_scale_from_unrelated_goal():
    p = problem({'kind': 'equal_length', 'args': ['A', 'B', 'A', 'B']})
    reply = IdeasReply.model_validate({'routes': [{'title': 'Wrong scale', 'steps': [{
        'id': 's1', 'statement': 'BC=1', 'premises': [],
        'conclusion': {'id': 'claim', 'kind': 'fixed_length', 'args': ['B', 'C'], 'value': 1},
    }]}]})
    route = check_ideas(p, reply)[0]
    assert route['steps'][0]['checkStatus'] != 'verified'
    assert route['status'] != 'verified'
