"""A newly entered problem uses relations, not catalogue/condition IDs."""
import json
from pathlib import Path
from server.models import Problem
from server.proofs import teaching_proofs,dependencies,newclid
from server.constraints import ConstraintSystem

def custom():
    p=json.loads((Path(__file__).resolve().parents[1]/'data/cases.json').read_text(encoding='utf8'))[0]
    p={k:v for k,v in p.items() if k not in ['description','tag']}
    p['id']='custom-proof-regression';p['title']='自建题：顶点 B 的角平分线'
    names={'A':'B','B':'A','C':'C','D':'D'}
    for q in p['points']:q['id']=names[q['id']]
    p['points'].sort(key=lambda q:q['id'])
    for i,r in enumerate(p['conditions']):r['id']='user-'+str(i);r['args']=[names[a] for a in r['args']]
    p['goal']['args']=[names[a] for a in p['goal']['args']]
    for s in p['segments']:s['points']=[names[a] for a in s['points']]
    p['nondegenerate']['triangles']=[[names[a] for a in t] for t in p['nondegenerate']['triangles']]
    return Problem.model_validate(p)

def test_custom_relation_ids_and_renamed_vertices_have_two_verified_routes():
    p=custom();routes=teaching_proofs(p)
    assert len(routes)==2
    assert {r['title'] for r in routes}=={'HL 教学路线','SSS 教学路线'}
    assert routes[0]['assumptionIds']==['user-0','user-3','user-1']
    assert routes[0]['steps'][-1]['statement']=='∠ABD = ∠DBC'
    for route in routes:
        q=p.model_copy(deep=True)
        for r in q.conditions:r.enabled=r.id in route['assumptionIds']
        assert ConstraintSystem(q).analyze()['outcome']=='proven'

def test_custom_condition_removal_tracks_actual_ids_and_then_finds_counterexample():
    p=custom();original=teaching_proofs(p)
    p.conditions[3].enabled=False
    routes=teaching_proofs(p);assert len(routes)==1
    impact=dependencies(original[0],[r.id for r in p.conditions if r.enabled])
    assert impact['removed']==['user-3'];assert 't-congruent' in impact['affected']
    assert ConstraintSystem(p).analyze()['outcome']=='proven'
    p.conditions[2].enabled=False
    assert teaching_proofs(p)==[]
    assert ConstraintSystem(p).analyze()['counterexample']['verified']

def test_newclid_really_searches_a_user_created_problem():
    result=newclid(custom())
    assert result['status']=='found',result
    assert result['steps']
    assert all(not cid.startswith('equal-sides') for cid in result['assumptionIds'])
