from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

KINDS = {"equal_length": 4, "midpoint": 3, "perpendicular": 4, "parallel": 4,
         "collinear": 3, "on_segment": 3, "equal_angle": 6, "on_circle": 3,
         "fixed_length": 2, "fixed_point": 1, "on_arc": 4, "minimize": -1,
         "length_ratio": 4, "similar_triangles": 6, "fixed_angle": 3, "angle_value": 3, "free_text": -2,
         "inside_triangle":4,"inside_circle":3,"outside_circle":3,"same_side":4,"opposite_side":4}

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Point(StrictModel):
    id: str = Field(pattern=r"^[A-Z][0-9]?$", max_length=2)
    x: float = Field(ge=-10000, le=10000, allow_inf_nan=False)
    y: float = Field(ge=-10000, le=10000, allow_inf_nan=False)
    fixed: bool = False

class Segment(StrictModel):
    id: str = Field(max_length=64)
    points: list[str] = Field(min_length=2, max_length=2)

class Circle(StrictModel):
    id: str = Field(max_length=64)
    center: str
    through: str
    end: str | None = None
    orientation: Literal['ccw','cw'] = 'ccw'

class Relation(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$", max_length=60)
    kind: str = Field(max_length=30)
    args: list[str] = Field(default_factory=list)
    description: str = Field(default='',max_length=20000)
    enabled: bool = True
    toggleable: bool = True
    value: float | None = Field(default=None,ge=0,le=100000,allow_inf_nan=False)
    weights: list[float] = Field(default_factory=list,max_length=6)
    orientation: Literal['ccw','cw'] = 'ccw'

    coordinates: list[float] = Field(default_factory=list,max_length=2)

    @model_validator(mode='before')
    @classmethod
    def legacy_coordinates(cls, value):
        # Apply to saved problems as well as new AI imports, at every API boundary.
        if isinstance(value,dict) and value.get('kind')=='free_text':
            from .coordinate_conditions import coordinate_statement
            parsed=coordinate_statement(value.get('description',''))
            if parsed:
                name,coordinates=parsed
                if not value.get('args') or value['args']==[name]:
                    return {**value,'kind':'fixed_point','args':[name],'coordinates':coordinates}
            from .spatial_conditions import spatial_statement
            spatial=spatial_statement(value.get('description',''))
            if spatial and (not value.get('args') or set(value['args'])==set(spatial['args'])):
                return {**value,**spatial}
        return value

    @model_validator(mode='after')
    def parameters(self):
        import math
        if self.kind=='fixed_point':
            if len(self.coordinates)!=2 or any(not math.isfinite(v) or abs(v)>10000 for v in self.coordinates):
                raise ValueError('固定点坐标需要两个有限数，范围为 -10000 到 10000')
        elif self.coordinates:raise ValueError('坐标值只能用于固定点条件')
        if self.kind=='free_text' and not self.description.strip():raise ValueError('请填写条件或目标的完整文字')
        if self.kind=='fixed_angle':
            from .angles import supported_angle
            if self.value is None:raise ValueError('角度数值尚未填写')
            supported_angle(self.value)
        if self.kind=='fixed_length' and self.value is None:raise ValueError('线段数值长度尚未填写')
        if self.kind=='length_ratio' and (self.value is None or self.value<=0):raise ValueError('线段长度比必须填写有限正数')
        if self.kind=='minimize':
            if len(self.args)%2 or len(self.weights)!=len(self.args)//2:raise ValueError('最小值目标需要为每条线段填写一个权重')
            if any(not math.isfinite(w) or w<=0 for w in self.weights):raise ValueError('线段权重必须为有限正数')
        return self

class Nondegenerate(StrictModel):
    distinct: bool = True
    triangles: list[list[str]] = Field(default_factory=list)

class Problem(StrictModel):
    schemaVersion: Literal[1] = 1
    id: str = Field(max_length=100)
    title: str = Field(min_length=1, max_length=80)
    version: int = Field(ge=1, le=1000000)
    points: list[Point] = Field(min_length=3)
    segments: list[Segment] = Field(default_factory=list)
    circles: list[Circle] = Field(default_factory=list)
    conditions: list[Relation]
    goal: Relation
    nondegenerate: Nondegenerate
    sourceText: str = Field(default='',max_length=30000)
    constructions: list = Field(default_factory=list, max_length=0)

    @model_validator(mode='before')
    @classmethod
    def legacy_spatial_notices(cls,value):
        if not isinstance(value,dict) or not isinstance(value.get('conditions'),list):return value
        from .spatial_conditions import spatial_statement,NOTICE
        conditions=[];warnings=[]
        for original in value['conditions']:
            if not isinstance(original,dict):conditions.append(original);warnings.append(False);continue
            spatial=spatial_statement(original.get('description','')) if original.get('kind') in ('free_text','inside_triangle') else None
            conditions.append({**original,**spatial} if spatial else original)
            warnings.append(bool(spatial and NOTICE.fullmatch(original.get('description','').strip())))
        kept=[r for i,r in enumerate(conditions) if not warnings[i] or not any(j!=i and not warnings[j] and isinstance(other,dict) and other.get('kind')==r.get('kind') and other.get('args')==r.get('args') for j,other in enumerate(conditions))]
        return {**value,'conditions':kept}

    @model_validator(mode="after")
    def references(self):
        ids = {p.id for p in self.points}
        if len(ids) != len(self.points):
            raise ValueError("点名不能重复")
        rel_ids = [r.id for r in self.conditions]
        if any(i=='domain' or i.startswith(('nc-','t-')) for i in [*rel_ids,self.goal.id]):
            raise ValueError('条件和目标编号使用了证明节点的保留命名空间')
        if len(set(rel_ids)) != len(rel_ids) or self.goal.id in rel_ids:
            raise ValueError("条件和目标的编号必须唯一")
        for r in [*self.conditions, self.goal]:
            if r.kind not in KINDS:
                raise ValueError(f"暂不支持关系：{r.kind}；未忽略该关系")
            if (r.kind not in ('minimize','free_text') and len(r.args) != KINDS[r.kind]) or any(a not in ids for a in r.args):
                raise ValueError(f"关系 {r.id} 的对象数量或点名不正确")
            if r.kind=='minimize' and r is not self.goal:raise ValueError('最小值是求解目标，不能当作已知条件')
            if r.kind=='angle_value' and r is not self.goal:raise ValueError('求角度是求解目标，不能当作已知条件')
            if r.kind in ('fixed_angle','angle_value') and len(set(r.args))!=3:raise ValueError('一个角需要三个不同的点，第二个点是顶点')
            if r.kind=='inside_triangle' and len(set(r.args))!=4:raise ValueError('三角形内点必须不同于三个顶点，三个顶点也必须互异')
            if r.kind in ('inside_circle','outside_circle') and r.args[1]==r.args[2]:raise ValueError('圆心和确定半径的点必须不同')
            if r.kind in ('same_side','opposite_side') and r.args[2]==r.args[3]:raise ValueError('确定直线的两个点必须不同')
        for s in self.segments:
            if any(p not in ids for p in s.points) or s.points[0] == s.points[1]:
                raise ValueError("线段端点不正确")
        for c in self.circles:
            if c.center not in ids or c.through not in ids or c.center == c.through:
                raise ValueError("圆的圆心和过点必须存在且不同")
            if c.end is not None and (c.end not in ids or c.end in [c.center,c.through]):raise ValueError('圆弧终点必须是不同的已有点')
        for t in self.nondegenerate.triangles:
            if len(t) != 3 or len(set(t)) != 3 or any(p not in ids for p in t):
                raise ValueError("非退化三角形必须由三个不同的已有点组成")
        return self

class PreviousNode(BaseModel):
    model_config = ConfigDict(extra='ignore')
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]+$',min_length=1,max_length=100)
    statement: str = Field(max_length=2000)
    premises: list[str] = Field(default_factory=list,max_length=50)
    rule: str = Field(default='',max_length=1000)

