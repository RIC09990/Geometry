import test from 'node:test';
import assert from 'node:assert/strict';
import {projectDrawing,validateDrawing} from '../lib/display-constraints';
import {cleanProblem,normalizeDrawingProblem,type Problem,type Point,type Relation} from '../lib/geometry';
import catalogue from '../data/cases.json';
import pressureProblems from './fixtures/competition-geometry.json';
const {default:Nlp}=await import(new URL('../node_modules/jsxgraph/src/math/nlp.js',import.meta.url).href);
const point=(p:Point[],id:string)=>p.find(q=>q.id===id)!;
const distance=(p:Point[],a:string,b:string)=>Math.hypot(point(p,a).x-point(p,b).x,point(p,a).y-point(p,b).y);
const close=(a:number,b:number,tolerance=1e-4)=>assert.ok(Math.abs(a-b)<tolerance,`${a} differs from ${b}`);

test('Complex independent moving-point loci avoid NLP throughout 1200 off-locus pointer moves',t=>{
 const source=pressureProblems.find(entry=>entry.name==='三动点三次反射')!,p=structuredClone(source.problem) as Problem;
 let points=p.points,solves=0;const nlp={FindMinimum:()=>{solves++;throw new Error('This drag has an exact locus')}};
 const elapsed=[];
 for(let i=0;i<1200;i++){
  const id=['P','Q','R'][i%3],previous=point(points,id),start=performance.now();
  const result=projectDrawing(p,points,{...previous,x:previous.x+.015*Math.sin(i/11),y:previous.y+.015*Math.cos(i/13)},nlp,12);
  elapsed.push(performance.now()-start);assert.ok(result.valid);assert.ok(validateDrawing(p,result.points).valid);
  for(const q of points.filter(q=>q.id!==id))assert.deepEqual(point(result.points,q.id),q);
  points=result.points;
 }
 assert.equal(solves,0);elapsed.sort((a,b)=>a-b);
 t.diagnostic(JSON.stringify({pointerMoves:1200,nlpCalls:solves,medianMs:elapsed[600],p95Ms:elapsed[1140],maxMs:elapsed.at(-1)}));
});
function efgh():Problem{return {schemaVersion:1,id:'custom-general',title:'通用约束测试',version:1,
 points:[{id:'E',x:0,y:3,fixed:true},{id:'F',x:-3,y:0,fixed:true},{id:'G',x:3,y:0,fixed:true},{id:'H',x:0,y:0}],
 segments:['EF','EG','FG','EH'].map(s=>({id:s,points:s.split('')})),circles:[],constructions:[],
 conditions:[{id:'side',kind:'equal_length',args:['E','F','E','G'],enabled:true,toggleable:true},{id:'angle',kind:'fixed_angle',args:['E','G','F'],value:45,enabled:true,toggleable:true},{id:'segment',kind:'on_segment',args:['H','F','G'],enabled:true,toggleable:true},{id:'middle',kind:'midpoint',args:['H','F','G'],enabled:true,toggleable:true}],
 goal:{id:'goal',kind:'equal_angle',args:['E','F','H','E','G','H'],enabled:true,toggleable:true},nondegenerate:{distinct:true,triangles:[['E','F','G'],['E','G','H']]}}}
function onSegment(points:Point[],id:string,a:string,b:string){const p=point(points,id),u=point(points,a),v=point(points,b),dx=v.x-u.x,dy=v.y-u.y;close((p.x-u.x)*dy-(p.y-u.y)*dx,0);const t=((p.x-u.x)*dx+(p.y-u.y)*dy)/(dx*dx+dy*dy);assert.ok(t>0&&t<1)}

function linkedSegmentProblem(scale=1):Problem{
 const radius=4*scale,base=radius*(1+Math.sin(Math.PI/3)/Math.sin(4*Math.PI/9));
 return {...efgh(),id:'custom-linked-segment',points:[
  {id:'A',x:base-radius*Math.cos(2*Math.PI/9),y:radius*Math.sin(2*Math.PI/9)},
  {id:'B',x:0,y:0},{id:'C',x:base,y:0},{id:'D',x:radius,y:0},
 ],segments:['AB','AC','BC','AD'].map(id=>({id,points:[...id]})),conditions:[
  {id:'c',kind:'fixed_angle',args:['A','C','B'],value:40,enabled:false,toggleable:true},
  {id:'a',kind:'fixed_angle',args:['C','A','D'],value:60,enabled:false,toggleable:true},
  {id:'equal',kind:'equal_length',args:['B','D','A','C'],enabled:true,toggleable:true},
  {id:'on',kind:'on_segment',args:['D','B','C'],enabled:true,toggleable:true},
 ],goal:{id:'goal',kind:'angle_value',args:['A','B','C'],enabled:true,toggleable:false},
 nondegenerate:{distinct:true,triangles:[['A','B','C']]}};
}

