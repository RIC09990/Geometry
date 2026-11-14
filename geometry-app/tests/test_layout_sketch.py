from fastapi.testclient import TestClient

from server.main import app


def problem():
    return {'schemaVersion': 1, 'id': 'custom-sketch', 'title': '圆中直径与等腰三角形', 'version': 1,
            'points': [{'id': 'O', 'x': 0, 'y': 0}, {'id': 'A', 'x': -5, 'y': 0}, {'id': 'B', 'x': 5, 'y': 0},
                       {'id': 'C', 'x': 3, 'y': 4}, {'id': 'D', 'x': -3, 'y': 4}],
            'segments': [{'id': 'AB', 'points': ['A', 'B']}], 'circles': [{'id': 'c', 'center': 'O', 'through': 'A'}],
            'constructions': [],
            'conditions': [{'id': 'mid', 'kind': 'midpoint', 'args': ['O', 'A', 'B']},
                           {'id': 'on-c', 'kind': 'on_circle', 'args': ['C', 'O', 'A']},
                           {'id': 'ac', 'kind': 'fixed_length', 'args': ['A', 'C'], 'value': 8},
                           {'id': 'bc', 'kind': 'fixed_length', 'args': ['B', 'C'], 'value': 6},
                           {'id': 'iso', 'kind': 'free_text', 'args': [], 'description': '△ABD为等腰三角形'}],
            'goal': {'id': 'goal', 'kind': 'angle_value', 'args': ['A', 'C', 'B']},
            'nondegenerate': {'distinct': True, 'triangles': [['A', 'B', 'C']]}}


def test_unencoded_conditions_pause_by_default():
    client = TestClient(app)
    reply = client.post('/api/validate', json={'problem': problem()}).json()
    assert reply['status'] == 'unverified'
    assert reply['unverifiedConditions'] == ['iso']


def test_ignoring_unencoded_conditions_still_builds_a_labelled_sketch():
    client = TestClient(app)
    reply = client.post('/api/validate', json={'problem': problem(), 'ignoreUnencoded': True}).json()
    assert reply['status'] == 'sat'
    assert len(reply['points']) == 5
    assert reply['unverifiedConditions'] == ['iso']
    assert '△ABD为等腰三角形' in reply['message']