class PreviousProof(BaseModel):
    model_config = ConfigDict(extra='ignore')
    id: str = Field(min_length=1,max_length=100)
    title: str = Field(max_length=160)
    assumptionIds: list[str] = Field(max_length=20)
    steps: list[PreviousNode] = Field(max_length=200)
    assumptionNodes: list[PreviousNode] = Field(default_factory=list,max_length=200)

    @model_validator(mode='after')
    def unique_nodes(self):
        ids=[n.id for n in self.steps+self.assumptionNodes]
        if len(set(ids))!=len(ids):raise ValueError('证明节点编号不能重复')
        if 'domain' in ids or set(ids)&set(self.assumptionIds):raise ValueError('推理节点和条件编号不能冲突')
        return self

class AnalyzeRequest(StrictModel):
    problem: Problem
    previous: list[PreviousProof] = Field(default_factory=list, max_length=8)

class LayoutRequest(StrictModel):
    problem: Problem
    ignoreUnencoded:bool=False
    pinned: Point | None = None
    fixedPoints: list[str] = Field(default_factory=list)
    pinTolerance:float=Field(default=0,ge=0,le=.001)

class StepRequest(StrictModel):
    problem: Problem
    statement: Relation
    premises: list[str] = Field(default_factory=list, max_length=20)
    proofBody: str = Field(default='', max_length=3000)
    reason: Literal['automatic','given','reflexivity','equality_symmetry','length_symmetry','midpoint','line_symmetry','custom'] = 'automatic'