test('D slides on BC and drives A when BD=AC ties the two lengths',t=>{
 let nlpCalls=0;
 const noNlp={FindMinimum:()=>++nlpCalls};
 const times:number[]=[];
 for(const scale of [.01,1,100]){
  const problem=linkedSegmentProblem(scale);let points=problem.points;
  for(let i=1;i<=96;i++){
   const target={id:'D',x:(4+.8*Math.sin(i/10))*scale,y:.16*Math.cos(i/10)*scale};
   const start=performance.now();
   const result=projectDrawing(problem,points,target,noNlp,12);
   times.push(performance.now()-start);
   assert.ok(result.valid,'each displayed frame must be valid');points=result.points;
   close(point(points,'D').x,target.x,.002*scale);
   onSegment(points.map(p=>({...p,x:p.x/scale,y:p.y/scale})),'D','B','C');
   close(distance(points,'B','D'),distance(points,'A','C'),.00003*scale);
   for(const id of ['B','C'])assert.deepEqual(point(points,id),point(problem.points,id));
  }
  assert.ok(Math.abs(point(points,'A').y-point(problem.points,'A').y)>.05*scale);
 }
 assert.equal(nlpCalls,0,'a local linked drag should not require the global optimizer');
 times.sort((a,b)=>a-b);t.diagnostic('288 linked pointer steps, p95 '+times[Math.floor(times.length*.95)].toFixed(3)+' ms');
});

test('The fully specified angle construction can still move in its similarity family',()=>{
 const problem=linkedSegmentProblem();
 problem.conditions=problem.conditions.map(r=>({...r,enabled:true}));
 const d=point(problem.points,'D');
 const result=projectDrawing(problem,problem.points,{...d,x:d.x+.7,y:d.y+.4},Nlp);
 assert.ok(result.valid);
 const moved=point(result.points,'D');
 assert.ok(Math.hypot(moved.x-d.x,moved.y-d.y)>.5);
 assert.deepEqual(point(result.points,'B'),point(problem.points,'B'));
 assert.ok(validateDrawing(problem,result.points).valid);
});

test('A saved square construction can leave a nearly singular endpoint and drag back from either end',()=>{
 const fixed:Point[]=[{id:'A',x:0,y:4},{id:'B',x:0,y:0},{id:'D',x:4,y:4},{id:'E',x:6.4,y:0}];
 const relation=(id:string,kind:string,args:string[],extra:Partial<Relation>={}):Relation=>({id,kind,args,enabled:true,toggleable:true,...extra});
 const problem:Problem={
  ...linkedSegmentProblem(),id:'custom-square-endpoint',
  points:[...fixed,{id:'F',x:5.4,y:1.4},{id:'P',x:4-4e-8,y:0},{id:'C',x:4,y:0}],
  segments:[],conditions:[
   ...fixed.map(p=>relation('fix-'+p.id,'fixed_point',[p.id],{coordinates:[p.x,p.y]})),
   relation('horizontal','parallel',['A','D','B','C']),relation('vertical','parallel',['A','B','D','C']),
   relation('side','on_segment',['P','B','C']),relation('perpendicular','perpendicular',['P','F','A','P']),
   relation('bisector','equal_angle',['D','C','F','F','C','E']),
  ],goal:relation('goal','equal_length',['P','A','P','F']),
 };
 let points=problem.points;
 for(const [target,expected] of [[3.95,3.8],[2.7,2.7],[-1,.2],[1.3,1.3],[4.6,3.8],[3.2,3.2]]){
  const step=projectDrawing(problem,points,{id:'P',x:target,y:.03},Nlp,Infinity,.2);
  assert.ok(step.valid,'the point must be movable even from a saved endpoint');
  points=step.points;
  close(point(points,'P').x,expected,.0001);
  onSegment(points,'P','B','C');
  close(distance(points,'P','A'),distance(points,'P','F'));
  for(const p of fixed)assert.deepEqual(point(points,p.id),p);
 }
});

