import test from 'node:test';
import assert from 'node:assert/strict';
import {validateDrawing,projectDrawing} from '../lib/display-constraints';
import {normalizeDrawingProblem,type Problem} from '../lib/geometry';
import {spatialStatement} from '../lib/spatial-conditions';
const {default:Nlp}=await import(new URL('../node_modules/jsxgraph/src/math/nlp.js',import.meta.url).href);

const problem:Problem={schemaVersion:1,id:'spatial',title:'空间约束',version:1,
 points:[{id:'A',x:4,y:0},{id:'B',x:0,y:0},{id:'C',x:0,y:4},{id:'O',x:0,y:0},{id:'P',x:1,y:1},{id:'Q',x:1,y:2}],
 segments:[],circles:[],conditions:[],goal:{id:'goal',kind:'equal_length',args:['A','B','B','A'],enabled:true,toggleable:true},nondegenerate:{distinct:false,triangles:[]},constructions:[]};

test('Only complete interior statements are upgraded, including old explanatory notices',()=>{
 for(const source of ['D在△ABC内部','点 D 位于三角形 A B C 的内部。','“D在△ABC内部”无法用当前已定义的几何关系直接精确表达，已用 free_text 条件保留。'])assert.deepEqual(spatialStatement(source),{kind:'inside_triangle',args:['D','A','B','C']});
 for(const source of ['D在△ABC内部，且AD=BD','D在△ABC内部或边上','D在△ABC内部？'])assert.equal(spatialStatement(source),undefined);
});
test('Legacy explanatory duplicates cannot silently keep a disabled interior premise active',()=>{
 const r={id:'inside',kind:'free_text',args:[],description:'P在△ABC内部',enabled:false,toggleable:true};
 const p={...problem,conditions:[r,{...r,id:'warning',enabled:true,description:'“P在△ABC内部”无法用当前已定义的几何关系直接精确表达，已用 free_text 条件保留。'}]};
 const restored=normalizeDrawingProblem(p);assert.equal(restored.conditions.length,1);assert.equal(restored.conditions[0].enabled,false);assert.equal(restored.conditions[0].kind,'inside_triangle');
});
test('Spatial predicates keep strict boundaries and agree under reversal of triangle orientation',()=>{
 const scenarios=[{kind:'inside_triangle',args:['P','A','B','C'],good:[1,1],bad:[4,4],edge:[2,2]},
 {kind:'inside_circle',args:['P','O','A'],good:[1,1],bad:[5,0],edge:[4,0]},
 {kind:'outside_circle',args:['P','O','A'],good:[5,0],bad:[1,1],edge:[4,0]},
 {kind:'same_side',args:['P','Q','A','B'],good:[1,1],bad:[1,-1],edge:[1,0]},
 {kind:'opposite_side',args:['P','Q','A','B'],good:[1,-1],bad:[1,1],edge:[1,0]}];
 for(const s of scenarios){const p={...problem,conditions:[{id:'spatial',kind:s.kind,args:s.args,enabled:true,toggleable:true}]};
  for(const [position,expected] of [[s.good,true],[s.bad,false],[s.edge,false]] as const){const points=p.points.map(q=>q.id==='P'?{...q,x:position[0],y:position[1]}:q);assert.equal(validateDrawing(p,points).valid,expected,s.kind)}
  if(s.kind==='inside_triangle'){p.conditions[0].args=['P','C','B','A'];assert.equal(validateDrawing(p,p.points).valid,true)}
 }
});
test('A dragged interior point is projected within all retained relations or rejected without corrupting the frame',()=>{
 const p={...problem,conditions:[{id:'inside',kind:'inside_triangle',args:['P','A','B','C'],enabled:true,toggleable:true}]};
 for(const target of [{id:'P',x:8,y:8},{id:'P',x:1.2,y:1.6}]){const result=projectDrawing(p,p.points,target,Nlp);if(result.valid)assert.equal(validateDrawing(p,result.points).valid,true);else assert.deepEqual(result.points,p.points)}
});
