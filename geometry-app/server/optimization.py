"""Find a display candidate, then certify a lower bound and attainment with Z3.

The numerical search never becomes a proof by itself. Display anchors are not
inserted into the universal certificate as mathematical givens.
"""
import math
from fractions import Fraction
import z3
import sympy as sp
from scipy.optimize import minimize_scalar
from .constraints import ConstraintSystem
from .models import Point
from .algebraic_numbers import exact_radical


def proof_namespace(problem):
    prefix='opt-'
    while any(r.id.startswith(prefix) for r in problem.conditions):prefix+='x-'
    return lambda name:prefix+name


def canonical_goal(goal,conditions=()):
    """Combine identical unoriented distances using exact decimal arithmetic."""
    weights={}
    for a,b,w in zip(goal.args[::2],goal.args[1::2],goal.weights):
        edge=tuple(sorted((a,b)));coefficient=Fraction(str(w));seen=set()
        while True:
            if edge in seen:return goal
            seen.add(edge)
            midpoint=next((r for r in conditions if r.enabled and r.kind=='midpoint' and r.args[0] in edge and (r.args[1] in edge or r.args[2] in edge)),None)
            if midpoint is None:break
            edge=tuple(sorted(midpoint.args[1:]));coefficient/=2
        weights[edge]=weights.get(edge,Fraction(0))+coefficient
    if any(Fraction(str(float(w)))!=w for w in weights.values()):return goal
    return goal.model_copy(update={'args':[name for edge in weights for name in edge],'weights':[float(w) for w in weights.values()]})


def weighted_path(goal):
    if len(goal.weights)<2 or len(set(goal.weights))!=1:return None
    neighbors={}
    for a,b in zip(goal.args[::2],goal.args[1::2]):
        if a==b:return None
        neighbors.setdefault(a,[]).append(b);neighbors.setdefault(b,[]).append(a)
    ends=[name for name,adjacent in neighbors.items() if len(adjacent)==1]
    if len(ends)!=2 or any(len(adjacent)>2 for adjacent in neighbors.values()):return None
    path=[ends[0]]
    while path[-1]!=ends[1]:
        following=[name for name in neighbors[path[-1]] if len(path)<2 or name!=path[-2]]
        if len(following)!=1 or following[0] in path:return None
        path.append(following[0])
    if len(path)!=len(neighbors):return None
    return path


def path_certificate(problem):
    """Triangle inequality for a whole path, with every original constraint."""
    goal=canonical_goal(problem.goal,problem.conditions);path=weighted_path(goal)
    if path is None:return None
    first,last=path[0],path[-1];by_id={p.id:(p.x,p.y) for p in problem.points}
    for r in problem.conditions:
        if r.enabled and r.kind=='fixed_point':by_id[r.args[0]]=r.coordinates
    suggestion=Fraction(sum((by_id[first][i]-by_id[last][i])**2 for i in (0,1))).limit_denominator(100000)
    if suggestion<=0:return None
    system=ConstraintSystem(problem,timeout=3000)
    # First establish consistency: entailment from contradictory givens is void.
    if system.solver.check()!=z3.sat:return None
    system.solver.push();system.solver.add(system.d2(first,last)!=z3.RealVal(str(suggestion),ctx=system.ctx));constant=system.solver.check();system.solver.pop()
    if constant!=z3.unsat:return None
    direction=system.vec(first,last);length2=system.dot(direction,direction);previous=z3.RealVal(0,ctx=system.ctx)
    for point in path[1:-1]:
        ray=system.vec(first,point);parameter=system.dot(ray,direction)
        system.solver.add(system.cross(ray,direction)==0,parameter>=previous,parameter<=length2);previous=parameter
    if system.solver.check()!=z3.sat:return None
    bound=sp.Rational(str(goal.weights[0]))*sp.sqrt(sp.Rational(str(suggestion)))
    node=proof_namespace(problem);givens=[r.id for r in problem.conditions if r.enabled];term=objective_text(problem.goal)
    steps=[{'id':node('path-bound'),'statement':f'{term} ≥ {bound}。','rule':'连续使用三角不等式；两端点距离由全部保留条件精确核验','premises':['domain',*givens]},
           {'id':node('path-attain'),'statement':f'存在满足全部保留条件的位置，使 {"、".join(path)} 按顺序共线，三角不等式同时取等。','rule':'Z3 对全部轨迹、区域和联动条件检查取等可满足性','premises':['domain',*givens]},
           {'id':node('path-result'),'statement':f'{term} 的最小值为 {bound}。','rule':'下界与能够取得的等号共同确定最小值','premises':[node('path-bound'),node('path-attain')]}]
    return {'outcome':'optimized','message':'多线段路径的全局下界与取等位置已核验。','engine':'三角不等式 + Z3',
            'optimization':{'minimum':str(bound),'value':float(bound),'certificate':{'verified':True,'method':'多段路径三角不等式 + 端点距离不变性 + 全部条件下有序共线取等'}},
            'proofs':[{'id':'opt-path-route','title':'多动点路径与三角不等式','engine':'三角不等式 + Z3','status':'verified','steps':steps,'assumptionIds':givens,'assumptionNodes':[]}]}