test('Explicitly fixing A, B and C really does lock D to the line and length intersection',()=>{
 const problem=linkedSegmentProblem();
 for(const id of ['A','B','C']){
  const p=point(problem.points,id);
  problem.conditions.push({id:'fixed-'+id,kind:'fixed_point',args:[id],coordinates:[p.x,p.y],enabled:true,toggleable:true});
 }
 const result=projectDrawing(problem,problem.points,{id:'D',x:5,y:.1},Nlp);
 assert.ok(result.valid);
 assert.deepEqual(result.points,problem.points);
});

test('Dragging the midpoint in the six-term weighted problem drives its circle point',()=>{
 const problem=structuredClone(pressureProblems.find(entry=>entry.name==='六项加权中点联动')!.problem) as Problem;
 const m=point(problem.points,'M'),p=point(problem.points,'P');
 const result=projectDrawing(problem,problem.points,{id:'M',x:m.x+.25,y:m.y+.07},Nlp,12);
 assert.ok(result.valid);
 const moved=point(result.points,'M'),driver=point(result.points,'P'),focus=point(result.points,'A');
 assert.ok(moved.x-m.x>.18&&driver.x-p.x>.36);
 close(2*moved.x,driver.x+focus.x,1e-5);close(2*moved.y,driver.y+focus.y,1e-5);
 close(distance(result.points,'O','P'),distance(result.points,'O','U'),1e-5);
 for(const id of ['O','U','A','B'])assert.deepEqual(point(result.points,id),point(problem.points,id));
 const weightedSum=(points:Point[])=>problem.goal.weights!.reduce((sum,w,i)=>sum+w*distance(points,problem.goal.args[i*2],problem.goal.args[i*2+1]),0);
 assert.ok(Math.abs(weightedSum(result.points)-weightedSum(problem.points))>.01);
});

test('Interior intersections can drive the seven-point angle construction',()=>{
 const problem=structuredClone(pressureProblems.find(entry=>entry.name==='七点多重角度与区域约束')!.problem) as Problem;
 let points=problem.points;
 for(const id of ['D','E','F','G']){
  const before=point(points,id);
  const result=projectDrawing(problem,points,{...before,x:before.x+.13,y:before.y+.07},Nlp,12);
  assert.ok(result.valid,id);
  points=result.points;
  const after=point(points,id);assert.ok(Math.hypot(after.x-before.x,after.y-before.y)>.09,id);
  assert.ok(validateDrawing(problem,points).valid,id);
 }
});

