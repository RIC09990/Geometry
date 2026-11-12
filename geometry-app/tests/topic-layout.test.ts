import test from 'node:test';
import assert from 'node:assert/strict';
import {topicConfirmationSnapshot,validateTopicMove,verifyTopicPlacement} from '../lib/topic-layout';
import {cleanProblem,type Problem} from '../lib/geometry';
import catalogue from '../data/cases.json';

const source=()=>cleanProblem({...catalogue[0],id:'custom-layout'} as Problem);

test('Confirmation uses exactly the displayed points and preserves human conditions',()=>{
 const problem=source();problem.conditions=problem.conditions.slice(1);
 const visible=problem.points.map(p=>({...p,x:p.x+.2}));
 const snapshot=topicConfirmationSnapshot(problem,{problem,points:visible});
 assert.deepEqual(snapshot.points,visible);
 assert.deepEqual(snapshot.conditions,problem.conditions);
 assert.notDeepEqual(snapshot.points,problem.points);
 visible[0].x=999;assert.notEqual(snapshot.points[0].x,999);
});

test('A preview of an older AI draft with the same version cannot replace current points',()=>{
 const old=source(),current=source();current.points[0].y+=1;
 const snapshot=topicConfirmationSnapshot(current,{problem:old,points:old.points});
 assert.deepEqual(snapshot.points,current.points);
});

for(const change of ['manual-edit','new-ai-draft','cancelled'] as const)test(`Late drag validation cannot restore ${change}`,async()=>{
 const previousFetch=globalThis.fetch,original=source(),abort=new AbortController();let current=original;
 let finish!:(response:Response)=>void;
 globalThis.fetch=()=>new Promise<Response>(resolve=>{finish=resolve});
 try{
  const pending=validateTopicMove(original,original.points[0],abort.signal,()=>current===original);
  if(change==='cancelled')abort.abort();
  else current={...original,version:change==='new-ai-draft'?original.version:original.version+1,conditions:original.conditions.slice(1)};
  const expected=current;
  finish(Response.json({status:'sat',points:original.points.map(p=>({...p,x:99}))}));
  assert.equal(await pending,undefined);
  assert.equal(current,expected);
 }finally{globalThis.fetch=previousFetch}
});

test('Current drag verification keeps the displayed points when the exact model rounds differently',async()=>{
 const previousFetch=globalThis.fetch,original=source(),abort=new AbortController();
 const visible=original.points.map(p=>({...p,y:p.y+.1})),returned=original.points.map(p=>({...p,y:p.y+.100001}));
 globalThis.fetch=async(url,init)=>{
  assert.equal(url,'/api/validate');assert.equal(init?.signal,abort.signal);
  const request=JSON.parse(init?.body as string);assert.deepEqual(request.problem.points,visible);
  assert.deepEqual(request.fixedPoints,visible.slice(1).map(p=>p.id));
  assert.deepEqual(request.pinned,visible[0]);
  return Response.json({status:'sat',points:returned});
 };
 try{
  const accepted=await validateTopicMove({...original,points:visible},visible[0],abort.signal,()=>true);
  assert.deepEqual(accepted,visible);
  assert.notDeepEqual(accepted,returned);
 }finally{globalThis.fetch=previousFetch}
});

test('Creation verifies the whole preview and keeps its current coordinates',async()=>{
 const previousFetch=globalThis.fetch,problem=source(),abort=new AbortController();
 problem.points.push(...['E','F','G','H','I','J'].map((id,i)=>({id,x:10+i,y:2})));
 globalThis.fetch=async(_url,init)=>{
  const request=JSON.parse(init?.body as string);
  assert.deepEqual(request.fixedPoints,problem.points.map(p=>p.id));
  assert.equal(request.pinned,undefined);
  return Response.json({status:'sat',points:problem.points.map(p=>({...p,y:p.y+.000001})),version:problem.version});
 };
 try{assert.deepEqual(await verifyTopicPlacement(problem,abort.signal),problem.points)}
 finally{globalThis.fetch=previousFetch}
});

test('Confirmation cannot persist an invalid live preview or unsupported retained condition',()=>{
 const problem=source(),invalid=problem.points.map(p=>p.id==='D'?{...p,y:p.y+1}:p);
 assert.throws(()=>topicConfirmationSnapshot(problem,{problem,points:invalid}),/尚未满足全部条件/);
 problem.conditions.push({id:'not-encoded',kind:'free_text',args:[],description:'待补充的曲线条件',enabled:true,toggleable:true});
 assert.throws(()=>topicConfirmationSnapshot(problem),/尚未满足全部条件/);
});

for(const defect of ['off-locus','moved-anchor','moved-follower','non-finite','missing-point','not-sat'] as const)test('A server '+defect+' response cannot replace the last valid preview',async()=>{
 const previousFetch=globalThis.fetch,original=source(),abort=new AbortController();
 const preview=original.points.map(p=>({...p}));
 const returned=preview.map(p=>({...p}));
 if(defect==='off-locus')returned.find(p=>p.id==='D')!.y+=1;
 if(defect==='moved-anchor')for(const p of returned)p.y+=1;
 if(defect==='moved-follower')returned.find(p=>p.id==='A')!.y+=.3;
 if(defect==='non-finite')returned[0].x=NaN;
 if(defect==='missing-point')returned.pop();
 globalThis.fetch=async()=>Response.json({status:defect==='not-sat'?'unknown':'sat',points:returned});
 try{
  await assert.rejects(validateTopicMove(original,preview.find(p=>p.id==='D')!,abort.signal,()=>true),/未通过条件核验/);
  assert.deepEqual(original.points,preview);
 }finally{globalThis.fetch=previousFetch}
});

test('Invalid local drag coordinates are never sent to the placement service',async()=>{
 const previousFetch=globalThis.fetch,original=source(),abort=new AbortController();let calls=0;
 const preview=original.points.map(p=>p.id==='D'?{...p,y:p.y+1}:p);
 globalThis.fetch=async()=>{calls++;return Response.json({status:'sat',points:preview})};
 try{
  await assert.rejects(validateTopicMove({...original,points:preview},preview[0],abort.signal,()=>true),/不满足全部保留条件/);
  assert.equal(calls,0);
 }finally{globalThis.fetch=previousFetch}
});
