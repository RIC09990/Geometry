"""Exhaustive exact ray intersections for constructible angle frameworks.

Each new point must be the intersection of rays at two already placed vertices.
Both signs of every unsigned angle are enumerated. Degenerate continuous
branches or resource limits abort the method; a partial enumeration is never
used to claim uniqueness. All original relations filter the exact candidates.
"""
from itertools import combinations
from fractions import Fraction
import time
import z3
from .angles import cosine_constant,display_number,supported_angle
from .models import Relation


def construction_plan(problem):
    ids=[p.id for p in problem.points]
    angles=[r for r in problem.conditions if r.enabled and r.kind=='fixed_angle']
    if len(ids)>12 or len(angles)<2:return None
    preferred=[tuple(problem.nondegenerate.triangles[0][1:])] if problem.nondegenerate.triangles else []
    for seed in dict.fromkeys([*preferred,*combinations(ids,2)]):
        known=set(seed);steps=[]
        while len(known)<len(ids):
            found=False
            for point in ids:
                if point in known:continue
                supports=[]
                for r in angles:
                    a,vertex,c=r.args
                    if vertex not in known:continue
                    reference=c if a==point else a if c==point else None
                    if reference in known:supports.append((vertex,reference,r.value))
                pair=next(((u,v) for u,v in combinations(supports,2) if u[0]!=v[0]),None)
                if pair:
                    steps.append((point,*pair));known.add(point);found=True;break
            if not found:break
        if len(known)==len(ids):return seed,steps
    return None


def exact_angle_models(problem, *, follow_placement=False, layout=False):
    active=[r for r in problem.conditions if r.enabled]
    if any(r.kind in ('fixed_point','fixed_length','free_text') for r in active) or (not layout and problem.goal.kind=='minimize'):return None
    plan=construction_plan(problem)
    if plan is None:return None
    # Lazy import keeps the general constraint encoder independent of this path.
    from .constraints import ConstraintSystem
    system=ConstraintSystem(problem,normalize=False)
    ctx=system.ctx;zero=z3.RealVal(0,ctx=ctx);one=z3.RealVal(1,ctx=ctx)
    seed,steps=plan;models=[{seed[0]:(zero,zero),seed[1]:(one,zero)}]
    placement={p.id:(p.x,p.y) for p in problem.points} if follow_placement else None
    started=time.monotonic();examined=0
    simplify=z3.simplify
    def positive(value):return z3.is_true(simplify(value>0))
    def equal_zero(value):return z3.is_true(simplify(value==0))
    def sub(a,b):return tuple(simplify(x-y) for x,y in zip(a,b))
    def cross(a,b):return simplify(a[0]*b[1]-a[1]*b[0])
    encoded=[(r,system.encode(r)) for r in active]
    bearings={};unit_directions={}
    def ray_key(model,vertex,reference):return (vertex,reference,*[value.get_id() for name in (vertex,reference) for value in model[name]])
    bearings[ray_key(models[0],seed[0],seed[1])]=Fraction(0)
    bearings[ray_key(models[0],seed[1],seed[0])]=Fraction(180)
    def accepts(model,added=None,supports=()):
        substitutions=[(variable,value) for name,point in model.items() for variable,value in zip(system.xy[name],point)]
        for r,expression in encoded:
            # These two angles are already exact consequences of the ray's
            # cosine/sine rotation and the strictly positive intersection
            # parameters. Re-solving their expanded algebraic identities at
            # every branch can dominate a multi-point construction.
            if r.kind=='fixed_angle' and any(r.args[1]==vertex and set((r.args[0],r.args[2]))=={added,reference} and r.value==degree for vertex,reference,degree in supports):continue
            if (added is None or added in r.args) and all(name in model for name in r.args) and not z3.is_true(simplify(z3.substitute(expression,*substitutions))):return False
        if problem.nondegenerate.distinct:
            for a,b in combinations(model,2):
                if added is not None and added not in (a,b):continue
                if all(equal_zero(value) for value in sub(model[a],model[b])):return False
        for a,b,c in problem.nondegenerate.triangles:
            if added is not None and added not in (a,b,c):continue
            if all(name in model for name in (a,b,c)) and equal_zero(cross(sub(model[b],model[a]),sub(model[c],model[a]))):return False
        return True
    def directions(model,support):
        vertex,reference,degree=support;origin=model[vertex];u=sub(model[reference],origin)
        bearing=bearings.get(ray_key(model,vertex,reference))
        if bearing is not None:
            angles=[(bearing+sign*Fraction(str(degree)))%360 for sign in (1,-1)]
            for angle in angles:
                if angle in unit_directions:continue
                if angle in (0,90,180,270):
                    unit_directions[angle]={0:(one,zero),90:(zero,one),180:(-one,zero),270:(zero,-one)}[angle]
                else:
                    cosine=cosine_constant(str(angle if angle<180 else 360-angle),ctx)
                    sine=simplify((1-cosine*cosine)**z3.RealVal('1/2',ctx=ctx))
                    unit_directions[angle]=(cosine,sine if angle<180 else -sine)
            return origin,[unit_directions[angle] for angle in angles],angles
        cosine=cosine_constant(degree,ctx);sine=simplify((1-cosine*cosine)**z3.RealVal('1/2',ctx=ctx))
        return origin,[(simplify(cosine*u[0]-sign*sine*u[1]),simplify(sign*sine*u[0]+cosine*u[1])) for sign in (1,-1)],[None,None]
    def ray_indices(point,support):
        if placement is None:return (0,1)
        vertex,reference,_=support
        u,v,w=placement[vertex],placement[reference],placement[point]
        orientation=(v[0]-u[0])*(w[1]-u[1])-(v[1]-u[1])*(w[0]-u[0])
        # A display check only needs a witness on the branch being shown.
        # The exact tests above still check every retained premise.
        return (0,) if orientation>0 else (1,) if orientation<0 else (0,1)
    models=[model for model in models if accepts(model)]
    for point,first,second in steps:
        next_models=[]
        for model in models:
            origin,first_rays,first_angles=directions(model,first);other,second_rays,second_angles=directions(model,second)
            delta=sub(other,origin)
            for first_index in ray_indices(point,first):
                for second_index in ray_indices(point,second):
                    u,v=first_rays[first_index],second_rays[second_index]
                    examined+=1
                    if examined>2048 or time.monotonic()-started>10:return None
                    denominator=cross(u,v)
                    if equal_zero(denominator):
                        # Coincident rays can leave a continuous family. Dropping
                        # it would make a false uniqueness certificate.
                        if equal_zero(cross(delta,u)):
                            required_triangles=[*problem.nondegenerate.triangles,*[r.args[1:] for r in active if r.kind=='inside_triangle']]
                            forbidden=False
                            for triangle in required_triangles:
                                others=[name for name in triangle if name!=point]
                                if point in triangle and len(others)==2 and all(name in model and equal_zero(cross(sub(model[name],origin),u)) for name in others):
                                    forbidden=True;break
                            if forbidden:continue
                            return None
                        continue
                    t=simplify(cross(delta,v)/denominator);s=simplify(cross(delta,u)/denominator)
                    if not positive(t) or not positive(s):continue
                    candidate={**model,point:tuple(simplify(origin[i]+t*u[i]) for i in (0,1))}
                    if accepts(candidate,point,(first,second)):
                        next_models.append(candidate)
                        for support,angle in ((first,first_angles[first_index]),(second,second_angles[second_index])):
                            if angle is not None:
                                bearings[ray_key(candidate,support[0],point)]=angle
                                bearings[ray_key(candidate,point,support[0])]=(angle+180)%360
        models=next_models
        if not models:break
    return {'system':system,'models':models,'steps':steps,'seed':seed,'complete':not follow_placement}