test('Removing both E conditions releases E despite legacy fixed flags',()=>{
 const p=efgh();p.conditions[0].enabled=false;p.conditions[1].enabled=false;
 const result=projectDrawing(p,p.points,{id:'E',x:.6,y:3.2},Nlp);assert.ok(result.valid);
 close(point(result.points,'E').x,.6,.002);close(point(result.points,'E').y,3.2,.002);
 close(point(result.points,'F').x,-3);close(point(result.points,'G').x,3);close(point(result.points,'H').x,0);close(point(result.points,'H').y,0);
 assert.ok(cleanProblem(p).points.every(p=>p.fixed===undefined));
});
test('A retained numeric angle projects E onto its ray instead of locking it',()=>{
 const p=efgh();p.conditions[0].enabled=false;
 const result=projectDrawing(p,p.points,{id:'E',x:.6,y:3.2},Nlp);assert.ok(result.valid);
 const e=point(result.points,'E');assert.ok(Math.hypot(e.x,e.y-3)>.05);close(e.y,3-e.x);close(point(result.points,'G').x,3);
});
test('EH=GH and H on FG remain true together throughout successive E moves',()=>{
 const p=efgh();p.conditions[0].enabled=false;p.conditions[1].enabled=false;p.conditions[3].enabled=false;
 p.conditions.push({id:'new-equality',kind:'equal_length',args:['E','H','G','H'],enabled:true,toggleable:true});
 let points=p.points;
 for(let i=0;i<12;i++){const e=point(points,'E'),result=projectDrawing(p,points,{...e,x:e.x+.04,y:e.y+.015},Nlp);assert.ok(result.valid);points=result.points;onSegment(points,'H','F','G');close(distance(points,'E','H'),distance(points,'G','H'));close(point(points,'F').x,-3);close(point(points,'G').x,3)}
 assert.ok(point(points,'E').x>.4);
});
test('Keeping H a midpoint makes EH=GH constrain E to its circle',()=>{
 const p=efgh();p.conditions[0].enabled=false;p.conditions[1].enabled=false;
 p.conditions.push({id:'new-equality',kind:'equal_length',args:['E','H','G','H'],enabled:true,toggleable:true});
 const result=projectDrawing(p,p.points,{id:'E',x:.7,y:3.1},Nlp);assert.ok(result.valid);
 close(point(result.points,'H').x,0);close(point(result.points,'H').y,0);close(distance(result.points,'E','H'),3);assert.ok(point(result.points,'E').x>.3);
});
test('Changing point names and removing a segment constraint releases the same degrees of freedom',()=>{
 const p=efgh(),names:Record<string,string>={E:'P',F:'Q',G:'R',H:'S'};
 p.points=p.points.map(q=>({...q,id:names[q.id]}));p.segments=p.segments.map(s=>({...s,points:s.points.map(id=>names[id])}));for(const r of [...p.conditions,p.goal])r.args=r.args.map(id=>names[id]);p.nondegenerate.triangles=p.nondegenerate.triangles.map(t=>t.map(id=>names[id]));
 p.conditions=p.conditions.filter(r=>r.id==='segment');
 let result=projectDrawing(p,p.points,{id:'S',x:1,y:.6},Nlp);assert.ok(result.valid);onSegment(result.points,'S','Q','R');
 p.conditions=[];result=projectDrawing(p,result.points,{id:'S',x:1,y:.6},Nlp);assert.ok(result.valid);close(point(result.points,'S').y,.6,.002);
});
test('All five catalogue problems keep their retained geometry when a driver moves',()=>{
 for(const source of catalogue){const p=cleanProblem(source as Problem),q=point(p.points,p.id==='bisector'?'P':p.id==='parallelogram'?'C':'A');
  const result=projectDrawing(p,p.points,{...q,x:q.x+.05,y:q.y+.08},Nlp);assert.ok(result.valid,p.id);assert.ok(result.points.every(q=>Number.isFinite(q.x)&&Number.isFinite(q.y)),p.id);
  if(p.id==='midline'){const d=point(result.points,'D'),a=point(result.points,'A'),b=point(result.points,'B');close(2*d.x,a.x+b.x);close(2*d.y,a.y+b.y)}
  if(p.id==='isosceles'||p.id==='base-angles')close(distance(result.points,'A','B'),distance(result.points,'A','C'));
  if(p.id==='parallelogram'){const [a,b,c,d]=['A','B','C','D'].map(id=>point(result.points,id));close(a.x+c.x,b.x+d.x);close(a.y+c.y,b.y+d.y)}
 }
});
test('The goal never becomes a display constraint and unknown relations are rejected',()=>{
 const p=efgh();p.conditions=[];const target={id:'E',x:1,y:4},first=projectDrawing(p,p.points,target,Nlp);
 p.goal={...p.goal,kind:'fixed_length',args:['E','F'],value:99};const second=projectDrawing(p,p.points,target,Nlp);assert.deepEqual(first.points,second.points);
 p.conditions.push({id:'unknown',kind:'made_up',args:['E','F'],enabled:true,toggleable:true});assert.equal(projectDrawing(p,p.points,target,Nlp).valid,false);
});
test('Arc and distance-ratio loci stay constrained and release when removed',()=>{
 const p=efgh();p.points=[{id:'E',x:0,y:0},{id:'F',x:2,y:0},{id:'G',x:0,y:2},{id:'H',x:Math.SQRT2,y:Math.SQRT2}];p.nondegenerate.triangles=[['E','F','G']];
 p.conditions=[{id:'arc',kind:'on_arc',args:['H','E','F','G'],orientation:'ccw',enabled:true,toggleable:true}];
 let result=projectDrawing(p,p.points,{id:'H',x:1.8,y:1.2},Nlp);assert.ok(result.valid);close(distance(result.points,'H','E'),2);assert.ok(point(result.points,'H').x>0&&point(result.points,'H').y>0);
 p.nondegenerate.distinct=false;
 const inclusive=projectDrawing(p,result.points,{id:'H',x:3,y:-.5},Nlp,Infinity,.2);
 assert.ok(inclusive.valid);close(distance(inclusive.points,'H','F'),0,1e-10);
 p.nondegenerate.distinct=true;
 p.conditions=[];result=projectDrawing(p,result.points,{id:'H',x:1.8,y:1.2},Nlp);assert.ok(result.valid);close(point(result.points,'H').x,1.8,.002);close(point(result.points,'H').y,1.2,.002);
 p.points=[{id:'E',x:-2,y:0},{id:'F',x:2,y:0},{id:'G',x:0,y:2},{id:'H',x:10/3,y:8/3}];
 p.conditions=[{id:'ratio',kind:'length_ratio',args:['H','E','H','F'],value:2,enabled:true,toggleable:true}];
 result=projectDrawing(p,p.points,{id:'H',x:4,y:2.5},Nlp);assert.ok(result.valid);close(distance(result.points,'H','E'),2*distance(result.points,'H','F'));
});

