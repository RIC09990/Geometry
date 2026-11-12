import {api,normalizeDrawingProblem,type Point,type Problem} from './geometry';
import {validateDrawing} from './display-constraints';

export type TopicPreview={problem:Problem;points:Point[]};
export function topicConfirmationSnapshot(problem:Problem,preview?:TopicPreview):Problem{
 const snapshot={...normalizeDrawingProblem(problem),points:(preview?.problem===problem?preview.points:problem.points).map(p=>({...p}))};
 if(!validateDrawing(snapshot,snapshot.points).valid)throw new Error('当前图形尚未满足全部条件，请先修正或补齐条件。');
 return snapshot;
}

/** Check for an exact model near the displayed placement. Layout is not a
 * request to construct a different configuration when the preview is valid. */
export async function verifyTopicPlacement(input:Problem,signal:AbortSignal,pinned?:Point):Promise<Point[]>{
 const problem=normalizeDrawingProblem(input),points=problem.points;
 if(!validateDrawing(problem,points).valid)throw new Error('当前图形不满足全部保留条件。');
 const xs=points.map(p=>p.x),ys=points.map(p=>p.y);
 const extent=Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys));
 const pinTolerance=Math.min(.001,Math.max(.00001,extent*2e-6));
 const result=await api<{status:string;points?:Point[];message?:string;version?:number}>('validate',{
  problem,pinned,fixedPoints:points.filter(p=>p.id!==pinned?.id).map(p=>p.id),pinTolerance,
 },signal);
 if(result.status==='sat'&&result.points&&(result.version===undefined||result.version===problem.version)&&validateDrawing(problem,result.points).valid){
  const actual=new Map(result.points.map(p=>[p.id,p]));
  if(points.every(expected=>{
   const p=actual.get(expected.id)!;
   return Math.max(Math.abs(p.x-expected.x),Math.abs(p.y-expected.y))<=pinTolerance+1e-9;
  }))return points;
 }
 throw new Error(result.message||'当前画板位置未通过条件核验，已保留最后一个有效图形。');
}

/** A late verification must never restore coordinates from an old draft. */
export async function validateTopicMove(problem:Problem,point:Point,signal:AbortSignal,isCurrent:()=>boolean){
 try{
  if(signal.aborted||!isCurrent())return;
  const points=await verifyTopicPlacement(problem,signal,point);
  if(signal.aborted||!isCurrent())return;
  return points;
 }catch(error){if(signal.aborted||!isCurrent())return;throw error}
}
