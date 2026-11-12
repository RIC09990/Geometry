"""A bounded separate process calls the installed official Newclid API."""
import contextlib
import io
import json
import sys
import traceback
import itertools
from fractions import Fraction

class UnsupportedRelation(ValueError):pass

def compatibility_mapper():
    from newclid.rule_matching.mapping_matcher import FilterMapper
    from newclid.problem import PredicateConstruction
    class CompatMapper(FilterMapper):
        """Map the exact stored triangle predicate type and validate instances.
        Work around missing CONTRI efficient matching in upstream 3.0.1.
        The official MappingMatcher still checks every rule premise.
        """
        def candidate_mappings(self,rule,points,proof):
            triangles=[c for c in rule.premises if c.name in ['contri','contrir','simtri','simtrir']]
            if len(triangles)==1 and set(rule.variables)<=set(triangles[0].variables):
                premise=triangles[0]
                for predicate in tuple(proof.graph.hyper_graph):
                    if predicate.predicate_type.value!=premise.name:continue
                    tokens=predicate.to_tokens()
                    for order in itertools.permutations(range(3)):
                        args=tuple(tokens[i] for i in order)+tuple(tokens[i+3] for i in order)
                        yield dict(zip(premise.variables,args))
                        yield dict(zip(premise.variables,args[3:]+args[:3]))
            else:yield from super().mappings(rule,points,proof)
        def mappings(self,rule,points,proof):
            for mapping in self.candidate_mappings(rule,points,proof):
                try:
                    for clause in rule.premises+rule.conclusions:
                        PredicateConstruction.from_str(clause.name+' '+' '.join(mapping[x] for x in clause.variables))
                except (ValueError,KeyError):continue
                yield mapping
    return CompatMapper()

