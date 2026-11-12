"""Metric exploration regressions using a family of problems, not one screenshot.

The base conditions below deliberately omit OA=OB=12: those are consequences of
the given segment lengths and arc, and must disappear if their premises do.
"""
import math

import pytest
import sympy as sp
import z3
from pydantic import ValidationError

from server.algebra import holds
from server.constraints import ConstraintSystem
from server.models import Problem
from server.optimization import analyze_minimum, inversion_certificate
from server.proofs import dependencies


def metric_problem(radius=12, focus_x=10, focus_y=6, multiplier=1):
    """PC + (radius/OD) PD on a quarter-circle, with arbitrary numeric data."""
    points = [
        ('O', 0, 0), ('A', radius, 0), ('B', 0, radius),
        ('C', focus_x, 0), ('D', 0, focus_y),
        ('P', radius * 3 / 5, radius * 4 / 5),
    ]
    rows = [
        ('oc', 'fixed_length', ['O', 'C'], focus_x),
        ('ca', 'fixed_length', ['C', 'A'], radius-focus_x),
        ('od', 'fixed_length', ['O', 'D'], focus_y),
        ('db', 'fixed_length', ['D', 'B'], radius-focus_y),
        ('right', 'perpendicular', ['O', 'A', 'O', 'B'], None),
        ('insidec', 'on_segment', ['C', 'O', 'A'], None),
        ('insided', 'on_segment', ['D', 'O', 'B'], None),
        ('arc', 'on_arc', ['P', 'O', 'A', 'B'], None),
    ]
    return Problem.model_validate({
        'schemaVersion': 1, 'id': 'custom-metric-family',
        'title': 'Independent metric test', 'version': 1,
        'points': [{'id': name, 'x': x, 'y': y, 'fixed': name != 'P'}
                   for name, x, y in points],
        'segments': [{'id': a+b, 'points': [a, b]}
                     for a, b in [('O', 'A'), ('O', 'B'), ('P', 'C'), ('P', 'D')]],
        'circles': [{'id': 'original-arc', 'center': 'O', 'through': 'A', 'end': 'B'}],
        'conditions': [{'id': name, 'kind': kind, 'args': args,
                        **({'value': value} if value is not None else {})}
                       for name, kind, args, value in rows],
        'goal': {'id': 'goal', 'kind': 'minimize', 'args': ['P', 'C', 'P', 'D'],
                 'weights': [multiplier, multiplier*radius/focus_y]},
        'nondegenerate': {'distinct': False, 'triangles': [['O', 'A', 'B']]},
        'constructions': [],
    })


def fixed_layout_system(problem, replacement):
    """Use exact decimal coordinates only for testing the display-layout path."""
    system = ConstraintSystem(problem, normalize=False, timeout=1500)
    for point in problem.points:
        xy = replacement.get(point.id, (point.x, point.y))
        for variable, value in zip(system.xy[point.id], xy):
            system.solver.add(variable == z3.RealVal(str(value), ctx=system.ctx))
    return system


@pytest.mark.parametrize('radius,focus_x,focus_y,multiplier,expected', [
    (12, 10, 6, 1, sp.Integer(26)),
    (18, 15, 9, 1, sp.Integer(39)),
    (6, 3, 2, 1, 3*sp.sqrt(37)),
    (6, 3, 2, 2, 6*sp.sqrt(37)),
])
def test_inversion_route_works_for_distinct_radii_weights_and_scales(
        radius, focus_x, focus_y, multiplier, expected):
    result = inversion_certificate(metric_problem(radius, focus_x, focus_y, multiplier))
    assert result and result['outcome'] == 'optimized'
    assert sp.simplify(sp.sympify(result['optimization']['minimum'])-expected) == 0
    assert result['optimization']['value'] == pytest.approx(float(expected))
    assert result['optimization']['certificate']['verified'] is True
    assert result['proofs'][0]['status'] == 'verified'


def test_names_ids_rotation_and_translation_are_not_a_named_example_lookup():
    problem = metric_problem(6, 3, 2)
    raw = problem.model_dump()
    rename = dict(zip('OABCDP', 'UVWXYZ'))
    # Exact 90-degree rotation and translation; none of the original point names
    # or condition IDs remain. Distances and the ccw arc have the same meaning.
    for point in raw['points']:
        point['id'] = rename[point['id']]
        point['x'], point['y'] = 31-point['y'], point['x']-17
    for index, condition in enumerate(raw['conditions']):
        condition['id'] = f'independent-{index}'
        condition['args'] = [rename[name] for name in condition['args']]
    raw['goal']['args'] = [rename[name] for name in raw['goal']['args']]
    raw['nondegenerate']['triangles'] = [[rename[name] for name in triangle]
                                        for triangle in raw['nondegenerate']['triangles']]
    for segment in raw['segments']:
        segment['points'] = [rename[name] for name in segment['points']]
    for circle in raw['circles']:
        for key in ('center', 'through', 'end'):
            circle[key] = rename[circle[key]]
    renamed = Problem.model_validate(raw)
    result = inversion_certificate(renamed)
    assert result and result['optimization']['value'] == pytest.approx(3*math.sqrt(37))
    assert set(result['proofs'][0]['assumptionIds']) == {
        condition.id for condition in renamed.conditions}
    assert result['optimization']['movingPoint'] == 'Z'


