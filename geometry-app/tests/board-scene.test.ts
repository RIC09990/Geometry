import test from 'node:test';
import assert from 'node:assert/strict';
import {setImmediate} from 'node:timers/promises';
import {createScene,fitBounds} from '../components/geometry/board-scene';
import type {BoardProps} from '../components/geometry/board';
import type {Point,Problem} from '../lib/geometry';
import {validateDrawing} from '../lib/display-constraints';
import pressureProblems from './fixtures/competition-geometry.json';
const {default:Nlp}=await import(new URL('../node_modules/jsxgraph/src/math/nlp.js',import.meta.url).href);
const {default:NativeBoard}=await import(new URL('../node_modules/jsxgraph/src/base/board.js',import.meta.url).href);

const circleProblem=():Problem=>({schemaVersion:1,id:'custom-circle-scene',title:'圆上动点',version:1,
 points:[{id:'O',x:0,y:0},{id:'Q',x:2,y:0},{id:'P',x:0,y:2},{id:'A',x:-1,y:2},{id:'B',x:3,y:0}],
 segments:[{id:'PA',points:['P','A']},{id:'PB',points:['P','B']}],circles:[],constructions:[],
 conditions:[{id:'circle',kind:'on_circle',args:['P','O','Q'],enabled:true,toggleable:true}],
 goal:{id:'goal',kind:'minimize',args:['P','A','P','B'],weights:[1,.5],enabled:true,toggleable:true},
 nondegenerate:{distinct:true,triangles:[]}});
