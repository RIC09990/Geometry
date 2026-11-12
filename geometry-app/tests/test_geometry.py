import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from server.models import Problem, Point, Relation
from server.constraints import ConstraintSystem
from server.proofs import teaching_proofs, dependencies, newclid
from server.algebra import verify_witness
from server.main import app

DATA=json.loads((Path(__file__).resolve().parents[1]/'data/cases.json').read_text(encoding='utf-8'))
def problem(i=0):return Problem.model_validate({k:v for k,v in DATA[i].items() if k not in ['description','tag']})
def disable(p,*ids):
    q=p.model_copy(deep=True)
    q.version+=1
    for r in q.conditions:
        if r.id in ids:r.enabled=False
    return q

@pytest.mark.parametrize('index',range(5))
def test_all_catalogue_goals_exactly_entailed(index):
    assert ConstraintSystem(problem(index)).analyze()['outcome']=='proven'

def test_acceptance_altitude_then_sss_then_counterexample_then_restore():
    original=problem()
    assert ConstraintSystem(original).analyze()['outcome']=='proven'
    first=teaching_proofs(original)
    assert [p['id'] for p in first]==['teaching-HL','teaching-SSS']
    p=disable(original,'altitude')
    assert ConstraintSystem(p).analyze()['outcome']=='proven'
    assert [proof['id'] for proof in teaching_proofs(p)]==['teaching-SSS']
    impact=dependencies(first[0],[r.id for r in p.conditions if r.enabled])
    assert impact['removed']==['altitude']
    assert set(impact['affected'])=={'t-perp','t-congruent','t-goal'}
    # Losing one member of a joint premise set invalidates the whole inference.
    assert not dependencies(first[1],[r.id for r in p.conditions if r.enabled])['affected']
    q=disable(p,'midpoint')
    analysis=ConstraintSystem(q).analyze()
    assert analysis['outcome']=='counterexample'
    assert verify_witness(q,analysis['counterexample']['coordinates'])['verified']
    assert analysis['counterexample']['exact']
    restored=problem();restored.version=q.version+1
    assert restored.conditions==original.conditions
    assert restored.points==original.points
    assert ConstraintSystem(restored).analyze()['outcome']=='proven'

def test_removed_midpoint_is_not_hidden_in_the_canvas_constraints():
    p=disable(problem(),'altitude','midpoint')
    moved=Point(id='D',x=1,y=-1.5)
    layout=ConstraintSystem(p,normalize=False).layout(moved)
    assert layout['status']=='sat'
    assert next(point for point in layout['points'] if point['id']=='D')['x']==1
    constrained=ConstraintSystem(problem(),normalize=False).layout(moved)
    if constrained['status']=='sat':
        coords={p['id']:p for p in constrained['points']}
        assert coords['D']['x']==pytest.approx((coords['B']['x']+coords['C']['x'])/2)
        assert coords['D']['y']==pytest.approx((coords['B']['y']+coords['C']['y'])/2)

def test_conflicting_collinearity_cannot_prove_a_goal_vacuously():
    p=problem();p.conditions.append(Relation(id='contradiction',kind='collinear',args=['A','B','C']))
    assert ConstraintSystem(p).analyze()['outcome']=='inconsistent'

def test_no_goal_equivalence_from_squared_cosines_alone():
    from server.algebra import holds
    import sympy as s
    coords={k:tuple(map(s.Rational,v)) for k,v in {'A':(0,0),'B':(1,0),'C':(1,1),'D':(-1,1)}.items()}
    # 45 degrees versus 135 degrees must not be reported equal.
    goal=Relation(id='angle',kind='equal_angle',args=['B','A','C','B','A','D'])
    assert not holds(coords,goal)

def test_api_rejects_unsupported_relation_and_missing_points():
    client=TestClient(app)
    p=problem().model_dump();p['conditions'][0]['kind']='invented_relation'
    assert client.post('/api/validate',json={'problem':p}).status_code==422
    p=problem().model_dump();p['goal']['args'][0]='Z'
    assert client.post('/api/validate',json={'problem':p}).status_code==422

def test_missing_nicegeo_runtime_cannot_be_confused_with_z3_step_check(monkeypatch):
    from server import nicegeo_adapter
    monkeypatch.setattr(nicegeo_adapter,'executable',lambda:Path(__file__).resolve().parent/'no-runtime.exe')
    p=problem();client=TestClient(app)
    statement={'id':'step','kind':'equal_length','args':['A','D','A','D'],'enabled':True,'toggleable':False}
    response=client.post('/api/check-step',json={'problem':p.model_dump(),'statement':statement,'premises':[]})
    assert response.status_code==200
    assert response.json()['status']=='cannot_check'
    assert response.json()['constraintCheck']['outcome']=='proven'

def test_unknown_search_is_not_a_counterexample():
    p=disable(problem(),'altitude')
    assert ConstraintSystem(p).analyze()['outcome']=='proven'
    # Goal truth is determined independently of whether Newclid finds a trace.
    assert teaching_proofs(p)

@pytest.mark.parametrize('index',[0,1,2,4])
def test_newclid_returns_real_trace_and_dependencies(index):
    p=problem(index)
    proof=newclid(p)
    assert proof['status']=='found',proof
    assert proof['steps'] and proof['raw']
    assert proof['assumptionNodes']
    if index==0:
        assert 'altitude' not in proof['assumptionIds']
        assert not dependencies(proof,[r.id for r in p.conditions if r.enabled and r.id!='altitude'])['affected']

def test_newclid_finds_sss_without_altitude():
    p=disable(problem(),'altitude')
    proof=newclid(p)
    assert proof['status']=='found',proof
    assert 'midpoint' in proof['assumptionIds']
    assert 'altitude' not in proof['assumptionIds']

def test_public_service_key_is_server_side_and_enforced(monkeypatch):
    monkeypatch.setenv('GEOMETRY_SERVICE_KEY','unit-test-only-key')
    client=TestClient(app)
    assert client.get('/api/health').status_code==401
    assert client.get('/api/health',headers={'X-Geometry-Service-Key':'unit-test-only-key'}).status_code==200
