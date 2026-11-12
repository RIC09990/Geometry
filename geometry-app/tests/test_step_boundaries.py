import pytest
from fastapi.testclient import TestClient

from server import main


def problem():
    return {
        'id': 'step-boundaries', 'title': 'Step boundaries', 'version': 3,
        'points': [
            {'id': 'A', 'x': 0, 'y': 0},
            {'id': 'B', 'x': 1, 'y': 0},
            {'id': 'C', 'x': 0, 'y': 1},
        ],
        'conditions': [],
        'goal': {'id': 'goal', 'kind': 'equal_length', 'args': ['A', 'B', 'A', 'B']},
        'nondegenerate': {'distinct': True, 'triangles': [['A', 'B', 'C']]},
    }


def no_formal_check(*args, **kwargs):
    raise AssertionError('Unencoded claims must not reach a partial formal check')


@pytest.mark.parametrize('statement', [
    {'id': 'step', 'kind': 'free_text', 'description': 'An unencoded expression'},
    {'id': 'step', 'kind': 'minimize', 'args': ['A', 'B'], 'weights': [1]},
    {'id': 'step', 'kind': 'angle_value', 'args': ['A', 'B', 'C']},
])
def test_nonpropositional_step_returns_unknown_instead_of_server_error(statement, monkeypatch):
    monkeypatch.setattr(main, 'ConstraintSystem', no_formal_check)
    monkeypatch.setattr(main, 'nicegeo_check', no_formal_check)
    response = TestClient(main.app).post('/api/check-step', json={
        'problem': problem(), 'statement': statement, 'premises': [],
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == result['nicegeo']['status'] == 'cannot_check'
    assert result['constraintCheck']['outcome'] == 'unknown'
    assert result['version'] == 3 and result['message']


def test_selected_text_premise_is_not_silently_dropped(monkeypatch):
    monkeypatch.setattr(main, 'ConstraintSystem', no_formal_check)
    monkeypatch.setattr(main, 'nicegeo_check', no_formal_check)
    p = problem()
    p['conditions'] = [{'id': 'text', 'kind': 'free_text', 'description': 'Unencoded premise'}]
    statement = {**p['goal'], 'id': 'step'}
    response = TestClient(main.app).post('/api/check-step', json={
        'problem': p, 'statement': statement, 'premises': ['text'],
    })
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'cannot_check'
    assert response.json()['constraintCheck']['outcome'] == 'unknown'


def test_unselected_text_does_not_block_an_encoded_step(monkeypatch):
    monkeypatch.setattr(main, 'nicegeo_check', lambda *args: {'status': 'verified', 'message': 'Reflexive length'})
    p = problem()
    p['conditions'] = [{'id': 'text', 'kind': 'free_text', 'description': 'Unencoded premise'}]
    statement = {**p['goal'], 'id': 'step'}
    response = TestClient(main.app).post('/api/check-step', json={
        'problem': p, 'statement': statement, 'premises': [],
    })
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'verified'
    assert response.json()['constraintCheck']['outcome'] == 'proven'


def test_malformed_or_unknown_step_is_still_rejected():
    client = TestClient(main.app)
    for statement in [
        {'id': 'step', 'kind': 'invented', 'args': []},
        {'id': 'step', 'kind': 'fixed_length', 'args': ['A'], 'value': 1},
        {'id': 'step', 'kind': 'equal_length', 'args': ['A', 'B', 'A', 'Z']},
    ]:
        response = client.post('/api/check-step', json={
            'problem': problem(), 'statement': statement, 'premises': [],
        })
        assert response.status_code == 422, response.text