def reflection_path_certificate(problem):
    """Unfold a polygonal path through fixed lines; certify joint attainment.

    Mirrors are derived from explicit fixed-coordinate premises and collinearity.
    Consecutive reflections preserve lengths; sampled coordinates add no givens.
    """
    goal=canonical_goal(problem.goal,problem.conditions);path=weighted_path(goal)
    if path is None:return None
    fixed={r.args[0]:tuple(sp.Rational(str(value)) for value in r.coordinates) for r in problem.conditions if r.enabled and r.kind=='fixed_point'}
    if path[0] not in fixed or path[-1] not in fixed:return None
    mirrors=[]
    for point in path[1:-1]:
        candidates=[r for r in problem.conditions if r.enabled and r.kind in ('collinear','on_segment') and point in r.args]
        line=next(([name for name in r.args if name!=point] for r in candidates if len(set(r.args))==3 and all(name in fixed for name in r.args if name!=point)),None)
        if line is None or fixed[line[0]]==fixed[line[1]]:return None
        mirrors.append((fixed[line[0]],fixed[line[1]]))
    def reflect(point,line):
        a,b=line;u=tuple(b[i]-a[i] for i in (0,1));norm=sum(x*x for x in u)
        parameter=sum((point[i]-a[i])*u[i] for i in (0,1))/norm
        return tuple(2*(a[i]+parameter*u[i])-point[i] for i in (0,1))
    unfolded=fixed[path[0]]
    for mirror in mirrors:unfolded=tuple(sp.simplify(value) for value in reflect(unfolded,mirror))
    final=fixed[path[-1]];distance2=sp.simplify(sum((final[i]-unfolded[i])**2 for i in (0,1)))
    if distance2<=0:return None
    system=ConstraintSystem(problem,timeout=4000)
    if system.solver.check()!=z3.sat:return None
    start=tuple(exact_radical(value,system.ctx) for value in unfolded);end=tuple(exact_radical(value,system.ctx) for value in final)
    direction=tuple(end[i]-start[i] for i in (0,1));norm=system.dot(direction,direction);previous=z3.RealVal(0,ctx=system.ctx)
    for index,point in enumerate(path[1:-1]):
        value=system.xy[point]
        for mirror in mirrors[index+1:]:
            line=tuple(tuple(exact_radical(v,system.ctx) for v in endpoint) for endpoint in mirror)
            value=tuple(z3.simplify(v) for v in reflect(value,line))
        delta=tuple(value[i]-start[i] for i in (0,1));parameter=system.dot(delta,direction)
        system.solver.add(system.cross(delta,direction)==0,parameter>=previous,parameter<=norm);previous=parameter
    if system.solver.check()!=z3.sat:return None
    bound=sp.simplify(sp.Rational(str(goal.weights[0]))*sp.sqrt(distance2));node=proof_namespace(problem)
    givens=[r.id for r in problem.conditions if r.enabled];term=objective_text(problem.goal)
    steps=[{'id':node('reflect'),'statement':f'依照 {len(mirrors)} 条已知直线依次作反射，展开折线路径；反射保持对应线段长度。','rule':'反射的等距性；反射轴来自原题已知','premises':['domain',*givens]},
           {'id':node('reflection-bound'),'statement':f'由展开后路径的三角不等式，{term} ≥ {bound}。','rule':'展开端点间的精确距离','premises':[node('reflect')]},
           {'id':node('reflection-attain'),'statement':'存在满足原题全部轨迹、区域及联动条件的位置，使展开后的各点按顺序共线，各处同时取等。','rule':'Z3 核验全部条件下的联合取等位置存在','premises':['domain',*givens]},
           {'id':node('reflection-result'),'statement':f'{term} 的最小值为 {bound}。','rule':'全局下界与可取到的等号','premises':[node('reflection-bound'),node('reflection-attain')]}]
    return {'outcome':'optimized','message':'连续反射路径的全局下界与联合取等位置已核验。','engine':'反射等距性 + Z3',
            'optimization':{'minimum':str(bound),'value':float(bound),'certificate':{'verified':True,'method':'连续反射展开 + 三角不等式 + 全部原始条件下的有序共线取等'}},
            'proofs':[{'id':'opt-reflection-route','title':'多动点连续反射与最短路径','engine':'反射等距性 + Z3','status':'verified','steps':steps,'assumptionIds':givens,'assumptionNodes':[]}]}


