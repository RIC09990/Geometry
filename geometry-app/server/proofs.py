import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import networkx as nx
import z3
from .constraints import ConstraintSystem
from .models import Relation, Problem

ROOT=Path(__file__).resolve().parents[1]

def numerical_expression(system,kind,a):
    if kind=='diff':return system.d2(*a)>0
    if kind=='ncoll':return system.cross(system.vec(a[0],a[1]),system.vec(a[0],a[2]))!=0
    if kind=='sameclock':return system.cross(system.vec(a[0],a[1]),system.vec(a[0],a[2]))*system.cross(system.vec(a[3],a[4]),system.vec(a[3],a[5]))>0
    return None

def sufficient_support(problem,kind,a):
    """Find one sufficient subset of the FINITE input list, not weakest facts."""
    selected=[r.id for r in problem.conditions if r.enabled]
    for cid in selected.copy():
        candidate=[k for k in selected if k!=cid]
        reduced=problem.model_copy(deep=True)
        for r in reduced.conditions:r.enabled=r.id in candidate
        system=ConstraintSystem(reduced,timeout=300)
        expression=numerical_expression(system,kind,a)
        system.solver.add(z3.Not(expression))
        if system.solver.check()==z3.unsat:selected=candidate
    return ['domain',*selected]

def newclid(problem: Problem):
    try:
        env={**os.environ,'MPLBACKEND':'Agg','MPLCONFIGDIR':str(ROOT/'.local'/'matplotlib'),'PYTHONIOENCODING':'utf-8'}
        completed=subprocess.run([sys.executable,'-m','server.newclid_worker'],input=json.dumps({'problem':problem.model_dump()}),text=True,encoding='utf-8',capture_output=True,timeout=18,cwd=ROOT,env=env)
        if completed.returncode:return {'status':'error','message':completed.stderr[-1200:],'engine':'Newclid'}
        result=json.loads(completed.stdout)
        if result.get('status')!='found':return result
        system=ConstraintSystem(problem)
        for check in result.get('numericalChecks',[]):
            kind,a=check['type'],[v.upper() for v in check['args']]
            expr=numerical_expression(system,kind,a)
            if expr is None:
                result['status']='needs_extra_premise';result['message']='搜索结果含尚未形式化核验的数值前提：'+check['statement'];return result
            system.solver.push();system.solver.add(z3.Not(expr));valid=system.solver.check()==z3.unsat;system.solver.pop()
            if not valid:
                result['status']='needs_extra_premise';result['message']='数值前提不能从当前条件普遍推出：'+check['statement'];return result
            support=sufficient_support(problem,kind,a)
            result['assumptionNodes'].append({'id':check['id'],'statement':check['statement'],'premises':support})
        used={cid for node in result['assumptionNodes'] for cid in node.get('premises',[]) if cid!='domain'}
        result['assumptionIds']=sorted(used)
        retained=problem.model_copy(deep=True)
        for r in retained.conditions:r.enabled=r.id in used
        target_system=ConstraintSystem(retained)
        if target_system.solver.check()!=z3.sat or not target_system.entails(problem.goal):
            result['status']='needs_extra_premise'
            result['message']='返回的路线尚不能在其列明前提下核验本站完整目标；不作为已找到的有效证明。'
            return result
        result['verification']='Newclid 返回的目标另按本站内角、严格关系和非退化语义，由 Z3 使用本条路线列明的前提核验。'
        return result
    except subprocess.TimeoutExpired:return {'status':'timeout','message':'Newclid 搜索超过18秒；未找到证明不等于结论错误。','engine':'Newclid'}
    except Exception as e:return {'status':'error','message':str(e),'engine':'Newclid'}