function circleProblem():Problem{return {...efgh(),id:'circle-import',points:[{id:'O',x:0,y:0},{id:'Q',x:1,y:0},{id:'A',x:-1,y:2},{id:'B',x:2,y:0},{id:'P',x:0,y:0}],segments:[],circles:[],conditions:[
 {id:'circle',kind:'on_circle',args:['P','O','Q'],enabled:true,toggleable:true},
 {id:'a',kind:'free_text',args:[],description:'A(-1,2)',enabled:true,toggleable:true},
 {id:'b',kind:'free_text',args:[],description:'B(2,0)',enabled:true,toggleable:true},
],goal:{id:'goal',kind:'minimize',args:['P','A','P','B'],weights:[1,.5],enabled:true,toggleable:false},nondegenerate:{distinct:true,triangles:[]}}}

test('Imported circle repairs a point at its centre without moving the circle or fixed foci',()=>{
 const p=circleProblem(),result=projectDrawing(p,p.points,undefined,Nlp);
 assert.equal(validateDrawing(p,p.points).valid,false);assert.equal(result.valid,true);
 close(distance(result.points,'P','O'),1,1e-10);
 for(const id of ['O','Q','A','B'])assert.deepEqual(point(result.points,id),point(p.points,id));
 for(const id of ['A','B']){const moved=projectDrawing(p,result.points,{id,x:100,y:100},Nlp);assert.equal(moved.valid,true);assert.deepEqual(point(moved.points,id),point(p.points,id))}
});

test('A complete circle drag remains on its locus and retains reference coordinates',()=>{
 const p=circleProblem();let points=projectDrawing(p,p.points,undefined,Nlp).points;
 for(let i=0;i<360;i++){
  const theta=(i+.2)*Math.PI/180,result=projectDrawing(p,points,{id:'P',x:1.7*Math.cos(theta),y:1.7*Math.sin(theta)},Nlp);
  assert.ok(result.valid,`frame ${i}`);assert.ok(validateDrawing(p,result.points).valid);points=result.points;
  close(distance(points,'P','O'),1,1e-10);for(const id of ['O','Q','A','B'])assert.deepEqual(point(points,id),point(p.points,id));
 }
 // Passing the pointer through the centre keeps the last defined direction.
 const result=projectDrawing(p,points,{id:'P',x:0,y:0},Nlp);assert.ok(result.valid);close(distance(result.points,'P','O'),1,1e-10);
});

test('Apollonius loci survive a full revolution for ratios above and below one',()=>{
 for(const ratio of [.2,.5,2,5]){
  const p=circleProblem();p.points=p.points.filter(q=>['A','B','P'].includes(q.id));p.conditions=[{id:'ratio',kind:'length_ratio',args:['P','A','P','B'],value:ratio,enabled:true,toggleable:true}];
  const a=point(p.points,'A'),b=point(p.points,'B'),cx=(a.x-ratio*ratio*b.x)/(1-ratio*ratio),cy=(a.y-ratio*ratio*b.y)/(1-ratio*ratio),radius=ratio*Math.hypot(a.x-b.x,a.y-b.y)/Math.abs(1-ratio*ratio);
  let points=p.points;
  for(let i=0;i<72;i++){const t=i*Math.PI/36,result=projectDrawing(p,points,{id:'P',x:cx+1.3*radius*Math.cos(t),y:cy+1.3*radius*Math.sin(t)},Nlp);assert.ok(result.valid,`ratio ${ratio}, frame ${i}`);points=result.points;close(distance(points,'P','A'),ratio*distance(points,'P','B'),1e-9);assert.deepEqual(point(points,'A'),a);assert.deepEqual(point(points,'B'),b)}
 }
});

test('A ratio of one has a perpendicular-bisector locus',()=>{
 const p=circleProblem();p.conditions=[{id:'ratio',kind:'length_ratio',args:['P','A','P','B'],value:1,enabled:true,toggleable:true}];
 const result=projectDrawing(p,p.points,{id:'P',x:8,y:7},Nlp);assert.ok(result.valid);close(distance(result.points,'P','A'),distance(result.points,'P','B'),1e-10);
});

