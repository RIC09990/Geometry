"""Relation-to-polynomial adapter. Each instance owns its Z3 context."""
from itertools import combinations
from fractions import Fraction
import z3
from .models import Problem, Relation
from .algebra import verify_witness

class ConstraintSystem:
    def __init__(self, problem: Problem, timeout=6000, normalize=True):
        self.problem=problem
        self.normalized=normalize
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
        relevant=[r for r in problem.conditions if r.enabled]+[problem.goal]
        if normalize and problem.nondegenerate.triangles and not any(r.kind=='fixed_point' for r in relevant):
            a,b,c=problem.nondegenerate.triangles[0]
            metric=any(r.kind in ('minimize','fixed_length') for r in relevant)
            oriented=any(r.kind=='on_arc' for r in relevant)
            arc=next((r for r in problem.conditions if r.enabled and r.kind=='on_arc'),None)
            if arc:
                center=arc.args[1];start=arc.args[3] if arc.orientation=='cw' else arc.args[2]
                length=next((r.value for r in problem.conditions if r.enabled and r.kind=='fixed_length' and set(r.args)=={center,start}),None)
                self.solver.add(self.xy[center][0]==0,self.xy[center][1]==0,self.xy[start][1]==0,
                    self.xy[start][0]==z3.RealVal(str(length),ctx=self.ctx) if length is not None else self.xy[start][0]>0 if metric else self.xy[start][0]==1)
            else:
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

    def layout(self,pinned=None,fixed_points=(),pin_tolerance=0):
        fixed_points = set(fixed_points)
        entire_placement = {p.id for p in self.problem.points} <= fixed_points | ({pinned.id} if pinned else set())
        angle_shape=(not self.normalized
                        and not any(r.enabled and r.kind=='fixed_point' for r in self.problem.conditions)
                        and any(r.enabled and r.kind=='fixed_angle' for r in self.problem.conditions))
        angle_fallback=angle_shape and not pinned and not fixed_points
        if angle_fallback:self.solver.set(timeout=300)
        if entire_placement and pin_tolerance and angle_shape:
            witness=self.angle_layout(pinned,fixed_points,pin_tolerance,follow_placement=True)
            if witness and witness['status']=='sat':return witness
        for p in self.problem.points:
            if p.id in fixed_points:
                for i,value in enumerate([p.x,p.y]):
                    coordinate=self.xy[p.id][i]
                    # Fixed display anchors also originate in rounded browser
                    # coordinates. Use the drag's display tolerance for them;
                    # exact decimal anchors contradict e.g. an algebraic 40°.
                    # Theorem checks never use layout or these bounds.
                    if pin_tolerance:
                        self.solver.add(coordinate>=z3.RealVal(str(value-pin_tolerance),ctx=self.ctx),coordinate<=z3.RealVal(str(value+pin_tolerance),ctx=self.ctx))
                    else:self.solver.add(coordinate==z3.RealVal(str(value),ctx=self.ctx))
        if pinned:
            for i,value in enumerate([pinned.x,pinned.y]):
                coordinate=self.xy[pinned.id][i]
                if pin_tolerance:
                    self.solver.add(coordinate>=z3.RealVal(str(value-pin_tolerance),ctx=self.ctx),coordinate<=z3.RealVal(str(value+pin_tolerance),ctx=self.ctx))
                else:self.solver.add(coordinate==z3.RealVal(str(value),ctx=self.ctx))
        # Retain the exact current layout whenever it satisfies the new conditions.
        # Browser coordinates are floating point. Locking EVERY displayed decimal
        # exactly can make a midpoint miss its equation by 1e-15 and send the
        # solver to an unrelated layout. Try small neighbourhoods before releasing
        # anchors. These bounds affect display placement only, never theorem checks.
        base_ids=set(self.problem.nondegenerate.triangles[0][1:] if self.problem.nondegenerate.triangles else [p.id for p in self.problem.points[1:3]])
        groups=[(list(self.problem.points),0),
                *[(list(self.problem.points),radius) for radius in [0.00001,0.01,0.25,1,4]],
                ([p for p in self.problem.points if p.id in base_ids],0),([],0)]
        if entire_placement:
            # Every coordinate already has its submitted bound.
            groups=[([],0)]
        for group,radius in groups:
            # Removing a condition should retain a valid drawing. Only build a
            # different angle model when the current display cannot be retained.
            if angle_fallback and radius>=.01:return self.angle_layout()
            self.solver.push()
            for p in group:
                if pinned and p.id==pinned.id:continue
                for i,value in enumerate([p.x,p.y]):
                    coordinate=self.xy[p.id][i]
                    if radius:
                        self.solver.add(coordinate>=z3.RealVal(str(value-radius),ctx=self.ctx),coordinate<=z3.RealVal(str(value+radius),ctx=self.ctx))
                    else:self.solver.add(coordinate==z3.RealVal(str(value),ctx=self.ctx))
            check=self.solver.check()
            if check==z3.sat:
                model=self.solver.model()
                try:
                    coords=self.coordinates(model)
                    points=[{"id":k,"x":float(Fraction(v[0])),"y":float(Fraction(v[1])),"fixed":next(p.fixed for p in self.problem.points if p.id==k)} for k,v in coords.items()]
                    self.solver.pop()
                    return {"status":"sat","points":points,"exactCoordinates":coords}
                except ValueError:
                    # Approximation is acceptable for display, never for a certified counterexample.
                    points=[]
                    for k,xy in self.xy.items():
                        vals=[model.eval(v,model_completion=True) for v in xy]
                        def number(v):
                            if z3.is_rational_value(v): return float(Fraction(v.numerator_as_long(),v.denominator_as_long()))
                            return float(v.as_decimal(12).rstrip('?'))
                        points.append({"id":k,"x":number(vals[0]),"y":number(vals[1]),"fixed":next(p.fixed for p in self.problem.points if p.id==k)})
                    self.solver.pop()
                    return {"status":"sat","points":points,"approximateDisplay":True}
            # pop() clears Z3's reason_unknown on this solver. Capture the
            # diagnostic first; internal status words are never UI messages.
            reason=self.solver.reason_unknown() if check==z3.unknown else ''
            self.solver.pop()
            if check==z3.unknown:
                if angle_shape:
                    fallback=self.angle_layout(pinned,fixed_points,pin_tolerance)
                    if fallback['status']=='sat':return fallback
                return {"status":"unknown","message":"本次图形计算未完成，不能据此判断条件矛盾。请稍后重试。","solverReason":reason}
        return {"status":"unsat","message":"当前条件无法同时满足，或拖动位置不符合保留条件"}

    def angle_layout(self,pinned=None,fixed_points=(),pin_tolerance=0,*,follow_placement=False):
        """Solve in a coordinate frame, then move the display back to its frame.

        Translation/rotation and, for non-metric problems, uniform scale preserve
        all relations. Screen coordinates are never promoted to premises.
        """
        import math
        from .angles import display_number
        from .angle_construction import exact_angle_models
        constructed=exact_angle_models(self.problem,follow_placement=follow_placement)
        if follow_placement and (not constructed or not constructed['models']):return None
        if constructed is not None:
            if not constructed['models']:return {'status':'unsat','message':'这些条件不能同时成立，请核对角度和点的位置。'}
            xy={name:[display_number(v) for v in point] for name,point in constructed['models'][0].items()}
            b,c=constructed['seed']
        else:
            system=ConstraintSystem(self.problem)
            status=system.solver.check()
            if status==z3.unsat:return {'status':'unsat','message':'这些条件不能同时成立，请核对角度和点的位置。'}
            if status!=z3.sat:return {'status':'unknown','message':'图形计算超时，请核对条件后重试。'}
            model=system.solver.model()
            xy={name:[display_number(model.eval(v,model_completion=True)) for v in point] for name,point in system.xy.items()}
            b,c=self.problem.nondegenerate.triangles[0][1:] if self.problem.nondegenerate.triangles else [p.id for p in self.problem.points[:2]]
        old={p.id:(p.x,p.y) for p in self.problem.points}
        source=complex(*xy[c])-complex(*xy[b]);target=complex(*old[c])-complex(*old[b])
        ratio=target/source if abs(source)>1e-12 and abs(target)>1e-12 else 1+0j
        metric=any(r.enabled and r.kind=='fixed_length' for r in self.problem.conditions) or self.problem.goal.kind=='minimize'
        if metric:ratio/=abs(ratio)
        offset=complex(*old[b])-ratio*complex(*xy[b])
        points=[]
        for point in self.problem.points:
            value=ratio*complex(*xy[point.id])+offset
            if not all(math.isfinite(v) and abs(v)<=10000 for v in [value.real,value.imag]):return {'status':'unknown','message':'图形坐标超出可显示范围。'}
            points.append({'id':point.id,'x':value.real,'y':value.imag,'fixed':point.fixed})
        # A normalized display fallback may not move a user's drag or anchors.
        # The similarity preserves every original condition; coordinate
        # closeness is used only for this display placement, never for proofs.
        expected=[p for p in self.problem.points if p.id in fixed_points]
        if pinned:expected.append(pinned)
        by_id={p['id']:p for p in points}
        tolerance=pin_tolerance or 1e-10
        if any(math.hypot(by_id[p.id]['x']-p.x,by_id[p.id]['y']-p.y)>tolerance for p in expected):
            return {'status':'unknown','message':'本次未能在保留拖动位置的同时完成图形计算，已保留上一个有效位置。'}
        return {'status':'sat','points':points,'approximateDisplay':True}

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