def inversion_certificate(problem):
    """A reusable circle-inversion/triangle-inequality route, not a named example."""
    goal=canonical_goal(problem.goal,problem.conditions)
    if len(goal.weights)!=2:return None
    by_id={p.id:p for p in problem.points}
    for locus in problem.conditions:
        if not locus.enabled or locus.kind not in ['on_arc','on_circle']:continue
        moving,center,start=locus.args[:3]
        focuses=[]
        for a,b in zip(goal.args[::2],goal.args[1::2]):
            if moving not in [a,b]:break
            focuses.append(b if a==moving else a)
        if len(focuses)!=2:continue
        for base,scaled in [(0,1),(1,0)]:
            c,d=focuses[base],focuses[scaled]
            k=sp.Rational(str(goal.weights[scaled]))/sp.Rational(str(goal.weights[base]));k2=k*k
            system=ConstraintSystem(problem,timeout=2500)
            def entails(expression):
                system.solver.push();system.solver.add(z3.Not(expression));answer=system.solver.check();system.solver.pop();return answer==z3.unsat
            factor=z3.RealVal(str(k2),ctx=system.ctx)
            if not entails(z3.And(system.d2(center,d)>0,system.d2(moving,center)==factor*system.d2(center,d))):continue
            e=tuple(system.xy[center][i]+factor*(system.xy[d][i]-system.xy[center][i]) for i in [0,1])
            displacement=tuple(system.xy[c][i]-e[i] for i in [0,1]);length2=system.dot(displacement,displacement)
            o,fp,cp=by_id[center],by_id[d],by_id[c]
            suggestion=Fraction(sum((getattr(cp,axis)-(getattr(o,axis)+float(k2)*(getattr(fp,axis)-getattr(o,axis))))**2 for axis in ['x','y'])).limit_denominator(10000)
            if suggestion<=0 or not entails(length2==z3.RealVal(str(suggestion),ctx=system.ctx)):continue
            # Check the inversion identity symbolically, not using sampled points.
            x,y,u,v,t=sp.symbols('x y u v t',real=True)
            identity=sp.expand((x-t**2*u)**2+(y-t**2*v)**2-t**2*((x-u)**2+(y-v)**2)-(1-t**2)*(x*x+y*y-t**2*(u*u+v*v)))
            if identity!=0:continue
            cpvec=tuple(system.xy[moving][i]-system.xy[c][i] for i in [0,1])
            cevec=tuple(e[i]-system.xy[c][i] for i in [0,1])
            system.solver.add(system.cross(cpvec,cevec)==0,system.dot(cpvec,cevec)>=0,system.dot(cpvec,cevec)<=system.dot(cevec,cevec))
            if system.solver.check()!=z3.sat:continue
            bound=sp.simplify(sp.Rational(str(goal.weights[base]))*sp.sqrt(sp.Rational(str(suggestion))))
            givens=[r.id for r in problem.conditions if r.enabled];term=objective_text(problem.goal)
            auxiliary=next((name for name in ['E','F','G','H','Q','R'] if name not in by_id),'X')
            label=str(bound).replace('sqrt','√');ratio='' if k==1 else str(k);scale='' if k2==1 else str(k2)
            coefficient='' if goal.weights[base]==1 else f'{goal.weights[base]:g}'
            node=proof_namespace(problem)
            steps=[
                {'id':node('construction'),'statement':f'在射线 {center}{d} 上取辅助点 {auxiliary}，使 {center}{auxiliary} = {scale}{center}{d}。','rule':'辅助点的定义','premises':['domain']},
                {'id':node('inversion'),'statement':f'由圆上的距离关系，{moving}{auxiliary} = {ratio}{moving}{d}。','rule':'圆的反演距离恒等式；SymPy 展开核验','premises':[node('construction'),*givens]},
                {'id':node('triangle'),'statement':f'{term} = {coefficient}({moving}{c} + {moving}{auxiliary}) ≥ {coefficient}{c}{auxiliary}。','rule':'三角不等式','premises':[node('inversion')]},
                {'id':node('distance'),'statement':f'{coefficient}{c}{auxiliary} = {label}。','rule':'保留条件下的精确距离核验','premises':[node('construction'),*givens]},
                {'id':node('equality'),'statement':f'当 {c}、{moving}、{auxiliary} 共线且 {moving} 在线段 {c}{auxiliary} 上时取等；该位置满足全部保留条件。','rule':'Z3 检查取等位置存在','premises':[node('construction'),*givens]},
                {'id':node('conclusion'),'statement':f'{term} 的最小值为 {label}。','rule':'下界成立且能够取到','premises':[node('triangle'),node('distance'),node('equality')]}]
            return {'outcome':'optimized','message':'最小值和取等位置已核验。','engine':'SymPy + Z3',
                'optimization':{'minimum':str(bound),'value':float(bound),'movingPoint':moving,'certificate':{'verified':True,'method':'反演恒等式 + 三角不等式 + 精确距离与取等可满足性核验'}},
                'proofs':[{'id':'opt-inversion-route','title':'反演与三角不等式','engine':'SymPy + Z3','status':'verified','steps':steps,'assumptionIds':givens,'assumptionNodes':[]}]}
    return None