function onCircle(points:Point[]){
 const [p,o,q]=['P','O','Q'].map(id=>points.find(p=>p.id===id)!);
 assert.ok(p&&o&&q,'all circle points exist');
 assert.ok(points.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
 const radius=Math.hypot(q.x-o.x,q.y-o.y);
 assert.ok(radius>1e-4,'the defining radius must not collapse');
 assert.ok(Math.abs(Math.hypot(p.x-o.x,p.y-o.y)-radius)<1e-4,'P must remain on its circle');
}

/** Records each render boundary, so a passing final placement cannot hide a bad intermediate frame. */
function sceneHarness(initial:Problem,extra:Partial<BoardProps>={},nlp=Nlp){
 const oldRaf=Object.getOwnPropertyDescriptor(globalThis,'requestAnimationFrame'),oldCancel=Object.getOwnPropertyDescriptor(globalThis,'cancelAnimationFrame');
 const oldDocument=Object.getOwnPropertyDescriptor(globalThis,'document'),oldMedia=Object.getOwnPropertyDescriptor(globalThis,'matchMedia');
 const frames=new Map<number,FrameRequestCallback>();let nextFrame=0,nextObject=0,suspended=0;
 Object.defineProperty(globalThis,'requestAnimationFrame',{configurable:true,value:(callback:FrameRequestCallback)=>{frames.set(++nextFrame,callback);return nextFrame}});
 Object.defineProperty(globalThis,'cancelAnimationFrame',{configurable:true,value:(id:number)=>frames.delete(id)});
 Object.defineProperty(globalThis,'document',{configurable:true,value:{querySelector:()=>null}});
 Object.defineProperty(globalThis,'matchMedia',{configurable:true,value:()=>({matches:false})});
 const previews:Point[][]=[],renders:Point[][]=[],states:boolean[]=[],events=new Map<string,()=>void>();
 const locusFrames:{points:Point[];shapes:{kind:string;parents:any[]}[]}[]=[];
 const objects:Record<string,any>={};
 let props:BoardProps={problem:initial,onPreview:points=>previews.push(structuredClone(points)),onConstraintState:valid=>states.push(valid),...extra};
 let bounds=[-5,5,5,-5];
 const coordinates=():Point[]=>Object.values(objects).filter(el=>el.kind==='point').map(el=>({id:el.attributes.name,x:el.X(),y:el.Y()}));
 const locusShapes=()=>Object.values(objects).filter(el=>el.attributes.dash===2).map(el=>({kind:el.kind,parents:el.parents.map((parent:any)=>typeof parent==='function'?parent():parent)}));
 const board:any={objects,containerObj:{style:{visibility:'visible'}},attr:{pan:{enabled:true}},
  suspendUpdate:()=>{suspended++},unsuspendUpdate:()=>{suspended--;if(!suspended){if(board.containerObj.style.visibility!=='hidden'){renders.push(coordinates());locusFrames.push({points:coordinates(),shapes:locusShapes()})}events.get('update')?.()}},
  getBoundingBox:()=>bounds,setBoundingBox:(value:number[])=>{bounds=value},
  on:(name:string,handler:()=>void)=>events.set(name,handler),off:(name:string)=>events.delete(name),
  removeObject:(el:any)=>{delete objects[el.id]},
  create:(kind:string,parents:any[],attributes:any)=>{
   let x=Number(parents[0]),y=Number(parents[1]);const handlers=new Map<string,()=>void>();
   const el:any={id:'object-'+(++nextObject),kind,attributes:{...attributes},parents,
    X:()=>x,Y:()=>y,setPosition:(_mode:unknown,position:number[])=>{[x,y]=position},
    setAttribute:(value:object)=>Object.assign(el.attributes,value),
    rendNode:{setAttribute:()=>{}},on:(name:string,handler:()=>void)=>handlers.set(name,handler),
    trigger:(name:string)=>handlers.get(name)?.(),movePointer:(position:number[])=>{[x,y]=position}};
   objects[el.id]=el;return el;
  }};
 const scene=createScene(board,{Math:{Nlp:nlp},COORDS_BY_USER:0},()=>props);
 const flush=()=>{for(let i=0;frames.size&&i<10;i++){const pending=[...frames.values()];frames.clear();pending.forEach(callback=>callback(performance.now()+1000))}};
 const point=(id:string)=>Object.values(objects).find(el=>el.kind==='point'&&el.attributes.name===id)!;
 const drag=(id:string,x:number,y:number)=>{const el=point(id);el.trigger('down');el.movePointer([x,y]);el.trigger('drag');flush();return el};
 return {scene,board,previews,renders,states,coordinates,point,drag,flush,locusShapes,locusFrames,
  setProps:(value:Partial<BoardProps>)=>{props={...props,...value}},
  cleanup:()=>{scene.dispose();for(const [key,value] of [['requestAnimationFrame',oldRaf],['cancelAnimationFrame',oldCancel],['document',oldDocument],['matchMedia',oldMedia]] as const){if(value)Object.defineProperty(globalThis,key,value);else Reflect.deleteProperty(globalThis,key)}}};
}

test('An imported circle with P initially at its center never renders that invalid placement',()=>{
 const problem=circleProblem();problem.points.find(p=>p.id==='P')!.y=0;
 const h=sceneHarness(problem);
 try{h.scene.sync();assert.ok(h.previews.length>0,'the valid circle placement should be constructed');for(const points of [...h.previews,...h.renders])if(points.length)onCircle(points)}finally{h.cleanup()}
});

test('Fitting a portrait board expands its shorter world span and contains the full figure',()=>{
 const problem=circleProblem();
 problem.points.find(p=>p.id==='B')!.x=14;
 const aspect=.6,[left,top,right,bottom]=fitBounds(problem,aspect);
 assert.ok(Math.abs((right-left)/(top-bottom)-aspect)<1e-12);
 for(const p of problem.points)assert.ok(p.x>left&&p.x<right&&p.y>bottom&&p.y<top);
 assert.ok(left<-2&&bottom<-2&&top>2);
});

test('JSXGraph picks a coincident motion handle before the defining point',()=>{
 const problem=circleProblem();
 problem.nondegenerate.distinct=false;
 Object.assign(problem.points.find(p=>p.id==='P')!,{x:2,y:0});
 const h=sceneHarness(problem);
 try{
  h.scene.sync();
  const candidate=(id:string)=>{
   const point=h.point(id);
   return {id,isDraggable:true,hasPoint:()=>true,visProp:{layer:point.attributes.layer},
    visPropCalc:{visible:true},lastDragTime:new Date(0),highlight:()=>{},triggerEventHandlers:()=>{},evalVisProp:()=>false};
  };
  const nativePicker={objectsList:[candidate('P'),candidate('Q')],downObjects:[],attr:{drag:{enabled:true}},renderer:{type:'none'},BOARD_MODE_DRAG:1,triggerEventHandlers:()=>{}};
  assert.equal(NativeBoard.prototype.initMoveObject.call(nativePicker,0,0,{},'mouse')[0].id,'P');
 }finally{h.cleanup()}
});

test('Applying committed coordinates keeps the manually chosen view',()=>{
 const problem=circleProblem(),h=sceneHarness(problem);
 try{
  h.scene.sync();const view=[-.5,3,1.8,-1];
  h.board.setBoundingBox(view);
  const driver=h.drag('P',1.2,1.6);driver.trigger('up');
  h.setProps({problem:{...problem,points:h.coordinates()}});h.scene.sync();
  assert.deepEqual(h.board.getBoundingBox(),view);
 }finally{h.cleanup()}
});

for(const entry of pressureProblems)test(`Complex pressure drawing: ${entry.name}`,()=>{
 const problem=structuredClone(entry.problem) as Problem,h=sceneHarness(problem);
 try{
  h.scene.sync();assert.equal(h.board.containerObj.style.visibility,'visible');assert.equal(h.coordinates().length,problem.points.length);
  const fixed=new Set(problem.conditions.filter(r=>r.enabled&&r.kind==='fixed_point').map(r=>r.args[0]));
  const driver=problem.points.find(p=>!fixed.has(p.id))!;
  h.drag(driver.id,driver.x+.17,driver.y+.23);
  assert.ok(h.previews.length&&h.renders.length);
  for(const frame of [...h.previews,...h.renders])if(frame.length)assert.equal(validateDrawing(problem,frame).valid,true,entry.name);
 }finally{h.cleanup()}
});

test('Text-only conditions never hide an otherwise valid drawing',()=>{
 const problem=circleProblem();problem.conditions.push({id:'unknown',kind:'free_text',args:[],description:'尚未编码的方程',enabled:true,toggleable:true});
 const h=sceneHarness(problem);
 try{h.scene.sync();assert.equal(h.board.containerObj.style.visibility,'visible');assert.ok(h.previews.length>0);assert.equal(h.states.at(-1),true)}finally{h.cleanup()}
});

test('Read-only invalid coordinates are not silently projected into a different counterexample',()=>{
 const problem=circleProblem();problem.points.find(p=>p.id==='P')!.y=0;
 const h=sceneHarness(problem,{readOnly:true});
 try{h.scene.sync();assert.equal(h.previews.length,0);assert.equal(h.board.containerObj.style.visibility,'hidden')}finally{h.cleanup()}
});

test('Switching a projected draft to read-only rechecks the exact source coordinates',()=>{
 const problem=circleProblem();problem.points.find(p=>p.id==='P')!.y=0;
 const h=sceneHarness(problem);
 try{
  h.scene.sync();assert.equal(h.board.containerObj.style.visibility,'visible');const count=h.previews.length;
  h.setProps({readOnly:true});h.scene.sync();
  assert.equal(h.board.containerObj.style.visibility,'hidden');assert.equal(h.previews.length,count);
 }finally{h.cleanup()}
});

test('Changing only the title reaffirms valid placement and sends a preview to the new callback',()=>{
 const problem=circleProblem(),h=sceneHarness(problem),states:boolean[]=[],previews:Point[][]=[];
 try{
  h.scene.sync();const point=h.point('P'),coordinates=h.coordinates();
  h.setProps({problem:{...problem,title:'新题目名称',version:problem.version+1},onConstraintState:valid=>states.push(valid),onPreview:points=>previews.push(points)});h.scene.sync();
  assert.deepEqual(states,[true]);assert.deepEqual(previews,[coordinates]);assert.equal(h.point('P'),point,'a title change need not rebuild the geometry');
  assert.equal(h.board.containerObj.style.visibility,'visible');
 }finally{h.cleanup()}
});

for(const ratio of [1,2])test(`The live ratio-${ratio} locus follows anchor motion and every rendered frame satisfies all conditions`,()=>{
 const problem:Problem={schemaVersion:1,id:'custom-ratio-scene',title:'阿氏轨迹',version:1,
  points:[{id:'A',x:-2,y:0},{id:'B',x:2,y:0},{id:'P',x:ratio===1?0:10/3,y:ratio===1?2:8/3}],segments:[],circles:[],constructions:[],
  conditions:[{id:'ratio',kind:'length_ratio',args:['P','A','P','B'],value:ratio,enabled:true,toggleable:true},{id:'fixed-b',kind:'fixed_point',args:['B'],coordinates:[2,0],enabled:true,toggleable:true}],
  goal:{id:'goal',kind:'minimize',args:['P','A','P','B'],weights:[1,.5],enabled:true,toggleable:true},nondegenerate:{distinct:true,triangles:[['A','B','P']]}};
 const h=sceneHarness(problem);
 const verifyLocus=(points:Point[],shapes:{kind:string;parents:any[]}[])=>{
  assert.equal(shapes.length,1);assert.equal(shapes[0].kind,ratio===1?'line':'circle');
  const shape=shapes[0],a=points.find(p=>p.id==='A')!,b=points.find(p=>p.id==='B')!,p=points.find(p=>p.id==='P')!;
  assert.equal(b.x,2);assert.equal(b.y,0);
  const check=(x:number,y:number)=>assert.ok(Math.abs(Math.hypot(x-a.x,y-a.y)-ratio*Math.hypot(x-b.x,y-b.y))<1e-5);
  check(p.x,p.y);
  if(ratio===1){
   const [[x1,y1],[x2,y2]]=shape.parents;assert.ok(Math.hypot(x2-x1,y2-y1)>0);
   for(const t of [-5,0,.5,1,5])check(x1+t*(x2-x1),y1+t*(y2-y1));
  }else{
   const [[cx,cy],radius]=shape.parents;assert.ok(Number.isFinite(radius)&&radius>0);
   assert.ok(Math.abs(Math.hypot(p.x-cx,p.y-cy)-radius)<1e-5);
   for(let i=0;i<12;i++)check(cx+radius*Math.cos(i*Math.PI/6),cy+radius*Math.sin(i*Math.PI/6));
  }
 };
 try{
  h.scene.sync();const initial=h.locusShapes();verifyLocus(h.coordinates(),initial);
  for(const [x,y] of [[3,3],[1.5,2.3],[-.5,3.5]])h.drag('P',x,y);
  h.drag('A',-1.8,.4);assert.notDeepEqual(h.locusShapes(),initial,'the same JSXGraph parents read current anchor coordinates');
  for(const points of [...h.renders,...h.previews])assert.ok(validateDrawing(problem,points).valid);
  for(const frame of h.locusFrames)verifyLocus(frame.points,frame.shapes);
  verifyLocus(h.coordinates(),h.locusShapes());
 }finally{h.cleanup()}
});

test('Every drag render and server commit stays on the circle without chord interpolation',async()=>{
 const problem=circleProblem();let committed=0;
 const h=sceneHarness(problem,{onMove:async(_point,preview)=>{committed++;return preview.map(p=>p.id==='P'?{...p,x:0,y:-2}:p)}});
 try{
  h.scene.sync();const p=h.drag('P',1.2,1.6);p.trigger('up');await setImmediate();h.flush();
  assert.equal(committed,1);onCircle(h.coordinates());for(const points of [...h.previews,...h.renders])if(points.length)onCircle(points);
  assert.ok(Math.abs(h.point('P').Y()+2)<1e-4,'the checked server endpoint was committed');
 }finally{h.cleanup()}
});

for(const response of ['invalid','undefined','throws'] as const)test(`A ${response} move response retains the last valid drawing`,async()=>{
 const problem=circleProblem();problem.points.find(p=>p.id==='P')!.y=0;
 const h=sceneHarness(problem,{onMove:async()=>{if(response==='throws')throw new Error('network failure');return response==='invalid'?problem.points:undefined}});
 try{
  h.scene.sync();const p=h.drag('P',1.2,1.6),before=h.coordinates();p.trigger('up');await setImmediate();h.flush();
  assert.deepEqual(h.coordinates(),before);for(const points of [...h.previews,...h.renders])if(points.length)onCircle(points);
 }finally{h.cleanup()}
});

test('Beginning another drag cancels the display effect of an older placement response',async()=>{
 const problem=circleProblem();let finish!:(points:Point[])=>void,starts=0;
 const h=sceneHarness(problem,{onDragStart:()=>{starts++},onMove:()=>new Promise(resolve=>{finish=resolve})});
 try{
  h.scene.sync();h.drag('P',1.2,1.6).trigger('up');h.drag('P',-1.2,1.6);const newest=h.coordinates();
  finish(problem.points.map(p=>p.id==='P'?{...p,x:0,y:-2}:p));await setImmediate();h.flush();
  assert.equal(starts,2);assert.deepEqual(h.coordinates(),newest);onCircle(newest);
 }finally{h.cleanup()}
});

test('An overlapping point releasing does not commit a different active drag',async()=>{
 const problem=circleProblem();const commits:string[]=[];
 const h=sceneHarness(problem,{onMove:point=>{commits.push(point.id)}});
 try{
  h.scene.sync();const driver=h.drag('P',1.2,1.6);
  h.point('Q').trigger('up');await setImmediate();assert.deepEqual(commits,[]);
  driver.trigger('up');await setImmediate();assert.deepEqual(commits,['P']);
 }finally{h.cleanup()}
});

test('High-frequency three-point dragging solves and renders once per frame without global NLP',()=>{
 const problem=structuredClone(pressureProblems.find(entry=>entry.name==='三动点三次反射')!.problem) as Problem;
 let solves=0;const h=sceneHarness(problem,{}, {FindMinimum:(...args:Parameters<typeof Nlp.FindMinimum>)=>{solves++;return Nlp.FindMinimum(...args)}});
 try{
  h.scene.sync();const before=h.coordinates(),renders=h.renders.length,previews=h.previews.length,p=h.point('P');
  p.trigger('down');
  for(let i=0;i<240;i++){p.movePointer([2+i/200,.1*Math.sin(i)]);p.trigger('drag')}
  assert.equal(h.renders.length,renders,'raw pointer events cannot render off the segment');
  h.flush();assert.equal(h.renders.length,renders+1);assert.equal(h.previews.length,previews+1);
  assert.equal(solves,0,'the exact line/segment projection needs no whole-scene optimizer');
  const after=h.coordinates();assert.ok(Math.abs(after.find(p=>p.id==='P')!.x-(2+239/200))<1e-10);
  for(const point of before.filter(p=>p.id!=='P'))assert.deepEqual(after.find(p=>p.id===point.id),point,'unrelated moving points and fixed points must not drift');
  for(const frame of [...h.previews,...h.renders])assert.ok(validateDrawing(problem,frame).valid);
 }finally{h.cleanup()}
});

test('Mouse-up before the animation frame commits the newest pointer and cancels the queued frame',async()=>{
 const problem=circleProblem();let committed:Point[]|undefined;
 const h=sceneHarness(problem,{onMove:async(_point,preview)=>{committed=structuredClone(preview);return preview}});
 try{
  h.scene.sync();const p=h.point('P');p.trigger('down');
  p.movePointer([2,0]);p.trigger('drag');p.movePointer([0,-3]);p.trigger('drag');p.trigger('up');
  await setImmediate();h.flush();assert.ok(committed);onCircle(committed!);
  assert.ok(Math.abs(committed!.find(p=>p.id==='P')!.y+2)<1e-10);assert.deepEqual(h.coordinates(),committed);
 }finally{h.cleanup()}
});

test('Disposal or a condition change cancels a queued drag before it can overwrite the new scene',()=>{
 const problem=circleProblem(),h=sceneHarness(problem);
 try{
  h.scene.sync();const p=h.point('P');p.trigger('down');p.movePointer([2,0]);p.trigger('drag');
  h.setProps({problem:{...problem,conditions:[]}});h.scene.sync();const after=h.coordinates();h.flush();assert.deepEqual(h.coordinates(),after);
  p.trigger('down');p.movePointer([8,8]);p.trigger('drag');h.scene.dispose();const count=h.previews.length;h.flush();assert.equal(h.previews.length,count);
 }finally{h.cleanup()}
});