def analyze_constructed_angle(problem):
    constructed=exact_angle_models(problem)
    if constructed is None:return None
    models=constructed['models'];system=constructed['system']
    if not models:return {'outcome':'inconsistent','message':'已穷举角度构造的全部分支，没有位置满足全部保留条件。','engine':'精确角约束构造'}
    import math
    from fractions import Fraction
    a,b,c=problem.goal.args;model=models[0]
    u=[display_number(z3.simplify(model[a][i]-model[b][i])) for i in (0,1)]
    v=[display_number(z3.simplify(model[c][i]-model[b][i])) for i in (0,1)]
    estimate=math.degrees(math.atan2(abs(u[0]*v[1]-u[1]*v[0]),u[0]*v[0]+u[1]*v[1]))
    value=float(Fraction(estimate).limit_denominator(360))
    if abs(value-estimate)>1e-8:return None
    try:
        supported_angle(value);claim=system.encode(Relation(id='angle-answer',kind='fixed_angle',args=[a,b,c],value=value))
    except ValueError:return None
    for model in models:
        substitutions=[(variable,coordinate) for name,point in model.items() for variable,coordinate in zip(system.xy[name],point)]
        if not z3.is_true(z3.simplify(z3.substitute(claim,*substitutions))):
            return {'outcome':'unknown','message':'存在满足保留条件、但角度不同的构造分支；这些条件不能唯一确定目标角。','engine':'精确角约束构造'}
    return {'outcome':'proven','message':f'∠{a}{b}{c} = {value:g}°；全部构造分支已用原题约束精确核验。','engine':'精确角约束构造 · Z3 代数数',
            'angleAnswer':{'value':value,'args':[a,b,c]},'proofs':[],
            'angleCertificate':{'verified':True,'method':'双射线交点的完整分支枚举 + 全部原始关系精确代入','branches':len(models)}}
