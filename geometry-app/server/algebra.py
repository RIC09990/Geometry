"""Exact independent SymPy verification of a Z3 witness, never sampling."""
import itertools
import sympy as s

def vector(coords, a, b):
    return s.Matrix(coords[b]) - s.Matrix(coords[a])

def length2(coords, a, b):
    v = vector(coords, a, b)
    return s.expand(v.dot(v))

def cross(a, b):
    return s.expand(a[0]*b[1]-a[1]*b[0])

def holds(coords, r):
    a=r.args
    k=r.kind
    if k == "equal_length":
        return s.simplify(length2(coords,*a[:2])-length2(coords,*a[2:])) == 0
    if k=='fixed_length':return s.simplify(length2(coords,*a)-s.Rational(str(r.value))**2)==0
    if k=='fixed_point':return all(s.simplify(coords[a[0]][i]-s.Rational(str(value)))==0 for i,value in enumerate(r.coordinates))
    if k=='inside_triangle':
        point,u,v,w=a
        sides=[s.simplify(cross(vector(coords,start,end),vector(coords,start,point))) for start,end in [(u,v),(v,w),(w,u)]]
        return all(side>0 for side in sides) or all(side<0 for side in sides)
    if k in ('inside_circle','outside_circle'):
        distance,radius=length2(coords,a[0],a[1]),length2(coords,a[2],a[1])
        return bool(radius>0 and (distance<radius if k=='inside_circle' else distance>radius))
    if k in ('same_side','opposite_side'):
        line=vector(coords,a[2],a[3]);product=s.simplify(cross(line,vector(coords,a[2],a[0]))*cross(line,vector(coords,a[2],a[1])))
        return bool(line.dot(line)>0 and (product>0 if k=='same_side' else product<0))
    if k=='fixed_angle':
        u,v=vector(coords,a[1],a[0]),vector(coords,a[1],a[2])
        n=s.expand(u.dot(u)*v.dot(v));p=s.expand(u.dot(v))
        cosine=s.cos(s.pi*s.Rational(str(r.value))/180)
        sign=p>0 if r.value<90 else p<0 if r.value>90 else p==0
        return bool(n>0 and sign and s.simplify(p*p-cosine*cosine*n)==0)
    if k=='length_ratio':
        numerator,denominator=length2(coords,*a[:2]),length2(coords,*a[2:])
        return bool(denominator>0 and s.simplify(numerator-s.Rational(str(r.value))**2*denominator)==0)
    if k=='similar_triangles':
        p,q,r0,u,v,w=a
        first=[length2(coords,p,q),length2(coords,p,r0),length2(coords,q,r0)]
        second=[length2(coords,u,v),length2(coords,u,w),length2(coords,v,w)]
        return bool(cross(vector(coords,p,q),vector(coords,p,r0))!=0 and
                    cross(vector(coords,u,v),vector(coords,u,w))!=0 and
                    s.simplify(first[0]*second[1]-first[1]*second[0])==0 and
                    s.simplify(first[0]*second[2]-first[2]*second[0])==0)
    if k == "midpoint":
        return all(s.simplify(2*coords[a[0]][i]-coords[a[1]][i]-coords[a[2]][i]) == 0 for i in [0,1])
    if k == "perpendicular":
        u,v=vector(coords,*a[:2]),vector(coords,*a[2:])
        return bool(u.dot(u)>0 and v.dot(v)>0 and s.simplify(u.dot(v))==0)
    if k == "parallel":
        u,v=vector(coords,*a[:2]),vector(coords,*a[2:])
        return bool(u.dot(u)>0 and v.dot(v)>0 and s.simplify(cross(u,v))==0)
    if k in ["collinear","on_segment"]:
        u,v=vector(coords,a[1],a[0]),vector(coords,a[1],a[2])
        col=s.simplify(cross(u,v))==0
        return col if k=="collinear" else bool(col and u.dot(v)>0 and u.dot(v)<v.dot(v))
    if k == "on_circle":
        return bool(length2(coords,a[2],a[1])>0 and s.simplify(length2(coords,a[0],a[1])-length2(coords,a[2],a[1])) == 0)
    if k=='on_arc':
        point,center,start,end=a
        if r.orientation=='cw':start,end=end,start
        u,v,w=vector(coords,center,start),vector(coords,center,end),vector(coords,center,point)
        return bool(length2(coords,center,start)>0 and length2(coords,start,end)>0 and
            s.simplify(length2(coords,center,point)-length2(coords,center,start))==0 and
            s.simplify(length2(coords,center,end)-length2(coords,center,start))==0 and
            cross(u,v)>=0 and cross(u,w)>=0 and cross(w,v)>=0)
    if k == "equal_angle":
        u,v,w,t=vector(coords,a[1],a[0]),vector(coords,a[1],a[2]),vector(coords,a[4],a[3]),vector(coords,a[4],a[5])
        n,m=s.expand(u.dot(u)*v.dot(v)),s.expand(w.dot(w)*t.dot(t))
        p,q=s.expand(u.dot(v)),s.expand(w.dot(t))
        return bool(n>0 and m>0 and s.simplify(p*p*m-q*q*n)==0 and p*q>=0)
    raise ValueError(f"Unsupported relation {k}")

def verify_witness(problem, coordinates):
    coords={k:tuple(s.Rational(v) for v in val) for k,val in coordinates.items()}
    checks=[]
    for r in problem.conditions:
        if r.enabled: checks.append({"id":r.id,"passed":bool(holds(coords,r))})
    if problem.nondegenerate.distinct:
        checks.append({"id":"distinct","passed":all(length2(coords,a,b)>0 for a,b in itertools.combinations(coords,2))})
    for t in problem.nondegenerate.triangles:
        checks.append({"id":"noncollinear-"+"".join(t),"passed":cross(vector(coords,t[0],t[1]),vector(coords,t[0],t[2]))!=0})
    checks.append({"id":"goal_is_false","passed":not holds(coords,problem.goal)})
    return {"verified":all(bool(c["passed"]) for c in checks),"checks":checks,"engine":"SymPy","exact":True}