test('Unknown text and malformed conditions never claim a valid drawing',()=>{
 const p=circleProblem();p.conditions.push({id:'text',kind:'free_text',args:[],description:'P 位于另一个未编码的轨迹上',enabled:true,toggleable:true});
 assert.deepEqual(validateDrawing(p,p.points).unsupported,['text']);assert.equal(projectDrawing(p,p.points,undefined,Nlp).valid,false);
 p.conditions=p.conditions.filter(r=>r.id!=='text');p.conditions[0].args[1]='MISSING';assert.equal(validateDrawing(p,p.points).valid,false);assert.doesNotThrow(()=>projectDrawing(p,p.points,undefined,Nlp));
 assert.equal(projectDrawing(p,p.points,{id:'P',x:NaN,y:0},Nlp).valid,false);
});

test('Independent validation rejects degeneracy even when equality residuals vanish',()=>{
 const p=efgh();p.nondegenerate={distinct:false,triangles:[]};p.points=p.points.map(q=>({...q,x:0,y:0}));
 const relations=[
  {kind:'on_circle',args:['E','F','G']},
  {kind:'on_segment',args:['E','F','G']},
  {kind:'perpendicular',args:['E','F','G','H']},
  {kind:'parallel',args:['E','F','G','H']},
  {kind:'fixed_angle',args:['E','F','G'],value:90},
  {kind:'length_ratio',args:['E','F','G','H'],value:2},
  {kind:'similar_triangles',args:['E','F','G','F','G','H']},
 ];
 for(const r of relations){p.conditions=[{...r,id:'domain',enabled:true,toggleable:true}];assert.equal(validateDrawing(p,p.points).valid,false,r.kind);assert.equal(projectDrawing(p,p.points,undefined,{FindMinimum:()=>0}).valid,false,r.kind)}
 p.conditions=[];p.nondegenerate={distinct:true,triangles:[]};assert.equal(validateDrawing(p,p.points).valid,false);
 p.nondegenerate={distinct:false,triangles:[['E','F','G']]};assert.equal(validateDrawing(p,p.points).valid,false);
});

test('Open segment endpoints and inconsistent constraints are rejected',()=>{
 const p=efgh();p.nondegenerate={distinct:false,triangles:[]};p.conditions=[{id:'on',kind:'on_segment',args:['H','F','G'],enabled:true,toggleable:true}];
 for(const endpoint of ['F','G']){const q=point(p.points,endpoint),points=p.points.map(v=>v.id==='H'?{...v,x:q.x,y:q.y}:v);assert.equal(validateDrawing(p,points).valid,false)}
 p.conditions=[1,2].map(value=>({id:'fixed-'+value,kind:'fixed_length',args:['F','G'],value,enabled:true,toggleable:true}));
 const result=projectDrawing(p,p.points,undefined,Nlp);assert.equal(result.valid,false);assert.deepEqual(result.points,p.points);
});

test('Explicit coordinate constraints repair stale imported positions',()=>{
 const p=circleProblem();p.points=projectDrawing(p,p.points,undefined,Nlp).points;p.points= p.points.map(q=>q.id==='A'?{...q,x:12,y:12}:q);
 const result=projectDrawing(p,p.points,undefined,Nlp);assert.ok(result.valid);assert.deepEqual(point(result.points,'A'),{id:'A',x:-1,y:2});
 const invalid=result.points.map(q=>q.id==='A'?{...q,x:-.9}:q);assert.equal(validateDrawing(p,invalid).valid,false);
});

test('Coordinate sentence normalization is complete, bounded and exact in its supported grammar',()=>{
 const p=circleProblem();
 for(const description of ['A(-1,2)','点A（−1，2）','定点 A 的坐标为 (-1, 2)。','已知定点A坐标是(-1e0, 2e+0)','A = (-1,2)','$A(-1,2)$','\\(A\\left(-1,2\\right)\\)']){
  p.conditions=[{id:'coordinate',kind:'free_text',args:[],description,enabled:true,toggleable:true}];
  assert.deepEqual(normalizeDrawingProblem(p).conditions[0].coordinates,[-1,2],description);
 }
 for(const description of ['A(-1,2)，且P在AB上','A(1/3,2)','A(1/0,2)','A(1e100,2)','A(10001,2)','Z(-1,2)','线段A(-1,2)']){
  p.conditions=[{id:'coordinate',kind:'free_text',args:[],description,enabled:true,toggleable:true}];assert.equal(normalizeDrawingProblem(p).conditions[0].kind,'free_text',description);
 }
});