def teaching_proofs(problem):
    """Two finite curriculum routes, with every asserted relation checked by Z3.
    These are labelled templates; they are not returned as Newclid discoveries.
    """
    if problem.goal.kind!='equal_angle':return []
    left,apex,split,split2,apex2,right=problem.goal.args
    if split!=split2 or apex!=apex2 or len({left,apex,split,right})!=4:return []
    names={'A':apex,'B':left,'C':right,'D':split}
    def shape(kind,args):
        if kind in ['equal_length','perpendicular']:
            return tuple(sorted(tuple(sorted(pair)) for pair in [args[:2],args[2:]]))
        return (args[0],*sorted(args[1:]))
    definitions={'equal-sides':('equal_length',['A','B','A','C']),'altitude':('perpendicular',['A','D','B','C']),'interior':('on_segment',['D','B','C']),'midpoint':('midpoint',['D','B','C'])}
    actual={}
    for role,(kind,args) in definitions.items():
        expected=shape(kind,[names[a] for a in args])
        match=next((r for r in problem.conditions if r.enabled and r.kind==kind and shape(kind,r.args)==expected),None)
        if match:actual[role]=match.id
    conditions=actual
    out=[]
    for route,required in [('HL',['equal-sides','altitude','interior']),('SSS',['equal-sides','midpoint','interior'])]:
        if not all(k in conditions for k in required):continue
        # The selected route must be valid without any other optional condition.
        reduced=problem.model_copy(deep=True)
        for r in reduced.conditions:r.enabled=r.id in [actual[role] for role in required]
        check=ConstraintSystem(reduced)
        refl=Relation(id='common',kind='equal_length',args=[apex,split,apex,split])
        goal=problem.goal
        if not check.entails(refl) or not check.entails(goal):continue
        if route=='HL':
            facts=[{'id':'t-perp','statement':'AD ⟂ BC，△ABD 与 △ACD 均为直角三角形','rule':'已知垂直及 D 在 BC 内部','premises':['altitude','interior']},
                   {'id':'t-sides','statement':'AB = AC，AD = AD','rule':'等腰条件与公共边','premises':['equal-sides']}]
            supports=['t-perp','t-sides']
        else:
            facts=[{'id':'t-mid','statement':'BD = DC','rule':'中点定义','premises':['midpoint']},
                   {'id':'t-sides','statement':'AB = AC，AD = AD','rule':'等腰条件与公共边','premises':['equal-sides']}]
            supports=['t-mid','t-sides']
        facts += [{'id':'t-congruent','statement':'△ABD ≌ △ACD','rule':route,'premises':supports},
                  {'id':'t-goal','statement':'∠BAD = ∠DAC','rule':'全等三角形的对应角相等','premises':['t-congruent','interior']}]
        # Bind human-created condition IDs and point names; no catalogue IDs or coordinates are required.
        for fact in facts:
            fact['statement']=''.join(names.get(char,char) for char in fact['statement'])
            fact['rule']=''.join(names.get(char,char) for char in fact['rule'])
            fact['premises']=[actual.get(cid,cid) for cid in fact['premises']]
        out.append({'id':'teaching-'+route,'title':route+' 教学路线','engine':'教学模板 · Z3 精确核验','status':'verified','assumptionIds':[actual[role] for role in required],'assumptionNodes':[], 'steps':facts,'verification':'使用列明前提、独立核验目标；教学模板不是 Newclid 的搜索输出。'})
    return out

def dependencies(proof, active):
    graph=nx.DiGraph()
    for cid in [*proof.get('assumptionIds',[]),'domain']:graph.add_node(cid,kind='condition')
    items=[*proof.get('assumptionNodes',[]),*proof.get('steps',[])]
    # A step node represents one inference with ALL of its incoming premises.
    for step in items:
        graph.add_node(step['id'],kind='inference')
        for premise in step.get('premises',[]):graph.add_edge(premise,step['id'])
    if not nx.is_directed_acyclic_graph(graph):
        return {'proofId':proof.get('id'),'error':'证明依赖包含循环，无法追踪'}
    removed=set(proof.get('assumptionIds',[]))-set(active)
    affected=set()
    for cid in removed:
        if cid in graph:affected|=nx.descendants(graph,cid)
    return {'proofId':proof.get('id'),'title':proof.get('title'),'removed':sorted(removed),'affected':[s['id'] for s in items if s['id'] in affected], 'steps':[dict(s,affected=s['id'] in affected,missing=[p for p in s.get('premises',[]) if p in removed]) for s in items], 'edges':[list(e) for e in graph.edges], 'semantics':'每个推理节点需要所有列出的前提共同支持；失去依据不等于结论错误。','engine':'NetworkX '+nx.__version__}