def objective_text(goal):
    return ' + '.join(('' if w==1 else f'{w:g}')+''.join(goal.args[2*i:2*i+2]) for i,w in enumerate(goal.weights))


def locus_candidate(problem):
    by_id={p.id:p.model_copy() for p in problem.points}
    for r in problem.conditions:
        if r.enabled and r.kind=='fixed_point':by_id[r.args[0]]=Point(id=r.args[0],x=r.coordinates[0],y=r.coordinates[1])
    midpoints={r.args[0]:r.args[1:] for r in problem.conditions if r.enabled and r.kind=='midpoint'}
    relevant=set(problem.goal.args)
    for _ in range(len(by_id)):
        expanded=relevant|{name for target,ends in midpoints.items() if target in relevant for name in ends}
        if expanded==relevant:break
        relevant=expanded
    loci=[r for r in problem.conditions if r.enabled and r.kind in ['on_arc','on_circle','on_segment','collinear'] and r.args[0] in relevant]
    # A ratio defines an Apollonius circle (or its k=1 perpendicular bisector).
    for r in problem.conditions:
        if not r.enabled or r.kind!='length_ratio':continue
        common=set(r.args[:2])&set(r.args[2:])
        if len(common)==1 and next(iter(common)) in relevant:loci.append(r)
    loci.sort(key=lambda r:r.kind!='on_arc')
    if not loci:return None
    relation=loci[0];moving=relation.args[0]
    lower=0.
    if relation.kind in ('on_segment','collinear'):
        a,b=[by_id[k] for k in relation.args[1:]]
        place=lambda t:(a.x+(b.x-a.x)*t,a.y+(b.y-a.y)*t)
        upper=1. if relation.kind=='on_segment' else 100.
        if relation.kind=='collinear':lower=-100.
    elif relation.kind=='length_ratio':
        moving=next(iter(set(relation.args[:2])&set(relation.args[2:])))
        first=next(name for name in relation.args[:2] if name!=moving);second=next(name for name in relation.args[2:] if name!=moving)
        a,b=by_id[first],by_id[second];k=relation.value
        if k==1:
            distance=math.hypot(b.x-a.x,b.y-a.y)
            if distance==0:return None
            place=lambda t:((a.x+b.x)/2-t*(b.y-a.y)/distance,(a.y+b.y)/2+t*(b.x-a.x)/distance)
            lower=-100*max(1,distance);upper=-lower
        else:
            t=k if k<1 else 1/k;origin,other=(a,b) if k<1 else (b,a);factor=t*t/((1-t)*(1+t))
            cx,cy=origin.x+factor*(origin.x-other.x),origin.y+factor*(origin.y-other.y)
            radius=t*math.hypot(b.x-a.x,b.y-a.y)/abs((1-t)*(1+t))
            place=lambda parameter:(cx+radius*math.cos(parameter),cy+radius*math.sin(parameter))
            upper=2*math.pi
    else:
        center,start=[by_id[k] for k in relation.args[1:3]]
        radius=math.hypot(start.x-center.x,start.y-center.y)
        angle=math.atan2(start.y-center.y,start.x-center.x)
        sign=-1 if relation.orientation=='cw' else 1
        upper=2*math.pi
        if relation.kind=='on_arc':
            end=by_id[relation.args[3]]
            upper=(sign*(math.atan2(end.y-center.y,end.x-center.x)-angle))%(2*math.pi)
            if upper>math.pi+1e-7:return None
        place=lambda t:(center.x+radius*math.cos(angle+sign*t),center.y+radius*math.sin(angle+sign*t))
    def coordinates(t):
        xy={moving:place(t)};visiting=set()
        def resolve(name):
            if name in xy:return xy[name]
            if name in visiting:raise ValueError('联动中点定义形成循环')
            visiting.add(name)
            if name in midpoints:
                u,v=[resolve(point) for point in midpoints[name]];xy[name]=tuple((a+b)/2 for a,b in zip(u,v))
            else:xy[name]=(by_id[name].x,by_id[name].y)
            visiting.remove(name);return xy[name]
        for name in by_id:resolve(name)
        return xy
    def cost(t):
        xy=coordinates(t)
        return sum(w*math.dist(xy[a],xy[b]) for w,a,b in zip(problem.goal.weights,problem.goal.args[::2],problem.goal.args[1::2]))
    # Multiple intervals cover distinct basins; certification below is universal.
    try:values=[(cost(t),t) for t in [lower,upper]]
    except ValueError:return None
    for i in range(24):
        lo,hi=lower+(upper-lower)*i/24,lower+(upper-lower)*(i+1)/24
        result=minimize_scalar(cost,bounds=(lo,hi),method='bounded',options={'xatol':1e-11})
        values.append((float(result.fun),float(result.x)))
    value,parameter=min(values)
    # A one-dimensional search uses only one locus. It cannot authorize a
    # position when an additional retained relation excludes that position.
    # Keep every coordinate close to the candidate and check ALL conditions.
    position=place(parameter)
    if not all(math.isfinite(v) and abs(v)<=10000 for v in position):return None
    display_problem=problem.model_copy(deep=True)
    candidate_point=Point(id=moving,x=position[0],y=position[1])
    candidate_xy=coordinates(parameter)
    if any(not all(math.isfinite(value) and abs(value)<=10000 for value in point) for point in candidate_xy.values()):return None
    display_problem.points=[Point(id=p.id,x=candidate_xy[p.id][0],y=candidate_xy[p.id][1],fixed=p.fixed) for p in display_problem.points]
    checked=ConstraintSystem(display_problem,normalize=False,timeout=1000).layout(
        candidate_point,[p.id for p in display_problem.points if p.id!=moving],1e-7)
    if checked['status']!='sat':return None
    xy={p['id']:(p['x'],p['y']) for p in checked['points']}
    value=sum(w*math.dist(xy[a],xy[b]) for w,a,b in zip(problem.goal.weights,problem.goal.args[::2],problem.goal.args[1::2]))
    return {'value':value,'moving':moving,'position':xy[moving]}


