import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from server.models import Problem, Relation
from server import nicegeo_adapter as ng
from server.main import app


def problem():
    raw = json.loads((Path(__file__).resolve().parents[1] / 'data/cases.json').read_text(encoding='utf-8'))[0]
    p = Problem.model_validate({k: v for k, v in raw.items() if k not in {'description', 'tag'}})
    p.conditions = []
    p.goal = Relation(id='step', kind='equal_length', args=['A', 'D', 'A', 'D'])
    return p


def require_runtime():
    if ng.status()['status'] != 'runtime_available':
        pytest.skip('NiceGeo CLI is not compiled on this machine')


def test_reflexivity_is_actually_checked_by_nicegeo_cli():
    require_runtime()
    result = ng.check(problem(), 'reflexivity.')
    assert result['status'] == 'verified', result
    assert result['exitCode'] == 0 and 'Valid proofs!' in result['raw']


def test_length_symmetry_uses_official_system_e_axiom():
    require_runtime()
    p = problem(); p.goal.args = ['A', 'B', 'B', 'A']
    result = ng.check(p, 'exact (length_symm A B).')
    assert result['status'] == 'verified', result


def test_wrong_proof_is_rejected_without_declaring_goal_false():
    require_runtime()
    p = problem(); p.goal.args = ['A', 'B', 'A', 'C']
    result = ng.check(p, 'reflexivity.')
    assert result['status'] == 'rejected', result
    assert result['exitCode'] != 0


@pytest.mark.parametrize('body', ['sorry.', 'exact sorry_ax.', 'Qed. Axiom fake: False', 'Import "private.txt"', '#print foo', 'repeat intro.'])
def test_unproved_admissions_and_file_imports_are_not_accepted(body):
    assert ng.check(problem(), body)['status'] == 'cannot_check'


def test_unsupported_premise_is_not_silently_dropped():
    p = problem()
    p.conditions = [Relation(id='future', kind='future_relation', args=['A', 'D', 'B', 'C'])]
    result = ng.check(p, 'reflexivity.')
    assert result['status'] == 'cannot_check'
    assert 'future' in result['message']


def test_midpoint_mapping_never_keeps_a_removed_condition():
    p = problem()
    p.conditions = [Relation(id='mid', kind='midpoint', args=['D', 'B', 'C'])]
    before = ng.translate(p, 'reflexivity.')
    assert 'Between B D C' in before and 'Length B D = Length D C' in before
    p.conditions[0].enabled = False
    assert 'Between B D C' not in ng.translate(p, 'reflexivity.')


def test_api_reports_nicegeo_and_z3_independently():
    require_runtime()
    p = problem()
    result = TestClient(app).post('/api/check-step', json={'problem': p.model_dump(), 'statement': p.goal.model_dump(), 'premises': [], 'proofBody': 'reflexivity.'})
    assert result.status_code == 200
    data = result.json()
    assert data['status'] == 'verified' and data['constraintCheck']['outcome'] == 'proven'
    assert data['nicegeo']['source'] and data['nicegeo']['raw']


@pytest.mark.parametrize('kind,args', [
    ('equal_length', ['A', 'B', 'A', 'C']),
    ('equal_angle', ['B', 'A', 'D', 'D', 'A', 'C']),
    ('midpoint', ['D', 'B', 'C']),
    ('on_segment', ['D', 'B', 'C']),
    ('collinear', ['B', 'D', 'C']),
    ('on_circle', ['D', 'A', 'B']),
    ('perpendicular', ['A', 'D', 'B', 'C']),
    ('parallel', ['A', 'B', 'C', 'D']),
])
def test_each_relation_mapping_is_parsed_and_typechecked_by_official_cli(kind, args):
    require_runtime()
    p = problem()
    p.goal = Relation(id='goal', kind=kind, args=args)
    p.conditions = [Relation(id='given', kind=kind, args=args)]
    result = ng.check(p)
    assert result['status'] == 'verified', result


@pytest.mark.parametrize('kind', ['perpendicular', 'parallel'])
def test_line_direction_and_pair_symmetries_have_real_nicegeo_proofs(kind):
    require_runtime()
    p = problem()
    p.goal = Relation(id='goal', kind=kind, args=['D', 'C', 'B', 'A'])
    p.conditions = [Relation(id='given', kind=kind, args=['A', 'B', 'C', 'D'])]
    result = ng.check(p, 'exact h0.')
    assert result['status'] == 'verified', result
    p.conditions[0].enabled = False
    removed = ng.check(p)
    assert removed['status'] != 'verified', removed


def test_parallel_mapping_accepts_coincident_lines_using_a_constructive_proof():
    require_runtime()
    p = problem()
    p.goal = Relation(id='goal', kind='parallel', args=['A', 'B', 'A', 'B'])
    proof = '''split.
exact nd0.
split.
exact nd0.
choose l hl (line_of_pts A B nd0).
destruct_ands hl ha hb.
exists l.
split.
exact ha.
split.
exact hb.
exists l.
split.
exact ha.
split.
exact hb.
left.
reflexivity.'''
    result = ng.check(p, proof)
    assert result['status'] == 'verified', result


def test_perpendicular_step_uses_retained_betweenness_to_change_supporting_segment():
    require_runtime()
    p = problem()
    p.goal = Relation(id='goal', kind='perpendicular', args=['A', 'D', 'B', 'D'])
    p.conditions = [Relation(id='perp', kind='perpendicular', args=['A', 'D', 'B', 'C']),
                    Relation(id='inside', kind='on_segment', args=['D', 'B', 'C'])]
    proof = '''split.
exact nd2.
split.
exact nd4.
destruct_ands h0 adNonzero bcNonzero geo.
choose l hl geo.
destruct_ands hl al dl geoM.
choose m hm geoM.
destruct_ands hm bm cm rays.
exists l.
split.
exact al.
split.
exact dl.
exists m.
split.
exact bm.
split.
exact (between_collinear_middle B D C m h1 bm cm).
exact rays.'''
    result = ng.check(p, proof)
    assert result['status'] == 'verified', result
    p.conditions[1].enabled = False
    assert ng.check(p, proof)['status'] == 'rejected'


def test_perpendicular_premise_cannot_be_used_as_parallel():
    require_runtime()
    p = problem()
    p.goal = Relation(id='goal', kind='parallel', args=['A', 'B', 'C', 'D'])
    p.conditions = [Relation(id='perp', kind='perpendicular', args=['A', 'B', 'C', 'D'])]
    result = ng.check(p, 'exact h0.')
    assert result['status'] == 'rejected', result


def test_zero_length_midpoint_case_is_retained_when_it_is_allowed_by_the_model():
    require_runtime()
    p = problem();p.nondegenerate.distinct=False
    p.goal = Relation(id='goal',kind='midpoint',args=['D','D','D'])
    result = ng.check(p,'right.\nsplit.\nreflexivity.\nreflexivity.')
    assert result['status']=='verified',result


def test_angle_mapping_requires_nonzero_rays_even_for_reflexive_goals():
    require_runtime()
    p=problem()
    p.goal=Relation(id='goal',kind='equal_angle',args=['A','A','B','A','A','B'])
    result=ng.check(p)
    assert result['status']!='verified',result
