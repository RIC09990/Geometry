"""Relation-to-polynomial adapter. Each instance owns its Z3 context."""
from itertools import combinations
from fractions import Fraction
import z3
from .models import Problem, Relation
from .algebra import verify_witness

class ConstraintSystem:
    def __init__(self, problem: Problem, timeout=6000, normalize=True, *, layout_frame=False):
        self.problem=problem
        self.normalized=normalize
        self.timeout=timeout
        self.ctx=z3.Context()
        self.xy={p.id:(z3.Real(p.id+"_x",ctx=self.ctx),z3.Real(p.id+"_y",ctx=self.ctx)) for p in problem.points}
        # Use the actual real-polynomial decision tactic rather than the generic
        # SMT dispatcher, which can time out even on midpoint/SSS identities.
        self.solver=z3.Tactic('qfnra-nlsat',ctx=self.ctx).solver()
        self.solver.set(timeout=timeout)
        if any(r.enabled and r.kind=='fixed_angle' for r in problem.conditions):
            # Use a variable order suited to algebraic angle coefficients.
            self.solver.set(variable_ordering_strategy=1)
        if not normalize:
            # Display layouts must roundtrip through the public Point schema.
            # Do not impose these viewport bounds on universal theorem checks.
            for xy in self.xy.values():
                for value in xy:self.solver.add(value>=-10000,value<=10000)
        # Fix a coordinate frame without restricting shapes. Metric lengths
        # retain their scale, and directed arcs retain their orientation.
        # This is a WLOG normalization, not measured coordinates as premises.
        # A change of coordinates must preserve the statement being tested as
        # well as its premises. Otherwise BC=1, B=(0,0), or a directed arc can
        # become true solely because of the chosen coordinate frame.
        active=[r for r in problem.conditions if r.enabled]
        relevant=active if layout_frame else [*active,problem.goal]
        triangle=problem.nondegenerate.triangles[0] if problem.nondegenerate.triangles else None
        angle=next((r.args for r in active if r.kind=='fixed_angle'),None) if layout_frame else None
        self.frame=None
        if normalize and (triangle or angle) and not any(r.kind=='fixed_point' for r in relevant):
            a,b,c=triangle or angle
            metric=any(r.kind in ('minimize','fixed_length') for r in relevant)
            oriented=any(r.kind=='on_arc' for r in relevant)
            arc=next((r for r in active if r.kind=='on_arc'),None)
            if arc:
                center=arc.args[1];start=arc.args[3] if arc.orientation=='cw' else arc.args[2]
                self.frame=(center,start)
                length=next((r.value for r in active if r.kind=='fixed_length' and set(r.args)=={center,start}),None)
                self.solver.add(self.xy[center][0]==0,self.xy[center][1]==0,self.xy[start][1]==0,
                    self.xy[start][0]==z3.RealVal(str(length),ctx=self.ctx) if length is not None else self.xy[start][0]>0 if metric else self.xy[start][0]==1)
            else:
                self.frame=(b,c)
                self.solver.add(self.xy[b][0]==0,self.xy[b][1]==0,self.xy[c][1]==0,
                                self.xy[c][0]>0 if metric else self.xy[c][0]==1)
                if not oriented:self.solver.add(self.xy[a][1]>0)
        if problem.nondegenerate.distinct:
            for a,b in combinations(self.xy,2): self.solver.add(self.d2(a,b)>0)
        for a,b,c in problem.nondegenerate.triangles:
            self.solver.add(self.cross(self.vec(a,b),self.vec(a,c))!=0)
        for r in problem.conditions:
            if r.enabled and r.kind=='free_text':raise ValueError('文字条件尚未转成精确约束，不能跳过后核验结论。')
            if r.enabled:self.solver.add(self.encode(r))

    def vec(self,a,b):return tuple(y-x for x,y in zip(self.xy[a],self.xy[b]))
    def dot(self,u,v):return u[0]*v[0]+u[1]*v[1]
    def cross(self,u,v):return u[0]*v[1]-u[1]*v[0]
    def d2(self,a,b):
        v=self.vec(a,b)
        return self.dot(v,v)

    def encode(self,r:Relation):
        a=r.args
        k=r.kind
        And=z3.And
        if k=="equal_length":return self.d2(*a[:2])==self.d2(*a[2:])
        if k=='fixed_length':return self.d2(*a)==z3.RealVal(str(r.value),ctx=self.ctx)**2
        if k=='fixed_point':return And(*[self.xy[a[0]][i]==z3.RealVal(str(value),ctx=self.ctx) for i,value in enumerate(r.coordinates)])
        if k=='inside_triangle':
            point,u,v,w=a
            sides=[self.cross(self.vec(start,end),self.vec(start,point)) for start,end in [(u,v),(v,w),(w,u)]]
            return z3.Or(And(*[side>0 for side in sides]),And(*[side<0 for side in sides]))
        if k in ('inside_circle','outside_circle'):
            distance,radius=self.d2(a[0],a[1]),self.d2(a[2],a[1])
            return And(radius>0,distance<radius if k=='inside_circle' else distance>radius)
        if k in ('same_side','opposite_side'):
            line=self.vec(a[2],a[3])
            product=self.cross(line,self.vec(a[2],a[0]))*self.cross(line,self.vec(a[2],a[1]))
            return And(self.dot(line,line)>0,product>0 if k=='same_side' else product<0)
        if k=='fixed_angle':
            from .angles import cosine_constant
            u,v=self.vec(a[1],a[0]),self.vec(a[1],a[2])
            n=self.dot(u,u)*self.dot(v,v);p=self.dot(u,v)
            c=cosine_constant(r.value,self.ctx)
            if r.value==90:return And(n>0,p==0)
            tangent=z3.simplify((1-c*c)**z3.RealVal('1/2',ctx=self.ctx)/c)
            cross=self.cross(u,v)
            return And(n>0,z3.Or(cross==tangent*p,cross==-tangent*p),p>0 if r.value<90 else p<0)
        if k=='length_ratio':
            numerator,denominator=self.d2(*a[:2]),self.d2(*a[2:])
            ratio=z3.RealVal(str(r.value),ctx=self.ctx)
            return And(denominator>0,numerator==ratio*ratio*denominator)
        if k=='similar_triangles':
            p,q,r0,u,v,w=a
            first=[self.d2(p,q),self.d2(p,r0),self.d2(q,r0)]
            second=[self.d2(u,v),self.d2(u,w),self.d2(v,w)]
            return And(self.cross(self.vec(p,q),self.vec(p,r0))!=0,
                       self.cross(self.vec(u,v),self.vec(u,w))!=0,
                       first[0]*second[1]==first[1]*second[0],
                       first[0]*second[2]==first[2]*second[0])
        if k=="midpoint":return And(*[2*self.xy[a[0]][i]==self.xy[a[1]][i]+self.xy[a[2]][i] for i in [0,1]])
        if k in ["perpendicular","parallel"]:
            u,v=self.vec(*a[:2]),self.vec(*a[2:])
            eq=self.dot(u,v)==0 if k=="perpendicular" else self.cross(u,v)==0
            return And(eq,self.dot(u,u)>0,self.dot(v,v)>0)
        if k in ["collinear","on_segment"]:
            u,v=self.vec(a[1],a[0]),self.vec(a[1],a[2])
            col=self.cross(u,v)==0
            return col if k=="collinear" else And(col,self.dot(u,v)>0,self.dot(u,v)<self.dot(v,v))
        if k=="on_circle":return And(self.d2(a[2],a[1])>0,self.d2(a[0],a[1])==self.d2(a[2],a[1]))
        if k=='on_arc':
            point,center,start,end=a
            if r.orientation=='cw':start,end=end,start
            u,v,w=self.vec(center,start),self.vec(center,end),self.vec(center,point)
            return And(self.d2(center,start)>0,self.d2(start,end)>0,
                       self.d2(center,point)==self.d2(center,start),
                       self.d2(center,end)==self.d2(center,start),
                       self.cross(u,v)>=0,self.cross(u,w)>=0,self.cross(w,v)>=0)
        if k=="equal_angle":
            u,v,w,t=self.vec(a[1],a[0]),self.vec(a[1],a[2]),self.vec(a[4],a[3]),self.vec(a[4],a[5])
            n,m=self.dot(u,u)*self.dot(v,v),self.dot(w,w)*self.dot(t,t)
            p,q=self.dot(u,v),self.dot(w,t)
            return And(n>0,m>0,p*p*m==q*q*n,p*q>=0)
        raise ValueError(f"Unsupported: {k}")

    def coordinates(self, model):
        out={}
        for name,xy in self.xy.items():
            vals=[model.eval(v,model_completion=True) for v in xy]
            if not all(z3.is_rational_value(v) for v in vals):
                raise ValueError("模型包含代数数，当前未完成独立精确核验")
            out[name]=[str(Fraction(v.numerator_as_long(),v.denominator_as_long())) for v in vals]
        return out

    def real(self, value):
        return z3.RealVal(str(value),ctx=self.ctx)

    def placement_bounds(self, xy, points, tolerance):
        radius=self.real(tolerance)
        for point in points:
            for coordinate,value in zip(xy[point.id],(point.x,point.y)):
                center=self.real(value)
                if tolerance:
                    yield z3.And(coordinate>=center-radius,coordinate<=center+radius)
                else:
                    yield coordinate==center

    def display_points(self, xy):
        from .angles import display_number
        return [{'id':p.id,'x':display_number(xy[p.id][0]),'y':display_number(xy[p.id][1]),'fixed':p.fixed}
                for p in self.problem.points]

    def check_placement(self, points=(), tolerance=0):
        self.solver.push()
        try:
            self.solver.add(*self.placement_bounds(self.xy,points,tolerance))
            status=self.solver.check()
            if status==z3.unknown:
                return {'status':'unknown','solverReason':self.solver.reason_unknown(),
                        'message':'本次图形计算未完成，不能据此判断条件矛盾。请稍后重试。'}
            if status==z3.unsat:
                return {'status':'unsat','message':'当前条件无法同时满足，或拖动位置不符合保留条件'}
            model=self.solver.model()
            xy={name:[model.eval(v,model_completion=True) for v in point] for name,point in self.xy.items()}
            result={'status':'sat','points':self.display_points(xy)}
            try:
                result['exactCoordinates']=self.coordinates(model)
            except ValueError:
                result['approximateDisplay']=True
            return result
        finally:
            self.solver.pop()

    def layout(self,pinned=None,fixed_points=(),pin_tolerance=0):
        points=self.problem.points
        fixed_ids=set(fixed_points)
        anchors=[p for p in points if p.id in fixed_ids]
        if pinned:
            anchors.append(pinned)
        entire_placement={p.id for p in points}=={p.id for p in anchors}
        active=[r for r in self.problem.conditions if r.enabled]
        angle_shape=not self.normalized and any(r.kind=='fixed_angle' for r in active)
        if angle_shape and entire_placement and pin_tolerance:
            witness=self.angle_layout(active,anchors,pin_tolerance,follow_placement=True)
            if witness:
                return witness

        self.solver.push()
        try:
            self.solver.add(*self.placement_bounds(self.xy,anchors,pin_tolerance))
            # Drawing preferences are temporary restrictions on the hard bounds.
            # A timeout in a small neighbourhood says nothing about a broader one.
            self.solver.set(timeout=min(self.timeout,300))
            if entire_placement and angle_shape:
                result=self.check_placement()
                if result['status']!='unknown':
                    return result
            if not entire_placement:
                nearby=[p for p in points if p.id not in {a.id for a in anchors}]
                for radius in (0,0.00001):
                    result=self.check_placement(nearby,radius)
                    if result['status']=='sat':
                        return result
            if angle_shape:
                witness=self.angle_layout(active,anchors,pin_tolerance)
                if witness:
                    return witness
            if not entire_placement:
                for radius in (0.01,0.25,1,4):
                    result=self.check_placement(nearby,radius)
                    if result['status']=='sat':
                        return result
                base_ids=self.problem.nondegenerate.triangles[0][1:] if self.problem.nondegenerate.triangles else [p.id for p in points[1:3]]
                result=self.check_placement([p for p in nearby if p.id in base_ids])
                if result['status']=='sat':
                    return result
            self.solver.set(timeout=self.timeout)
            return self.check_placement()
        finally:
            self.solver.pop()
            self.solver.set(timeout=self.timeout)

    def angle_layout(self, active, anchors, tolerance, *, follow_placement=False):
        """Find an exact shape first, then fit it to the hard layout constraints."""
        from .angle_construction import exact_angle_models
        absolute=[r for r in active if r.kind in ('fixed_point','fixed_length')]
        positions={p.id:p for p in [*self.problem.points,*anchors]}
        shape=self.problem.model_copy(update={
            'conditions':[r for r in active if r.kind not in ('fixed_point','fixed_length')],
            'points':list(positions.values()),
        })
        constructed=exact_angle_models(shape,follow_placement=follow_placement,layout=True)
        if constructed is not None:
            models=constructed['models']
            seed=constructed['seed']
        elif follow_placement:
            return None
        else:
            system=ConstraintSystem(shape,timeout=self.timeout,layout_frame=True)
            if system.solver.check()!=z3.sat:
                return None
            model=system.solver.model()
            models=[{name:[model.eval(v,model_completion=True) for v in point] for name,point in system.xy.items()}]
            seed=system.frame

        orientations=(1,) if any(r.kind=='on_arc' for r in active) else (1,-1)
        for model in models:
            for orientation in orientations:
                xy=self.fit_angle_model(model,seed,positions,absolute,orientation)
                if xy is None:
                    continue
                if all(z3.is_true(z3.simplify(bound)) for bound in self.placement_bounds(xy,anchors,tolerance)):
                    return {'status':'sat','points':self.display_points(xy),'approximateDisplay':True}
        return None

    def fit_angle_model(self, model, seed, positions, absolute, orientation):
        # A nonzero similarity preserves the shape predicates. Reflections
        # are only tried when there is no directed arc among the premises.
        simplify=z3.simplify
        def delta(a,b):
            return tuple(simplify(x-y) for x,y in zip(a,b))
        def nonzero(vector):
            return any(not z3.is_true(simplify(v==0)) for v in vector)

        model={name:(x.translate(self.ctx),orientation*y.translate(self.ctx)) for name,(x,y) in model.items()}
        fixed={r.args[0]:tuple(map(self.real,r.coordinates)) for r in absolute if r.kind=='fixed_point'}
        target={**{name:(self.real(p.x),self.real(p.y)) for name,p in positions.items()},**fixed}
        start=next(iter(fixed),seed[0])
        for end in dict.fromkeys([*fixed,*seed,*model]):
            u=delta(model[end],model[start])
            v=delta(target[end],target[start])
            if nonzero(u) and nonzero(v):
                break
        else:
            return None

        length_squared=simplify(self.dot(u,u))
        real=simplify(self.dot(u,v)/length_squared)
        imaginary=simplify(self.cross(u,v)/length_squared)
        metric=next((r for r in absolute if r.kind=='fixed_length' and r.value>0),None)
        if metric and end not in fixed:
            edge=delta(model[metric.args[0]],model[metric.args[1]])
            if not nonzero(edge):
                return None
            # Keep the direction from the sketch but set scale from the given length.
            placed_length=z3.Sqrt(self.dot(v,v)*self.dot(edge,edge)/length_squared)
            factor=simplify(self.real(metric.value)/placed_length)
            real,imaginary=simplify(real*factor),simplify(imaginary*factor)

        xy={}
        tx,ty=target[start]
        for name,point in model.items():
            x,y=delta(point,model[start])
            xy[name]=(simplify(tx+real*x-imaginary*y),simplify(ty+imaginary*x+real*y))
        if any(not z3.is_true(simplify(z3.And(v>=-10000,v<=10000))) for point in xy.values() for v in point):
            return None
        for relation in absolute:
            substitutions=[(variable,value) for name in set(relation.args) for variable,value in zip(self.xy[name],xy[name])]
            if not z3.is_true(simplify(z3.substitute(self.encode(relation),*substitutions))):
                return None
        return xy

    def analyze(self):
        if self.problem.goal.kind=='angle_value':
            from .angle_construction import analyze_constructed_angle
            constructed=analyze_constructed_angle(self.problem)
            if constructed is not None:return constructed
        consistency=self.solver.check()
        if consistency==z3.unsat:return {"outcome":"inconsistent","message":"条件矛盾或非退化要求无法满足"}
        if consistency==z3.unknown:return {"outcome":"unknown","message":"本次条件计算未完成，当前无法确定结论。请稍后重试，或生成 AI 解答。","solverReason":self.solver.reason_unknown()}
        if self.problem.goal.kind=='angle_value':return self.angle_value()
        self.solver.add(z3.Not(self.encode(self.problem.goal)))
        check=self.solver.check()
        if check==z3.unsat:
            return {"outcome":"proven","message":"在已编码的条件和非退化要求下，目标的否定不可满足。","engine":"Z3","encoding":"exact real polynomial constraints"}
        if check==z3.unknown:return {"outcome":"unknown","message":"本次结论核验未完成，不能据此判断结论错误。请稍后重试，或生成 AI 解答。","solverReason":self.solver.reason_unknown()}
        try:
            coords=self.coordinates(self.solver.model())
            validation=verify_witness(self.problem,coords)
            if not validation["verified"]:return {"outcome":"unknown","message":"候选反例未通过独立精确核验"}
            return {"outcome":"counterexample","message":"找到满足全部保留条件、违反目标的非退化反例。","counterexample":{"coordinates":coords,**validation},"engine":"Z3 + SymPy"}
        except ValueError as e:
            return {"outcome":"unknown","message":str(e)}

    def entails(self,relation):
        self.solver.push()
        self.solver.add(z3.Not(self.encode(relation)))
        check=self.solver.check()
        self.solver.pop()
        return check==z3.unsat

    def angle_value(self):
        import math
        from .angles import display_number, supported_angle
        a,b,c=self.problem.goal.args
        model=self.solver.model()
        u=[display_number(model.eval(v,model_completion=True)) for v in self.vec(b,a)]
        v=[display_number(model.eval(v,model_completion=True)) for v in self.vec(b,c)]
        n=math.hypot(*u)*math.hypot(*v)
        if n<1e-15:return {'outcome':'unknown','message':'这个角的一条边长度为零，无法确定角度。'}
        estimate=math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(u,v))/n))))
        candidate=float(Fraction(estimate).limit_denominator(360))
        if abs(candidate-estimate)>1e-7:return {'outcome':'unknown','message':'当前尚未求得可精确核验的角度值。'}
        try:
            supported_angle(candidate)
            conclusion=Relation(id='angle-answer',kind='fixed_angle',args=[a,b,c],value=candidate)
            self.solver.push();self.solver.add(z3.Not(self.encode(conclusion)))
            check=self.solver.check();self.solver.pop()
        except ValueError:
            return {'outcome':'unknown','message':'当前尚未求得可精确核验的角度值。'}
        if check==z3.sat:return {'outcome':'unknown','message':'这些条件不能唯一确定这个角，请补充条件。'}
        if check!=z3.unsat:return {'outcome':'unknown','message':'角度核验超时，当前无法确定答案。'}
        label=f'∠{a}{b}{c} = {candidate:g}°'
        return {'outcome':'proven','message':label,'engine':'Z3','angleAnswer':{'value':candidate,'args':[a,b,c]},'proofs':[]}