def run(data):
    from newclid.api import GeometricSolverBuilder, PythonDefault
    from newclid.problem import ProblemSetup, PredicateConstruction, predicate_to_construction
    from newclid.symbols.points_registry import Point
    from newclid.numerical.geometries import PointNum
    from newclid.proof_data import proof_data_from_state
    from newclid.proof_writing import write_proof
    from itertools import combinations

    p=data['problem']
    mapping={}
    limitations=[]
    assumptions=[]
    def canonical(raw):return PredicateConstruction.from_str(raw)
    def display(predicate):
        # Upstream 3.0.1 prints its similarity predicates with a congruence
        # symbol. Keep the exact predicate semantics in the student view.
        if predicate.predicate_type.value in ['simtri','simtrir']:
            a=[str(v).upper() for v in predicate.to_tokens()]
            return '△'+''.join(a[:3])+' ∽ △'+''.join(a[3:])
        return str(predicate)
    def relation(r):
        a=[v.lower() for v in r['args']]
        kind=r['kind']
        names={'equal_length':'cong','midpoint':'midp','perpendicular':'perp','parallel':'para','collinear':'coll'}
        if kind in names:return names[kind]+' '+' '.join(a)
        if kind=='fixed_angle' and r.get('value')==90:
            # The middle point is the vertex. An exact right interior angle
            # is equivalent to its two nonzero supporting edges being perp.
            return 'perp '+' '.join([a[0],a[1],a[1],a[2]])
        if kind=='length_ratio':
            ratio=Fraction(str(r['value']))
            if ratio<=0:raise UnsupportedRelation('长度比必须是正数。')
            return 'rconst '+' '.join(a)+f' {ratio.numerator}/{ratio.denominator}'
        if kind=='on_segment':
            if r is p['goal']:raise UnsupportedRelation('Newclid 当前不直接支持严格线段内部点作为目标；未将其降格为共线目标，仍可查看 Z3 对完整目标的核验。')
            limitations.append('内部点条件的共线推论供 Newclid 使用；严格内部性由 Z3 完整编码并独立核验。')
            return 'coll '+' '.join(a)
        if kind=='on_circle':return 'cong '+' '.join([a[0],a[1],a[2],a[1]])
        if kind=='equal_angle':
            if r is not p['goal']:raise UnsupportedRelation('当前 Newclid 适配尚不接收内角相等作为前提；没有忽略该条件。')
            return 'eqangle '+' '.join([a[0],a[1],a[1],a[2],a[3],a[4],a[4],a[5]])
        raise UnsupportedRelation('Newclid 未支持关系：'+kind)
    def relations(r):
        if r['kind']!='similar_triangles':return [relation(r)]
        # Unoriented SSS similarity is a conjunction, never a guessed simtri or
        # simtrir orientation chosen from the drawing. Both reflected cases stay.
        a,b,c,d,e,f=[v.lower() for v in r['args']]
        return [f'eqratio {a} {b} {a} {c} {d} {e} {d} {f}',
                f'eqratio {a} {b} {b} {c} {d} {e} {e} {f}',
                f'ncoll {a} {b} {c}',f'ncoll {d} {e} {f}']
    for r in p['conditions']:
        if not r['enabled']:continue
        for raw in relations(r):
            c=canonical(raw); assumptions.append(c);mapping.setdefault(str(c),[]).append(r['id'])
    if p['nondegenerate']['distinct']:
        for a,b in combinations(p['points'],2):
            c=canonical(f"diff {a['id'].lower()} {b['id'].lower()}"); assumptions.append(c);mapping[str(c)]=['domain']
    for t in p['nondegenerate']['triangles']:
        c=canonical('ncoll '+' '.join(v.lower() for v in t));assumptions.append(c);mapping[str(c)]=['domain']
    goals=list({str(c):c for c in (canonical(raw) for raw in relations(p['goal']))}.values())
    problem=ProblemSetup(name=p['title'],points=tuple(Point(name=q['id'].lower(),num=PointNum(x=q['x'],y=q['y'])) for q in p['points']),assumptions=tuple(assumptions),goals=tuple(goals))
    from newclid.all_rules import ALL_RULES, DEACTIVATED_RULES
    from newclid.rule_matching.mapping_matcher import MappingMatcher
    from newclid.justifications.justification import Reflexivity
    from newclid.predicates import predicate_from_construction
    # Use the official deductive rules, including ones DEFAULT_RULES leaves
    # to AR, without activating upstream's explicitly deactivated rules.
    builder=GeometricSolverBuilder(rng=0,api_default=PythonDefault(use_sympy_ar=False))
    safe_rules=[]
    for r in ALL_RULES:
        if r in DEACTIVATED_RULES:continue
        if not all(str(a)[0].isalpha() for c in r.premises+r.conclusions for a in c.variables):continue
        premises=[]
        for raw in r.premises_txt:
            name,*args=raw.split()
            if name=='diff' and len(args)>2:
                premises.extend('diff '+' '.join(pair) for pair in combinations(args,2))
            else:premises.append(raw)
        safe_rules.append(r.model_copy(update={'premises_txt':tuple(premises)}))
    builder.with_rule_matcher(MappingMatcher(compatibility_mapper()))
    solver=builder.with_rules(safe_rules).with_deductors([]).build(problem)
    # Explicitly register true common-side identities as official Reflexivity
    # justifications; these become T-nodes, never added givens.
    for a,b in combinations(problem.points,2):
        reflexive=predicate_from_construction(canonical(f'cong {a.name} {b.name} {a.name} {b.name}'),solver.proof_state.symbols.points)
        solver.proof_state.apply(Reflexivity(predicate=reflexive))
    found=solver.run()
    if not found:
        return {'status':'not_found','message':'在当前演绎规则子集内未找到证明；结论另由精确约束核验。','engine':'Newclid 3.0.1','steps':[],'assumptionNodes':[],'input':problem.pretty_str()}
    proof=proof_data_from_state(goals,solver.proof_state)
    nodes=[]
    for a in proof.construction_assumptions:
        construction=str(predicate_to_construction(a.predicate))
        nodes.append({'id':'nc-'+a.id,'statement':display(a.predicate),'premises':mapping.get(construction,['domain'])})
    for a in proof.trivial_predicates:
        nodes.append({'id':'nc-'+a.id,'statement':display(a.predicate),'premises':[]})
    numerical=[]
    for a in proof.numerical_checks:
        c=predicate_to_construction(a.predicate)
        numerical.append({'id':'nc-'+a.id,'type':c.predicate_type.value,'args':list(c.args),'statement':display(a.predicate)})
    steps=[]
    for s in proof.proof_steps:
        reason=getattr(s.justification,'rule',None)
        label=getattr(reason,'description',None) or s.justification.dependency_type.value
        steps.append({'id':'nc-'+s.proven_predicate.id,'statement':display(s.proven_predicate.predicate),'rule':str(label),'premises':['nc-'+v for v in s.applied_on_predicates]})
    limitations.append('Newclid 3.0.1 使用已记录的兼容适配：展开多点互异，注册公共边自反性，补足三角形谓词匹配；使用官方未停用的演绎规则子集，未启用当前存在运行及依赖回溯问题的 AR 模块。中点推论由官方规则产生，未修改上游源码或规则结论。')
    return {'status':'found' if found else 'not_found','id':'newclid','title':'Newclid 搜索证明','engine':'Newclid 3.0.1','steps':steps,'assumptionNodes':nodes,'numericalChecks':numerical,'raw':write_proof(proof),'input':problem.pretty_str(),'limitations':list(set(limitations)),'assumptionIds':[r['id'] for r in p['conditions'] if r['enabled']]}

if __name__=='__main__':
    data=json.load(sys.stdin)
    try:
        with contextlib.redirect_stdout(io.StringIO()):result=run(data)
    except Exception as e:
        result={'status':'unsupported' if isinstance(e,UnsupportedRelation) else 'error','message':str(e),'engine':'Newclid 3.0.1'}
        if not isinstance(e,UnsupportedRelation):traceback.print_exc(file=sys.stderr)
    print(json.dumps(result,ensure_ascii=False))