test('Nearly straight and nearly zero angles are validated by angle, not an insensitive cosine',()=>{
 const p=circleProblem();p.nondegenerate={distinct:false,triangles:[]};p.points=[{id:'A',x:1,y:0},{id:'O',x:0,y:0},{id:'P',x:Math.cos(.1*Math.PI/180),y:Math.sin(.1*Math.PI/180)}];
 p.goal={id:'goal',kind:'angle_value',args:['A','O','P'],enabled:true,toggleable:false};
 p.conditions=[{id:'tiny-angle',kind:'fixed_angle',args:['A','O','P'],value:.001,enabled:true,toggleable:true}];assert.equal(validateDrawing(p,p.points).valid,false);
 p.points[2]={id:'P',x:Math.cos(.001*Math.PI/180),y:Math.sin(.001*Math.PI/180)};assert.equal(validateDrawing(p,p.points).valid,true);
});

test('Coordinate bounds and zero lengths use the same domain as the backend',()=>{
 const p=efgh();p.nondegenerate={distinct:false,triangles:[]};p.conditions=[{id:'zero',kind:'fixed_length',args:['F','H'],value:0,enabled:true,toggleable:true}];
 const result=projectDrawing(p,p.points,undefined,Nlp);assert.ok(result.valid);assert.equal(distance(result.points,'F','H'),0);
 assert.equal(validateDrawing(p,result.points.map(q=>q.id==='E'?{...q,x:10001}:q)).valid,false);
 p.conditions=[{id:'bounds',kind:'fixed_point',args:['E'],coordinates:[10001,0],enabled:true,toggleable:true}];assert.equal(projectDrawing(p,p.points,undefined,Nlp).valid,false);
 assert.equal(projectDrawing(efgh(),efgh().points,{id:'E',x:Infinity,y:0},Nlp).valid,false);
});

test('Invalid render-object references fail before drawing without promoting the goal to a premise',()=>{
 const valid=efgh();valid.conditions=[];
 const cases:((p:Problem)=>void)[]=[
  p=>{p.segments=[{id:'bad-edge',points:['E','MISSING']}]},
  p=>{p.segments=[{id:'short-edge',points:['E']}]},
  p=>{p.circles=[{id:'missing-center',center:'MISSING',through:'E'}]},
  p=>{p.circles=[{id:'missing-through',center:'E',through:'MISSING'}]},
  p=>{p.circles=[{id:'missing-end',center:'E',through:'F',end:'MISSING'}]},
  p=>{p.circles=[{id:'same-point',center:'E',through:'E'}]},
  p=>{p.goal={...p.goal,kind:'on_circle',args:['E','MISSING','F']}},
  p=>{p.goal={...p.goal,kind:'on_circle',args:['E','F']}},
  p=>{p.goal={...p.goal,kind:'minimize',args:['E','F','G']}},
 ];
 for(const mutate of cases){const p=structuredClone(valid);mutate(p);assert.equal(validateDrawing(p,p.points).valid,false);assert.doesNotThrow(()=>projectDrawing(p,p.points,undefined,Nlp));assert.equal(projectDrawing(p,p.points,undefined,Nlp).valid,false)}
 valid.goal={...valid.goal,kind:'on_circle',args:['E','F','G']};assert.equal(validateDrawing(valid,valid.points).valid,true);
 const result=projectDrawing(valid,valid.points,{id:'E',x:1,y:4},Nlp);assert.ok(result.valid);close(point(result.points,'E').x,1);close(point(result.points,'E').y,4);
});