def test_reversing_segment_names_and_objective_term_order_preserves_the_problem():
    problem = metric_problem(12, 10, 4)
    problem.goal.args = ['D', 'P', 'C', 'P']
    problem.goal.weights = [3, 1]
    result = inversion_certificate(problem)
    assert result
    assert sp.simplify(sp.sympify(result['optimization']['minimum'])-2*sp.sqrt(349)) == 0


def test_numeric_lengths_are_not_destroyed_by_unit_scale_normalization():
    problem = metric_problem()
    system = ConstraintSystem(problem)
    assert system.solver.check() == z3.sat
    system.solver.add(system.d2('O', 'C') != 100)
    assert system.solver.check() == z3.unsat


def test_minimization_without_numeric_lengths_keeps_the_scaling_degree_of_freedom():
    problem = metric_problem()
    problem.conditions = [c for c in problem.conditions if c.kind != 'fixed_length']
    system = ConstraintSystem(problem)
    for squared_radius in [49, 100]:
        system.solver.push()
        system.solver.add(system.d2('O', 'A') == squared_radius)
        assert system.solver.check() == z3.sat
        system.solver.pop()


def test_arc_enforces_the_actual_sector_and_permits_its_endpoints():
    problem = metric_problem()
    for valid in [(12, 0), (0, 12), (7.2, 9.6)]:
        assert fixed_layout_system(problem, {'P': valid}).solver.check() == z3.sat
    for wrong_sector in [(0, -12), (-12, 0), (-7.2, 9.6)]:
        assert fixed_layout_system(problem, {'P': wrong_sector}).solver.check() == z3.unsat
    coordinates = {point.id: tuple(sp.Rational(str(v)) for v in (point.x, point.y))
                   for point in problem.points}
    arc = next(c for c in problem.conditions if c.kind == 'on_arc')
    assert holds(coordinates, arc)
    coordinates['P'] = (sp.Integer(0), sp.Integer(-12))
    assert not holds(coordinates, arc)


def test_reflected_clockwise_problem_has_the_same_certified_minimum():
    problem = metric_problem()
    for point in problem.points:
        point.y = -point.y
    next(c for c in problem.conditions if c.kind == 'on_arc').orientation = 'cw'
    problem.circles[0].orientation = 'cw'
    assert fixed_layout_system(problem, {}).solver.check() == z3.sat
    result = inversion_certificate(problem)
    assert result and result['optimization']['minimum'] == '26'


def test_deleting_arc_releases_the_point_even_if_the_arc_is_still_drawn():
    problem = metric_problem()
    next(c for c in problem.conditions if c.kind == 'on_arc').enabled = False
    assert problem.circles[0].end == 'B'
    assert fixed_layout_system(problem, {'P': (9, 9)}).solver.check() == z3.sat
    assert inversion_certificate(problem) is None


def test_display_fixed_flags_are_not_hidden_mathematical_conditions():
    problem = metric_problem()
    # C may now be anywhere strictly inside OA. Keeping the old display at C=10
    # and its fixed UI flag must not imply that the previous minimum is still 26.
    for condition in problem.conditions:
        if condition.id in ['oc', 'ca']:
            condition.enabled = False
    assert next(p for p in problem.points if p.id == 'C').fixed
    assert inversion_certificate(problem) is None


def test_changed_numeric_conditions_do_not_reuse_the_old_weighted_certificate():
    problem = metric_problem()
    next(c for c in problem.conditions if c.id == 'od').value = 4
    next(c for c in problem.conditions if c.id == 'db').value = 8
    # Old weights [1, 2] no longer match the new inversion distance ratio of 3.
    assert inversion_certificate(problem) is None


def test_inconsistent_data_never_certifies_a_vacuous_minimum():
    problem = metric_problem()
    next(c for c in problem.conditions if c.id == 'ca').value = 3
    result = analyze_minimum(problem)
    assert result['outcome'] == 'inconsistent'
    assert not result.get('proofs') and 'optimization' not in result


def test_optimization_dependencies_track_joint_support_and_its_transitive_effects():
    result = inversion_certificate(metric_problem())
    proof = result['proofs'][0]
    active = [name for name in proof['assumptionIds'] if name != 'arc']
    impact = dependencies(proof, active)
    assert impact['removed'] == ['arc']
    assert {'opt-inversion', 'opt-triangle', 'opt-equality', 'opt-conclusion'} <= set(impact['affected'])
    assert 'opt-construction' not in impact['affected']


def test_user_condition_ids_do_not_collide_with_generated_proof_steps():
    problem = metric_problem()
    problem.conditions[0].id = 'opt-conclusion'
    proof = inversion_certificate(problem)['proofs'][0]
    condition_ids = {c.id for c in problem.conditions}
    assert not condition_ids.intersection(step['id'] for step in proof['steps'])
    assert 'opt-conclusion' in proof['assumptionIds']


@pytest.mark.parametrize('weights', [[1], [1, -2], [1, 0], [1, math.inf]])
def test_invalid_objective_weights_cannot_bypass_the_positive_distance_proof(weights):
    payload = metric_problem().model_dump()
    payload['goal']['weights'] = weights
    with pytest.raises(ValidationError):
        Problem.model_validate(payload)
