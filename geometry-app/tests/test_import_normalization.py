import json
from pathlib import Path
from fastapi.testclient import TestClient
from server.topics import decode_import
from server.models import Problem
from server.main import app
from server import topics

def source():
    value=json.loads((Path(__file__).resolve().parents[1]/'data/cases.json').read_text(encoding='utf8'))[0]
    return {k:v for k,v in value.items() if k not in ('tag','description')}

def test_nondegenerate_condition_is_moved_to_domain_without_losing_other_conditions():
    p=source();p['conditions'].append({'id':'not-flat','kind':'nondegenerate','args':['A','B','C']})
    reply=decode_import(json.dumps({'recognizedText':'ABC是非退化三角形','problem':p}))
    assert reply.problem is not None,reply.encodingIssues
    assert ['A','B','C'] in reply.problem.nondegenerate.triangles
    assert len(reply.problem.conditions)==4 and not reply.encodingIssues

def test_arbitrary_condition_and_optimization_expression_survive_import_and_roundtrip():
    p=source();p['conditions'].append({'id':'cyclic','kind':'concyclic','args':['A','B','C','D'],'text':'A、B、C、D 四点共圆'})
    p['goal']={'id':'goal','kind':'maximize','args':['A','B','C','D'],'expression':r'求 \(\frac{AB^2+CD^2}{AC\cdot BD}\) 的最大值'}
    reply=decode_import(json.dumps({'recognizedText':'任意式子题目','problem':p}))
    assert reply.problem is not None,reply.encodingIssues
    assert reply.problem.conditions[-1].kind=='free_text'
    assert '四点共圆' in reply.problem.conditions[-1].description
    assert 'frac' in reply.problem.goal.description
    result=TestClient(app).post('/api/validate',json={'problem':reply.problem.model_dump()})
    assert result.status_code==200,result.text
    assert result.json()['status']=='unverified' and result.json()['unverifiedConditions']
    assert 'points' not in result.json()
    analysis=TestClient(app).post('/api/analyze',json={'problem':reply.problem.model_dump()}).json()
    assert analysis['outcome']=='unknown' and not analysis['proofs']

def test_case_with_more_than_eight_points_and_twenty_conditions_is_not_blocked():
    p=source();p['points'] += [{'id':id,'x':i,'y':i+1} for i,id in enumerate('EFGHIJKL')]
    p['conditions'] += [{'id':'text-'+str(i),'kind':'free_text','args':[],'description':'用户补充条件 '+str(i)} for i in range(24)]
    assert len(Problem.model_validate(p).points)==12

def test_typed_unknown_goal_can_be_solved_with_search_and_unencoded_steps(monkeypatch):
    p=source();p['goal']={'id':'goal','kind':'free_text','description':'求 AB+AC 的最小值','args':[]}
    async def dispatch(request,key,**kwargs):
        assert request.webSearch and kwargs['structured']
        assert '最小值' in kwargs['search_query']
        return {'content':json.dumps({'answer':r'由三角不等式，\(AB+AC\geq BC\)。','routes':[{'title':'三角不等式','steps':[{'id':'s1','statement':'两边之和大于第三边','premises':['domain'],'conclusion':None}]}]}),'sources':[{'title':'test-source','url':'https://example.com/source'}],'searchStatus':'found'}
    monkeypatch.setattr(topics,'dispatch',dispatch)
    result=TestClient(app).post('/api/ai/proof-ideas',json={'problem':p}).json()
    assert '三角不等式' in result['answer'] and result['sources']
    assert result['proofs'][0]['status']=='candidate'

def test_broken_ai_dependency_graph_keeps_the_readable_solution(monkeypatch):
    async def dispatch(request,key,**kwargs):
        return {'content':json.dumps({'answer':'已知、推导、结论均在此。','routes':[{'title':'有误依赖','steps':[{'id':'s1','statement':'一步','premises':['missing']}]}]})}
    monkeypatch.setattr(topics,'dispatch',dispatch)
    result=TestClient(app).post('/api/ai/proof-ideas',json={'problem':source()}).json()
    assert result['answer']=='已知、推导、结论均在此。' and result['proofs']==[]