def certify(problem, value):
    system=ConstraintSystem(problem,timeout=10000)
    lengths=[]
    for i,(a,b) in enumerate(zip(problem.goal.args[::2],problem.goal.args[1::2])):
        length=z3.Real(f'objective_length_{i}',ctx=system.ctx)
        system.solver.add(length>=0,length*length==system.d2(a,b));lengths.append(length)
    total=sum(z3.RealVal(str(w),ctx=system.ctx)*length for w,length in zip(problem.goal.weights,lengths))
    bound=exact_radical(value,system.ctx)
    system.solver.push();system.solver.add(total<bound);lower=system.solver.check();system.solver.pop()
    if lower!=z3.unsat:return {'verified':False,'lowerBoundStatus':str(lower)}
    system.solver.add(total==bound);attained=system.solver.check()
    return {'verified':attained==z3.sat,'lowerBoundStatus':'unsat','attainmentStatus':str(attained),
            'method':'Z3 精确实数约束：不存在更小值，并存在取等位置。'}


def analyze_minimum(problem):
    path=path_certificate(problem)
    if path:return path
    reflected=reflection_path_certificate(problem)
    if reflected:return reflected
    inversion=inversion_certificate(problem)
    if inversion:return inversion
    check=ConstraintSystem(problem,timeout=6000).solver.check()
    if check==z3.unsat:return {'outcome':'inconsistent','message':'这些条件不能同时成立。','proofs':[]}
    if check!=z3.sat:return {'outcome':'unknown','message':'条件核验超时，请稍后再试。','proofs':[]}
    candidate=locus_candidate(problem)
    if candidate is None:return {'outcome':'unknown','message':'已保留图形和条件；当前尚未找到可核验的最值位置，可继续让助手分析。','proofs':[]}
    guesses=[]
    rational=Fraction(candidate['value']).limit_denominator(10000)
    if abs(float(rational)-candidate['value'])<1e-9:guesses.append(sp.Rational(str(rational)))
    square=Fraction(candidate['value']**2).limit_denominator(10000)
    radical=sp.sqrt(sp.Rational(str(square)))
    if abs(float(radical)-candidate['value'])<1e-9 and radical not in guesses:guesses.append(radical)
    certificate={'verified':False};bound=None
    for guess in guesses:
        certificate=certify(problem,guess)
        if certificate['verified']:bound=guess;break
    term=objective_text(problem.goal);givens=[r.id for r in problem.conditions if r.enabled]
    numeric={'value':candidate['value'],'movingPoint':candidate['moving'],'position':candidate['position'],'certificate':certificate}
    if not certificate['verified']:
        return {'outcome':'unknown','message':'画板已可交互；当前找到的数值位置尚未通过全局最值核验。','optimization':numeric,'proofs':[]}
    node=proof_namespace(problem)
    steps=[{'id':node('bound'),'statement':f'由当前全部条件，{term} ≥ {bound}。','rule':'精确下界核验','premises':['domain',*givens]},
           {'id':node('attain'),'statement':f'存在满足全部条件的位置，使 {term} = {bound}。','rule':'取等条件可满足性核验','premises':['domain',*givens]},
           {'id':node('conclusion'),'statement':f'{term} 的最小值为 {bound}。','rule':'下界与取等位置共同确定最小值','premises':[node('bound'),node('attain')]}]
    return {'outcome':'optimized','message':'最小值与取等位置已核验。','engine':'Z3 最值核验',
            'optimization':{**numeric,'minimum':str(bound),'value':float(bound)},'proofs':[{'id':'opt-certificate','title':'最值的坐标约束证明',
             'engine':'Z3 精确实数约束','status':'verified','steps':steps,'assumptionIds':givens,'assumptionNodes':[]}]}