test('Every supported relation either preserves its equation or rejects the drag across scales and point orderings',t=>{
 const fixtures:Partial<Relation>[]=[
  {kind:'fixed_point',args:['A'],coordinates:[2,0]},
  {kind:'fixed_length',args:['O','A'],value:2},
  {kind:'equal_length',args:['O','A','O','B']},
  {kind:'length_ratio',args:['O','H','O','A'],value:2},
  {kind:'midpoint',args:['D','O','A']},
  {kind:'perpendicular',args:['O','A','O','B']},
  {kind:'parallel',args:['O','A','B','C']},
  {kind:'collinear',args:['O','D','A']},
  {kind:'on_segment',args:['D','O','A']},
  {kind:'on_circle',args:['P','O','A']},
  {kind:'on_arc',args:['P','O','A','B'],orientation:'ccw'},
  {kind:'fixed_angle',args:['A','O','B'],value:90},
  {kind:'equal_angle',args:['A','O','B','H','O','I']},
  {kind:'similar_triangles',args:['O','A','B','O','H','I']},
 ];
 const original:Point[]=[{id:'O',x:0,y:0},{id:'A',x:2,y:0},{id:'B',x:0,y:2},{id:'C',x:2,y:2},{id:'D',x:1,y:0},{id:'P',x:Math.SQRT2,y:Math.SQRT2},{id:'H',x:4,y:0},{id:'I',x:0,y:4}];
 let seed=74891,accepted=0,rejected=0;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296};
 for(const fixture of fixtures)for(const scale of [.01,1,100]){
  const p=circleProblem();p.nondegenerate={distinct:true,triangles:[]};p.points=original.map(q=>({...q,x:q.x*scale+scale*3,y:q.y*scale-scale*2}));
  for(let i=p.points.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[p.points[i],p.points[j]]=[p.points[j],p.points[i]]}
  const relation={id:'stress',enabled:true,toggleable:true,...fixture} as Relation;
  if(relation.kind==='fixed_length')relation.value=2*scale;
  if(relation.kind==='fixed_point')relation.coordinates=[5*scale,-2*scale];
  p.conditions=[relation];assert.ok(validateDrawing(p,p.points).valid,`${fixture.kind} initial ${scale}`);
  for(const q of p.points){
   const target={...q,x:q.x+(random()-.5)*.4*scale,y:q.y+(random()-.5)*.4*scale};
   const result=projectDrawing(p,p.points,target,Nlp);
   if(!result.valid){rejected++;assert.deepEqual(result.points,p.points);continue}
   accepted++;assert.ok(validateDrawing(p,result.points).valid,`${fixture.kind} ${q.id} ${scale}`);
   // Rescale to check the actual relation in an independent coordinate frame.
   const local=result.points.map(v=>({...v,x:(v.x-3*scale)/scale,y:(v.y+2*scale)/scale})),a=relation.args;
   const v=(a:string,b:string)=>[point(local,b).x-point(local,a).x,point(local,b).y-point(local,a).y];
   const cross=(u:number[],w:number[])=>u[0]*w[1]-u[1]*w[0],dot=(u:number[],w:number[])=>u[0]*w[0]+u[1]*w[1];
   const angle=(a:string,b:string,c:string)=>Math.atan2(Math.abs(cross(v(b,a),v(b,c))),dot(v(b,a),v(b,c)));
   switch(relation.kind){
    case 'fixed_point':close(point(local,'A').x,2,1e-5);close(point(local,'A').y,0,1e-5);break;
    case 'fixed_length':close(distance(local,...a as [string,string]),2,1e-5);break;
    case 'equal_length':case 'length_ratio':close(distance(local,a[0],a[1]),(relation.value??1)*distance(local,a[2],a[3]),1e-5);break;
    case 'midpoint':{const u=point(local,a[0]),w=point(local,a[1]),z=point(local,a[2]);close(u.x,(w.x+z.x)/2,1e-5);close(u.y,(w.y+z.y)/2,1e-5);break}
    case 'perpendicular':close(dot(v(a[0],a[1]),v(a[2],a[3])),0,1e-5);break;
    case 'parallel':close(cross(v(a[0],a[1]),v(a[2],a[3])),0,1e-5);break;
    case 'collinear':close(cross(v(a[1],a[0]),v(a[1],a[2])),0,1e-5);break;
    case 'on_segment':onSegment(local,a[0],a[1],a[2]);break;
    case 'on_circle':case 'on_arc':close(distance(local,a[0],a[1]),distance(local,a[2],a[1]),1e-5);if(relation.kind==='on_arc'){assert.ok(cross(v(a[1],a[2]),v(a[1],a[0]))>=-1e-5);assert.ok(cross(v(a[1],a[0]),v(a[1],a[3]))>=-1e-5)}break;
    case 'fixed_angle':close(angle(a[0],a[1],a[2]),Math.PI/2,1e-5);break;
    case 'equal_angle':close(angle(a[0],a[1],a[2]),angle(a[3],a[4],a[5]),1e-5);break;
    case 'similar_triangles':{const ratio=distance(local,a[0],a[1])/distance(local,a[3],a[4]);close(distance(local,a[0],a[2])/distance(local,a[3],a[5]),ratio,1e-5);close(distance(local,a[1],a[2])/distance(local,a[4],a[5]),ratio,1e-5);break}
   }
  }
 }
 assert.ok(accepted>250);t.diagnostic(`${accepted} accepted and independently checked; ${rejected} safely rejected across 336 drags`);
});
