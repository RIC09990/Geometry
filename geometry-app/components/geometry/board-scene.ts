import {circleGeometry} from '@/lib/arc';
import {displayFollowers,projectDrawing,validateDrawing} from '@/lib/display-constraints';
import {drawingObjects} from '@/lib/drawing-objects';
import {ratioLocusGeometry,ratioLocusBounds} from '@/lib/ratio-loci';
import {normalizeDrawingProblem,type Point,type Problem} from '@/lib/geometry';
import type {BoardProps} from './board';
export function fitBounds(p:Problem,aspect?:number){
 const xs=p.points.map(p=>p.x).filter(Number.isFinite),ys=p.points.map(p=>p.y).filter(Number.isFinite);
 if(!xs.length||!ys.length)return [-5,5,5,-5];
 for(const c of drawingObjects(p).circles){const geometry=circleGeometry(p.points,c);if(geometry){xs.push(...geometry.samples.map(p=>p.x));ys.push(...geometry.samples.map(p=>p.y))}}
 for(const q of ratioLocusBounds(p.points,drawingObjects(p).loci)){xs.push(q.x);ys.push(q.y)}
 const l=Math.min(...xs),r=Math.max(...xs),b=Math.min(...ys),t=Math.max(...ys),pad=Math.max(r-l,t-b,.5)*.25;
 const width=r-l+2*pad,height=t-b+2*pad;
 const ratio=aspect&&Number.isFinite(aspect)&&aspect>0?aspect:width/height;
 const extraX=Math.max(0,height*ratio-width)/2,extraY=Math.max(0,width/ratio-height)/2;
 return [l-pad-extraX,t+pad+extraY,r+pad+extraX,b-pad-extraY];
}
export type BoardScene={sync:()=>void;fit:()=>void;dispose:()=>void};
const trajectoryRelations=new Set(['on_segment','on_arc','on_circle','collinear']);
/** JSXGraph draws the complete relation geometry; its NLP module projects all retained conditions. */
export function createScene(board:any,JX:any,props:()=>BoardProps):BoardScene{
 let points:Record<string,any>={},objects:any[]=[],signature='',lastValid:Point[]=[];let projecting=false;
 let disposed=false,lastCoordinates='',revision=0,dragFrame=0;
 let drag:{id:string;moved:boolean}|undefined;
 let pendingTarget:Point|undefined;
 let sceneProblem=normalizeDrawingProblem(props().problem);
 const visible=(valid:boolean)=>{if(board.containerObj)board.containerObj.style.visibility=valid?'visible':'hidden';props().onConstraintState?.(valid)};
 const create=(kind:string,parents:any[],attrs:any={})=>{const el=board.create(kind,parents,attrs);objects.push(el);return el};
 const hidden={visible:false,name:'',withLabel:false,fixed:true,highlight:false};
 const coords=():Point[]=>props().problem.points.filter(p=>points[p.id]).map(p=>({...p,x:points[p.id].X(),y:points[p.id].Y()}));
 const attrs=(p:Point)=>{
  const onTrajectory=sceneProblem.conditions.some(r=>r.enabled&&r.args[0]===p.id&&trajectoryRelations.has(r.kind));
  // JSXGraph picks the highest hit layer. The moving handle must win over
  // its supporting point when the two coincide, including on a closed arc.
  const layer=(JX.Options?.layer?.point??9)+Number(onTrajectory);
  return {name:props().labels===false?'':p.id,layer,size:props().small?2.2:4,strokeWidth:1,strokeColor:'#352f29',fillColor:displayFollowers(props().problem).has(p.id)?'#a68c65':'#352f29',fixed:!!props().readOnly||!!props().small||sceneProblem.conditions.some(r=>r.enabled&&r.kind==='fixed_point'&&r.args[0]===p.id),highlight:!props().small,highlightFillColor:'#8b6a43',showInfobox:false,label:{fontSize:props().small?17:23,fontUnit:'px',offset:[10,12],cssStyle:'font-family:Georgia,serif;font-style:italic;color:#342d26'}};
 };
 // Coordinates are committed atomically. Cartesian tweening leaves nonlinear loci.
 const moveCoordinates=(values:Point[],suspended=false)=>{
  const changed=values.filter(p=>points[p.id]&&(Math.abs(points[p.id].X()-p.x)>1e-12||Math.abs(points[p.id].Y()-p.y)>1e-12));
  if(!changed.length)return;
  if(!suspended)board.suspendUpdate();
  for(const p of changed)points[p.id].setPosition(JX.COORDS_BY_USER,[p.x,p.y]);
  if(!suspended)board.unsuspendUpdate();
 };
 const projectPending=(budget=12)=>{
  cancelAnimationFrame(dragFrame);dragFrame=0;
  const target=pendingTarget;pendingTarget=undefined;
  if(!target||drag?.id!==target.id||disposed||props().readOnly||props().small)return;
  projecting=true;
  try{
   const pixelsPerUnit=Math.min(Math.abs(board.unitX),Math.abs(board.unitY));
   const clearance=Number.isFinite(pixelsPerUnit)&&pixelsPerUnit>0?10/pixelsPerUnit:0;
   const projection=projectDrawing(sceneProblem,lastValid,target,JX.Math.Nlp,budget,clearance);
   if(!projection.valid||!projection.points.some((p,i)=>Math.abs(p.x-lastValid[i].x)>1e-12||Math.abs(p.y-lastValid[i].y)>1e-12))return;
   if(!drag.moved){drag.moved=true;props().onDragStart?.()}
   lastValid=projection.points;moveCoordinates(lastValid);props().onPreview?.(lastValid);
  }finally{projecting=false}
 };
 const commit=async(id:string)=>{
  // Mouse-up may arrive before the next animation frame. Commit its latest
  // pointer target, never the penultimate frame or a stale server response.
  if(drag?.id!==id)return;
  projectPending(24);
  const movedDuringDrag=drag.moved;drag=undefined;
  if(!movedDuringDrag||disposed||props().readOnly||props().small||!lastValid.length)return;
  const values=lastValid.map(p=>({...p})),moved=values.find(p=>p.id===id);
  if(!moved||!validateDrawing(sceneProblem,values).valid)return;
  const token=++revision;
  try{
   const accepted=await props().onMove?.(moved,values);
   if(disposed||token!==revision||drag)return;
   if(accepted&&validateDrawing(sceneProblem,accepted).valid){lastValid=accepted.map(p=>({...p}));moveCoordinates(lastValid);props().onPreview?.(lastValid)}
   // Missing, stale or invalid server placements cannot replace the last valid frame.
  }catch{if(!disposed&&token===revision&&!drag)moveCoordinates(lastValid)}
 };
 const build=()=>{
  const p=sceneProblem;points={};const enabled=p.conditions.filter(r=>r.enabled);
  for(const q of p.points)points[q.id]=create('point',[q.x,q.y],attrs(q));
  const style={strokeColor:'#403830',strokeWidth:props().small?2:2.6,highlight:false,fixed:true};
  const drawing=drawingObjects(p);
  for(const locus of drawing.loci){
   const geometry=()=>ratioLocusGeometry(coords(),locus),initial=geometry();
   const style={strokeColor:'#8b7253',strokeWidth:1.5,dash:2,highlight:false,fixed:true,withLabel:false};
   if(initial?.kind==='circle')create('circle',[()=>{const g=geometry();return g?.kind==='circle'?[g.cx,g.cy]:[NaN,NaN]},()=>{const g=geometry();return g?.kind==='circle'?g.r:NaN}],style);
   if(initial?.kind==='line')create('line',[()=>{const g=geometry();return g?.kind==='line'?[g.a.x,g.a.y]:[NaN,NaN]},()=>{const g=geometry();return g?.kind==='line'?[g.b.x,g.b.y]:[NaN,NaN]}],style);
  }
  drawing.segments.forEach(s=>{const el=create('segment',s.points.map(id=>points[id]),style);el.rendNode?.setAttribute('data-segment',s.points.slice().sort().join('|'))});
  drawing.circles.forEach(c=>create(c.end?'arc':'circle',c.end?[points[c.center],points[c.orientation==='cw'?c.end:c.through],points[c.orientation==='cw'?c.through:c.end]]:[points[c.center],points[c.through]],{strokeColor:'#8b7253',strokeWidth:2,fillOpacity:0,highlight:false,fixed:true}));
  // Equality ticks depend on live coordinates, never the coordinates at mount time.
  const groups=new Map<string,string>(),counts=new Map<string,number>(),pairs=new Map<string,string[]>();
  const root=(s:string):string=>groups.get(s)===s?s:root(groups.get(s)!);
  for(const r of enabled){const a=r.args,list=r.kind==='equal_length'?[a.slice(0,2),a.slice(2)]:r.kind==='midpoint'?[[a[0],a[1]],[a[0],a[2]]]:[];if(list.length!==2)continue;const keys=list.map(pair=>{const key=pair.slice().sort().join('|');pairs.set(key,pair);if(!groups.has(key))groups.set(key,key);return key});groups.set(root(keys[1]),root(keys[0]))}
  for(const [key,[a,b]] of pairs){const group=root(key);if(!counts.has(group))counts.set(group,counts.size+1);const count=counts.get(group)!;
   for(let i=0;i<count;i++){const endpoint=(sign:number)=>()=>{const u=points[a],v=points[b],dx=v.X()-u.X(),dy=v.Y()-u.Y(),len=Math.max(1e-9,Math.hypot(dx,dy)),bb=board.getBoundingBox(),size=Math.min(Math.max(bb[2]-bb[0],bb[1]-bb[3])*.008,len*.12),offset=(i-(count-1)/2)*size*.9;return [(u.X()+v.X())/2+dx/len*offset-sign*dy/len*size,(u.Y()+v.Y())/2+dy/len*offset+sign*dx/len*size]};create('segment',[endpoint(-1),endpoint(1)],{...style,strokeWidth:2})}
  }
  if(!props().small)for(const r of enabled.filter(r=>r.kind==='perpendicular')){const a=r.args,common=a.slice(0,2).find(v=>a.slice(2).includes(v));if(common){const u=a.slice(0,2).find(v=>v!==common),v=a.slice(2).find(v=>v!==common);if(u&&v)create('angle',[points[u],points[common],points[v]],{radius:.25,type:'square',orthoType:'square',fillOpacity:0,strokeColor:'#8b7253',strokeWidth:1.5,withLabel:false,highlight:false})}}
  for(const [id,point] of Object.entries(points)){
   point.rendNode?.setAttribute('data-point',id);
   point.on('drag',(event?:Event)=>{
    if(projecting||props().readOnly||props().small||!lastValid.length)return;
    if(drag?.id!==id){
     cancelAnimationFrame(dragFrame);dragFrame=0;drag={id,moved:false};revision++;
    }
    pendingTarget={id,x:point.X(),y:point.Y()};
    // JSXGraph first writes the raw pointer into the point. Restore its last
    // valid position without rendering before scheduling the checked frame.
    const previous=lastValid.find(p=>p.id===id);if(previous)point.setPosition(JX.COORDS_BY_USER,[previous.x,previous.y]);
    if(event?.type==='keydown'){void commit(id);return}
    if(!dragFrame)dragFrame=requestAnimationFrame(()=>projectPending());
   });
   point.on('up',()=>void commit(id));
  }
 };
 const fit=()=>{
  if(!lastValid.length||drag)return;
  const container=board.containerObj,aspect=container?.clientWidth/container?.clientHeight;
  // Expand the requested bounds ourselves. JSXGraph's portrait fit can
  // otherwise crop the longer horizontal span even with equal units.
  board.setBoundingBox(fitBounds({...sceneProblem,points:lastValid},aspect),false);
  board.keepaspectratio=true;
 };
 return {sync(){
  if(disposed)return;
  const p=normalizeDrawingProblem(props().problem),next=JSON.stringify([p.id,!!props().readOnly,p.points.map(p=>p.id),p.segments,p.circles,p.goal,p.nondegenerate,p.conditions.filter(r=>r.enabled)]);
  const structureChanged=next!==signature,firstPlacement=!lastValid.length||p.id!==sceneProblem.id;
  if(drag&&!structureChanged)return;
  const incoming=JSON.stringify(p.points);
  if(!structureChanged&&incoming===lastCoordinates&&lastValid.length){
   for(const q of p.points)points[q.id]?.setAttribute(attrs(q));visible(true);props().onPreview?.(lastValid);return;
  }
  revision++;drag=undefined;cancelAnimationFrame(dragFrame);dragFrame=0;pendingTarget=undefined;
  const projection=props().readOnly?{...validateDrawing(p,p.points),points:p.points}:projectDrawing(p,p.points,undefined,JX.Math.Nlp,36);
  if(!projection.valid||!validateDrawing(p,projection.points).valid){lastValid=[];visible(false);return;}
  sceneProblem={...p,points:projection.points};
  board.suspendUpdate();
  if(structureChanged){if(board.containerObj)board.containerObj.style.visibility='hidden';for(const el of objects.slice().reverse())if(board.objects[el.id])board.removeObject(el);objects=[];signature=next;build()}
  else moveCoordinates(projection.points,true);
  for(const q of p.points)points[q.id]?.setAttribute(attrs(q));
  board.attr.pan.enabled=!props().small;board.unsuspendUpdate();
  lastCoordinates=incoming;lastValid=coords();visible(true);props().onPreview?.(lastValid);
  const box=board.getBoundingBox();
  if(firstPlacement||structureChanged&&lastValid.some(q=>q.x<box[0]||q.x>box[2]||q.y>box[1]||q.y<box[3]))fit();
 },fit,dispose(){disposed=true;revision++;drag=undefined;cancelAnimationFrame(dragFrame);pendingTarget=undefined}};
}
