import {normalizeDrawingProblem,type Point,type Problem,type Relation} from './geometry';
import {correctProjection,dragTangent,type Residual} from './drawing-projection';

type Nlp={FindMinimum:(f:(n:number,m:number,x:number[],constraints:number[])=>number,n:number,m:number,x:number[],start:number,end:number,print:number,limit:number)=>number};
export function displayFollowers(problem:Problem){
 const ids=new Set<string>();
 for(const r of problem.conditions.filter(r=>r.enabled)){
  if(['midpoint','on_segment','on_circle','on_arc','collinear','fixed_angle','equal_angle','inside_triangle','inside_circle','outside_circle','same_side','opposite_side'].includes(r.kind))ids.add(r.args[0]);
  if(r.kind==='equal_length'||r.kind==='length_ratio'){const common=r.args.slice(0,2).find(id=>r.args.slice(2).includes(id));ids.add(common||r.args[1])}
  if(r.kind==='fixed_length')ids.add(r.args[1]);
  if(r.kind==='similar_triangles')for(const id of r.args.slice(3))ids.add(id);
 }
 for(const r of problem.conditions.filter(r=>r.enabled&&r.kind==='perpendicular'))ids.add(ids.has(r.args[0])?r.args[1]:r.args[0]);
 const parallels=problem.conditions.filter(r=>r.enabled&&r.kind==='parallel');
 for(let i=0;i<parallels.length;i++){
  const first=parallels[i].args,other=parallels.slice(i+1).find(r=>r.args.every(id=>first.includes(id)));
  if(!other){ids.add(first[3]);continue}
  const vertices=[...new Set(first)],edges=[first.slice(0,2),first.slice(2),other.args.slice(0,2),other.args.slice(2)];
  const [a,b]=edges[0],c=edges.filter(e=>e.includes(b)).map(e=>e.find(id=>id!==b)!).find(id=>id!==a),fourth=vertices.find(id=>id!==a&&id!==b&&id!==c);
  if(fourth)ids.add(fourth);
 }
 return ids;
}
export function referenceAnchors(problem:Problem,driver:string){const followers=displayFollowers(problem);return problem.points.filter(p=>p.id!==driver&&!followers.has(p.id)).map(p=>p.id)}

const arities:Record<string,number>={fixed_point:1,equal_length:4,fixed_length:2,length_ratio:4,midpoint:3,perpendicular:4,parallel:4,collinear:3,on_segment:3,on_circle:3,on_arc:4,fixed_angle:3,equal_angle:6,similar_triangles:6,inside_triangle:4,inside_circle:3,outside_circle:3,same_side:4,opposite_side:4};
const tolerance=2e-6;
const bounded=(value:number)=>Number.isFinite(value)&&Math.abs(value)<=10000;
const invalidParameter=(r:Relation)=>r.kind==='fixed_point'?!r.coordinates||r.coordinates.length!==2||!r.coordinates.every(bounded):['fixed_length','fixed_angle','length_ratio'].includes(r.kind)&&(!Number.isFinite(r.value)||r.value!>100000||(r.kind==='fixed_length'?r.value!<0:r.value!<=0)||(r.kind==='fixed_angle'&&r.value!>=180));
/** Rendering references are structural, never additional geometric premises. */
function validDrawingReferences(problem:Problem,ids:Set<string>){
 if(!Array.isArray(problem.segments)||!Array.isArray(problem.circles))return false;
 if(problem.segments.some(s=>!s||!Array.isArray(s.points)||s.points.length!==2||s.points[0]===s.points[1]||s.points.some(id=>!ids.has(id))))return false;
 if(problem.circles.some(c=>!c||!ids.has(c.center)||!ids.has(c.through)||c.center===c.through||(c.end!=null&&(!ids.has(c.end)||c.end===c.center||c.end===c.through))||(c.orientation!=null&&!['cw','ccw'].includes(c.orientation))))return false;
 const goal=problem.goal;if(!goal||!Array.isArray(goal.args)||goal.args.some(id=>!ids.has(id)))return false;
 const arity=goal.kind==='angle_value'?3:arities[goal.kind];
 if(arity!==undefined&&goal.args.length!==arity)return false;
 if(goal.kind==='minimize'&&(goal.args.length<2||goal.args.length%2!==0))return false;
 return true;
}
/** Text-only conditions state premises the drawing cannot express, so the board
 * draws the encoded conditions and lists the rest as text. */
export function displayProblem(problem:Problem){
 return problem.conditions.some(r=>r.kind==='free_text')
  ?{...problem,conditions:problem.conditions.filter(r=>r.kind!=='free_text')}
  :problem;
}
/** Independent acceptance gate for imported, dragged and server-returned coordinates.
 * Equality tolerance must never also relax strict domains (distinct points, open
 * segments, nonzero circle radii and angle arms). */
export function validateDrawing(input:Problem,points:Point[]){
 const problem=normalizeDrawingProblem(input),unsupported:string[]=[];
 const fail=()=>({valid:false,error:Infinity,unsupported});
 const byId=new Map(points.map(p=>[p.id,p]));
 if(!points.length||points.length!==problem.points.length||byId.size!==points.length||problem.points.some(p=>!byId.has(p.id))||points.some(p=>!bounded(p.x)||!bounded(p.y)))return fail();
 if(!validDrawingReferences(problem,new Set(byId.keys())))return fail();
 let error=0,domain=true;
 const xy=(id:string)=>byId.get(id)!;
 const v=(a:string,b:string)=>[xy(b).x-xy(a).x,xy(b).y-xy(a).y];
 const dot=(a:number[],b:number[])=>a[0]*b[0]+a[1]*b[1],cross=(a:number[],b:number[])=>a[0]*b[1]-a[1]*b[0];
 const len=(a:string,b:string)=>Math.hypot(...v(a,b));
 const eq=(difference:number,scale=1)=>{error=Math.max(error,Math.abs(difference)/Math.max(1e-12,Math.abs(scale)))};
 const nonzero=(a:string,b:string)=>{const length=len(a,b);domain&&=length>1e-10;return length};
 const angle=(a:string,b:string,c:string)=>{nonzero(b,a);nonzero(b,c);return Math.atan2(Math.abs(cross(v(b,a),v(b,c))),dot(v(b,a),v(b,c)))};
 const triangle=(a:string[])=>{const u=v(a[0],a[1]),w=v(a[0],a[2]);domain&&=Math.abs(cross(u,w))>1e-10*Math.max(1e-12,Math.hypot(...u)*Math.hypot(...w))};
 for(const r of problem.conditions.filter(r=>r.enabled)){
  const a=r.args,count=arities[r.kind];
  if(count===undefined){unsupported.push(r.id);continue}
  if(a.length!==count||a.some(id=>!byId.has(id)))return fail();
  if(invalidParameter(r))return fail();
  switch(r.kind){
   case 'fixed_point':eq(xy(a[0]).x-r.coordinates![0]);eq(xy(a[0]).y-r.coordinates![1]);break;
   case 'inside_triangle':{const [p,u,w,z]=a,sides=[[u,w],[w,z],[z,u]].map(([start,end])=>cross(v(start,end),v(start,p)));domain&&=sides.every(s=>s>0)||sides.every(s=>s<0);break}
   case 'inside_circle':case 'outside_circle':{const radius=nonzero(a[1],a[2]),distance=len(a[0],a[1]);domain&&=r.kind==='inside_circle'?distance<radius:distance>radius;break}
   case 'same_side':case 'opposite_side':{nonzero(a[2],a[3]);const line=v(a[2],a[3]),product=cross(line,v(a[2],a[0]))*cross(line,v(a[2],a[1]));domain&&=r.kind==='same_side'?product>0:product<0;break}
   case 'equal_length':{const first=len(a[0],a[1]),second=len(a[2],a[3]);eq(first-second,Math.max(first,second));break}
   case 'fixed_length':eq(len(a[0],a[1])-r.value!,r.value!);break;
   case 'length_ratio':{const denominator=nonzero(a[2],a[3]),numerator=len(a[0],a[1]);eq(numerator-r.value!*denominator,Math.max(numerator,r.value!*denominator));break}
   case 'midpoint':{const p=xy(a[0]),u=xy(a[1]),w=xy(a[2]),scale=len(a[1],a[2]);eq(2*p.x-u.x-w.x,scale);eq(2*p.y-u.y-w.y,scale);break}
   case 'perpendicular':case 'parallel':{const product=nonzero(a[0],a[1])*nonzero(a[2],a[3]);eq(r.kind==='parallel'?cross(v(a[0],a[1]),v(a[2],a[3])):dot(v(a[0],a[1]),v(a[2],a[3])),product);break}
   case 'collinear':case 'on_segment':{const u=v(a[1],a[0]),w=v(a[1],a[2]),length=len(a[1],a[2]);eq(cross(u,w),Math.max(length*length,Math.hypot(...u)*length));if(r.kind==='on_segment'){const t=dot(u,w)/(length*length);domain&&=length>1e-10&&t>0&&t<1}break}
   case 'on_circle':{const radius=nonzero(a[1],a[2]);eq(len(a[0],a[1])-radius,radius);break}
   case 'on_arc':{let [p,o,u,w]=a;if(r.orientation==='cw')[u,w]=[w,u];const radius=nonzero(o,u);nonzero(u,w);eq(len(p,o)-radius,radius);eq(len(w,o)-radius,radius);for(const [first,last] of [[u,w],[u,p],[p,w]])error=Math.max(error,-cross(v(o,first),v(o,last))/(radius*radius));break}
   case 'fixed_angle':eq(angle(a[0],a[1],a[2])-r.value!*Math.PI/180);break;
   case 'equal_angle':eq(angle(a[0],a[1],a[2])-angle(a[3],a[4],a[5]));break;
   case 'similar_triangles':{triangle(a.slice(0,3));triangle(a.slice(3));const first=nonzero(a[0],a[1]),second=nonzero(a[3],a[4]);for(const [i,j] of [[0,2],[1,2]])eq(len(a[i],a[j])/first-len(a[i+3],a[j+3])/second);break}
  }
 }
 if(problem.nondegenerate.distinct)for(let i=0;i<points.length;i++)for(let j=i+1;j<points.length;j++)nonzero(points[i].id,points[j].id);
 for(const a of problem.nondegenerate.triangles){if(a.length!==3||a.some(id=>!byId.has(id)))return fail();triangle(a)}
 return {valid:domain&&unsupported.length===0&&Number.isFinite(error)&&error<tolerance,error:domain?error:Infinity,unsupported};
}
/** Numerical display placement only. Proofs and counterexamples still use Z3/SymPy. */
export function projectDrawing(input:Problem,reference:Point[],driver:Point|undefined,nlp:Nlp,budgetMilliseconds=Infinity,endpointClearance=0){
 const deadline=performance.now()+budgetMilliseconds;
 const problem=normalizeDrawingProblem(input),initial=validateDrawing(problem,reference),enabled=problem.conditions.filter(r=>r.enabled);
 const rejected=()=>({...initial,valid:false,points:reference});
 if(!validDrawingReferences(problem,new Set(reference.map(p=>p.id))))return rejected();
 if(initial.unsupported.length||!reference.length||reference.some(p=>!bounded(p.x)||!bounded(p.y))||reference.length!==problem.points.length||new Set(reference.map(p=>p.id)).size!==reference.length||problem.points.some(p=>!reference.some(q=>q.id===p.id)))return rejected();
 if(driver&&(!reference.some(p=>p.id===driver.id)||!bounded(driver.x)||!bounded(driver.y)))return rejected();
 for(const r of enabled)if(r.args.length!==arities[r.kind]||r.args.some(id=>!reference.some(p=>p.id===id))||invalidParameter(r))return rejected();
 if(problem.nondegenerate.triangles.some(a=>a.length!==3||a.some(id=>!reference.some(p=>p.id===id))))return rejected();
 const fixed=new Map(enabled.filter(r=>r.kind==='fixed_point').map(r=>[r.args[0],r.coordinates!]));
 const exactPins=reference.every(p=>{const pin=fixed.get(p.id);return !pin||p.x===pin[0]&&p.y===pin[1]});
 if(initial.valid&&exactPins&&(!driver||fixed.has(driver.id)))return {...initial,points:reference};
 const xs=reference.map(p=>p.x),ys=reference.map(p=>p.y),scale=Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys),1e-3);
 const clearance=Number.isFinite(endpointClearance)?Math.max(0,endpointClearance)/scale:0;
 const ox=(Math.max(...xs)+Math.min(...xs))/2,oy=(Math.max(...ys)+Math.min(...ys))/2;
 const index=new Map(reference.map((p,i)=>[p.id,2*i]));
 const start=reference.flatMap(p=>[(p.x-ox)/scale,(p.y-oy)/scale]),values=start.slice();
 const equations:Residual[]=[],limits:Residual[]=[];
 const eq=(f:Residual)=>equations.push(f);
 const ge=(f:Residual)=>limits.push(f);
 const xy=(x:number[],id:string)=>[x[index.get(id)!],x[index.get(id)!+1]];
 const vec=(x:number[],a:string,b:string)=>{const p=xy(x,a),q=xy(x,b);return[q[0]-p[0],q[1]-p[1]]};
 const dot=(a:number[],b:number[])=>a[0]*b[0]+a[1]*b[1],cross=(a:number[],b:number[])=>a[0]*b[1]-a[1]*b[0];
 const d2=(x:number[],a:string,b:string)=>{const v=vec(x,a,b);return dot(v,v)};
 const angle=(x:number[],a:string,b:string,c:string)=>{const u=vec(x,b,a),v=vec(x,b,c);return Math.atan2(Math.abs(cross(u,v)),dot(u,v))};
 for(const r of enabled){
  const a=r.args;
  switch(r.kind){
   case 'fixed_point':for(const i of [0,1])eq(x=>xy(x,a[0])[i]-(r.coordinates![i]-(i===0?ox:oy))/scale);break;
   case 'inside_triangle':{const [p,u,w,z]=a,sign=Math.sign(cross(vec(start,u,w),vec(start,u,z)))||1;for(const [first,last] of [[u,w],[w,z],[z,u]])ge(x=>sign*cross(vec(x,first,last),vec(x,first,p))-1e-8);break}
   case 'inside_circle':case 'outside_circle':{ge(x=>d2(x,a[1],a[2])-1e-10);const sign=r.kind==='inside_circle'?1:-1;ge(x=>sign*(d2(x,a[1],a[2])-d2(x,a[0],a[1]))-1e-8);break}
   case 'same_side':case 'opposite_side':{const sign=r.kind==='same_side'?1:-1;ge(x=>d2(x,a[2],a[3])-1e-10);ge(x=>sign*cross(vec(x,a[2],a[3]),vec(x,a[2],a[0]))*cross(vec(x,a[2],a[3]),vec(x,a[2],a[1]))-1e-8);break}
   case 'equal_length':eq(x=>d2(x,a[0],a[1])-d2(x,a[2],a[3]));break;
   case 'fixed_length':if(r.value===0){for(const i of [0,1])eq(x=>vec(x,a[0],a[1])[i])}else eq(x=>d2(x,a[0],a[1])-(r.value!/scale)**2);break;
   case 'length_ratio':eq(x=>d2(x,a[0],a[1])-(r.value??1)**2*d2(x,a[2],a[3]));ge(x=>d2(x,a[2],a[3])-1e-10);break;
   case 'midpoint':for(const i of [0,1])eq(x=>2*xy(x,a[0])[i]-xy(x,a[1])[i]-xy(x,a[2])[i]);break;
   case 'perpendicular':case 'parallel':{
    eq(x=>r.kind==='parallel'?cross(vec(x,a[0],a[1]),vec(x,a[2],a[3])):dot(vec(x,a[0],a[1]),vec(x,a[2],a[3])));ge(x=>d2(x,a[0],a[1])-1e-10);ge(x=>d2(x,a[2],a[3])-1e-10);break;
   }
   case 'collinear':case 'on_segment':{
    eq(x=>cross(vec(x,a[1],a[0]),vec(x,a[1],a[2])));
    if(r.kind==='on_segment'){ge(x=>dot(vec(x,a[1],a[0]),vec(x,a[1],a[2]))-1e-8);ge(x=>d2(x,a[1],a[2])-dot(vec(x,a[1],a[0]),vec(x,a[1],a[2]))-1e-8)}break;
   }
   case 'on_circle':eq(x=>d2(x,a[0],a[1])-d2(x,a[2],a[1]));ge(x=>d2(x,a[2],a[1])-1e-10);break;
   case 'on_arc':{
    let [point,center,first,last]=a;if(r.orientation==='cw')[first,last]=[last,first];
    eq(x=>d2(x,point,center)-d2(x,first,center));eq(x=>d2(x,last,center)-d2(x,first,center));
    ge(x=>d2(x,first,center)-1e-10);ge(x=>d2(x,first,last)-1e-10);
    ge(x=>cross(vec(x,center,first),vec(x,center,last))+1e-9);ge(x=>cross(vec(x,center,first),vec(x,center,point))+1e-9);ge(x=>cross(vec(x,center,point),vec(x,center,last))+1e-9);break;
   }
   case 'fixed_angle':case 'equal_angle':{
    eq(x=>angle(x,a[0],a[1],a[2])-(r.kind==='fixed_angle'?r.value!*Math.PI/180:angle(x,a[3],a[4],a[5])));ge(x=>d2(x,a[1],a[0])-1e-10);ge(x=>d2(x,a[1],a[2])-1e-10);
    if(r.kind==='equal_angle'){ge(x=>d2(x,a[4],a[3])-1e-10);ge(x=>d2(x,a[4],a[5])-1e-10)}break;
   }
   case 'similar_triangles':{
    eq(x=>d2(x,a[0],a[1])*d2(x,a[3],a[5])-d2(x,a[0],a[2])*d2(x,a[3],a[4]));
    eq(x=>d2(x,a[0],a[1])*d2(x,a[4],a[5])-d2(x,a[1],a[2])*d2(x,a[3],a[4]));
    for(const [u,v,w] of [a.slice(0,3),a.slice(3)]){const sign=Math.sign(cross(vec(start,u,v),vec(start,u,w)))||1;ge(x=>sign*cross(vec(x,u,v),vec(x,u,w))-1e-7)}break;
   }
   default:return {...rejected(),error:Infinity};
  }
 }
 if(problem.nondegenerate.distinct)for(let i=0;i<reference.length;i++)for(let j=i+1;j<reference.length;j++)ge(x=>d2(x,reference[i].id,reference[j].id)-1e-8);
 for(const [a,b,c] of problem.nondegenerate.triangles){const sign=Math.sign(cross(vec(start,a,b),vec(start,a,c)))||1;ge(x=>sign*cross(vec(x,a,b),vec(x,a,c))-1e-7)}
 const driverIndex=driver?index.get(driver.id):undefined;
 const target=driver?[(driver.x-ox)/scale,(driver.y-oy)/scale]:undefined;
 const openLoci=enabled.filter(r=>r.kind==='on_segment'&&r.args[0]===driver?.id);
 const nearOpenEnd=(coordinates:number[])=>openLoci.some(({args:[p,a,b]})=>{
  const length=Math.sqrt(d2(coordinates,a,b));
  const radius=Math.min(length/4,Math.max(length*1e-6,clearance*1.5));
  return Math.min(d2(coordinates,p,a),d2(coordinates,p,b))<=radius*radius;
 });
 const startsAtOpenEnd=nearOpenEnd(start);
 const followers=displayFollowers(problem);
 const preferred=new Set(referenceAnchors(problem,driver?.id??''));
 const placementRelations=new Set(['midpoint','on_segment','collinear','on_circle','on_arc','inside_triangle','inside_circle','outside_circle']);
 const supports=new Set(enabled.filter(r=>r.args[0]===driver?.id&&placementRelations.has(r.kind)).flatMap(r=>r.args.slice(1)));
 const firstSupport=supports.values().next().value;
 // Keep the defining line or circle whenever releasing other references gives
 // the driver a degree of freedom. Only explicit coordinate givens are hard pins.
 const anchorOptions=driver?[new Set([...preferred,...supports]),supports,preferred,new Set(firstSupport?[firstSupport]:[]),new Set<string>()]:[preferred,new Set<string>()];
 const orientedTriangles=[...problem.nondegenerate.triangles,...enabled.flatMap(r=>{
  const a=r.args;
  if(r.kind==='similar_triangles')return [a.slice(0,3),a.slice(3)];
  if(r.kind==='fixed_angle')return [a];
  if(r.kind==='inside_triangle')return [a.slice(1)];
  if(r.kind==='same_side'||r.kind==='opposite_side')return [[a[2],a[3],a[0]],[a[2],a[3],a[1]]];
  return [];
 })];
 const area=(x:number[],[a,b,c]:string[])=>cross(vec(x,a,b),vec(x,a,c));
 const branches=driver&&initial.valid?orientedTriangles.map(t=>[t,Math.sign(area(start,t))] as const).filter(([,sign])=>sign!==0):[];
 const set=(id:string,x:number,y:number)=>{const offset=index.get(id)!;values[offset]=x;values[offset+1]=y};
 const component=(anchors:Set<string>)=>{
  const available=new Set(reference.filter(p=>!anchors.has(p.id)&&!fixed.has(p.id)).map(p=>p.id));
  if(!driver||!initial.valid)return available;
  const affected=new Set(available.has(driver.id)?[driver.id]:[]);
  for(let previous=-1;previous!==affected.size;){
   previous=affected.size;
   for(const r of enabled)if(r.args.some(id=>affected.has(id)))for(const id of r.args)if(available.has(id))affected.add(id);
  }
  return affected;
 };
 const radial=(id:string,center:number[],radius:number,fallback:number[])=>{
  const wanted=xy(values,id),dx=wanted[0]-center[0],dy=wanted[1]-center[1],length=Math.hypot(dx,dy);
  const previous=xy(start,id),px=previous[0]-center[0],py=previous[1]-center[1],oldLength=Math.hypot(px,py);
  const direction=length>1e-12?[dx/length,dy/length]:oldLength>1e-12?[px/oldLength,py/oldLength]:fallback;
  set(id,center[0]+radius*direction[0],center[1]+radius*direction[1]);
 };
 const seed=(free:Set<string>,fraction=1)=>{
  for(let i=0;i<start.length;i++)values[i]=start[i];
  for(const [id,[x,y]] of fixed)set(id,(x-ox)/scale,(y-oy)/scale);
  if(driver&&free.has(driver.id)&&target&&driverIndex!==undefined)set(driver.id,
   start[driverIndex]+fraction*(target[0]-start[driverIndex]),start[driverIndex+1]+fraction*(target[1]-start[driverIndex+1]));
  // These exact seeds handle ordinary loci without running a numerical optimizer.
  for(let pass=0;pass<2;pass++)for(const r of enabled){
   const a=r.args;
   if((r.kind==='on_segment'||r.kind==='collinear')&&free.has(a[0])){
    const origin=xy(values,a[1]),direction=vec(values,a[1],a[2]),wanted=xy(values,a[0]),length=dot(direction,direction);
    if(length>1e-20){
     let t=((wanted[0]-origin[0])*direction[0]+(wanted[1]-origin[1])*direction[1])/length;
     if(r.kind==='on_segment'){
      const margin=Math.max(1e-8,Math.min(.2,(a[0]===driver?.id?clearance:0)/Math.sqrt(length)));
      t=Math.max(margin,Math.min(1-margin,t));
     }
     set(a[0],origin[0]+t*direction[0],origin[1]+t*direction[1]);
    }
   }
   if(r.kind==='midpoint'&&free.has(a[0])){const u=xy(values,a[1]),v=xy(values,a[2]);set(a[0],(u[0]+v[0])/2,(u[1]+v[1])/2)}
   if(r.kind==='fixed_length'){
    const moving=a.find(id=>id===driver?.id&&free.has(id))??[a[1],a[0]].find(id=>free.has(id));
    if(moving)radial(moving,xy(values,a.find(id=>id!==moving)??moving),r.value!/scale,[0,1]);
   }
   if((r.kind==='on_circle'||r.kind==='on_arc')&&free.has(a[0])){
    const center=xy(values,a[1]),u=vec(values,a[1],a[2]),radius=Math.hypot(...u);
    if(radius<=1e-12)continue;
    radial(a[0],center,radius,[-u[1]/radius,u[0]/radius]);
    if(r.kind==='on_arc'){
     const first=r.orientation==='cw'?a[3]:a[2],last=r.orientation==='cw'?a[2]:a[3];
     const u=vec(values,a[1],first),v=vec(values,a[1],last),w=vec(values,a[1],a[0]),sweep=Math.atan2(cross(u,v),dot(u,v));
     if(sweep>0){
      const angle=Math.atan2(cross(u,w),dot(u,w)),margin=problem.nondegenerate.distinct?Math.min(Math.max(1e-8,(a[0]===driver?.id?clearance:0)/radius),sweep/4):0;
      const clamped=angle>=margin&&angle<=sweep-margin?angle:Math.hypot(w[0]-u[0],w[1]-u[1])<=Math.hypot(w[0]-v[0],w[1]-v[1])?margin:sweep-margin;
      const bearing=Math.atan2(u[1],u[0])+clamped;set(a[0],center[0]+radius*Math.cos(bearing),center[1]+radius*Math.sin(bearing));
     }
    }
   }
   if(r.kind==='fixed_angle'){
    const arms=[a[0],a[2]],movable=arms.find(id=>id===driver?.id&&free.has(id))??arms.find(id=>free.has(id));
    if(!movable)continue;
    const other=movable===a[0]?a[2]:a[0],center=xy(values,a[1]),arm=vec(values,a[1],other),wanted=vec(values,a[1],movable),theta=r.value!*Math.PI/180,length=Math.hypot(...arm);
    if(length<=1e-12)continue;
    const branch=initial.valid?Math.sign(cross(vec(start,a[1],other),vec(start,a[1],movable))):0;
    let best:number[]|undefined,bestDistance=Infinity;
    for(const sign of branch?[branch]:[-1,1]){
     const c=Math.cos(theta),s=sign*Math.sin(theta),direction=[(c*arm[0]-s*arm[1])/length,(s*arm[0]+c*arm[1])/length],t=Math.max(1e-8,dot(wanted,direction));
     const candidate=[center[0]+t*direction[0],center[1]+t*direction[1]],distance=(t*direction[0]-wanted[0])**2+(t*direction[1]-wanted[1])**2;
     if(distance<bestDistance){best=candidate;bestDistance=distance}
    }
    if(best)set(movable,best[0],best[1]);
   }
   if(r.kind==='length_ratio'||r.kind==='equal_length'){
    const common=a.slice(0,2).find(id=>a.slice(2).includes(id));if(!common||!free.has(common))continue;
    const first=a.slice(0,2).find(id=>id!==common),second=a.slice(2).find(id=>id!==common);if(!first||!second||first===second)continue;
    const u=xy(values,first),v=xy(values,second),k=r.kind==='equal_length'?1:r.value!,delta=1-k*k;
    if(delta===0){const wanted=xy(values,common),dx=v[0]-u[0],dy=v[1]-u[1],length=dx*dx+dy*dy;if(length>1e-12){const t=((wanted[0]-(u[0]+v[0])/2)*dx+(wanted[1]-(u[1]+v[1])/2)*dy)/length;set(common,wanted[0]-t*dx,wanted[1]-t*dy)}}
    else if(Math.abs(delta)>1e-8){const center=[(u[0]-k*k*v[0])/delta,(u[1]-k*k*v[1])/delta],radius=k*Math.hypot(v[0]-u[0],v[1]-u[1])/Math.abs(delta);radial(common,center,radius,[0,1])}
   }
  }
 };
 const checked=(free:Set<string>)=>{
  if(branches.some(([triangle,sign])=>sign*area(values,triangle)<=0))return;
  const points=reference.map((p,i)=>{
   const pin=fixed.get(p.id);if(pin)return {...p,x:pin[0],y:pin[1]};
   const x=values[i*2],y=values[i*2+1];
   return free.has(p.id)&&(x!==start[i*2]||y!==start[i*2+1])?{...p,x:x*scale+ox,y:y*scale+oy}:p;
  });
  const result=validateDrawing(problem,points);
  // Relations that become dependent at an endpoint need tighter rounding
  // there. The visible clearance keeps the correction away from the limit.
  if(result.valid&&(!(startsAtOpenEnd||nearOpenEnd(values))||result.error<=1e-8))return {...result,points};
 };
 // When a connected construction has at most one reference vertex, a
 // similarity keeps all its angle/length ratios without moving other components.
 const trySimilarity=(free:Set<string>)=>{
  if(!driver||!target||!initial.valid||!free.has(driver.id))return;
  const related=enabled.filter(r=>r.args.some(id=>free.has(id)));
  const pins=new Set(related.flatMap(r=>r.args.filter(id=>!free.has(id))));
  if(pins.size>1)return;
  const origin=xy(start,driver.id),pin=pins.values().next().value;
  if(pin===undefined){
   for(const id of free){const p=xy(start,id);set(id,p[0]+target[0]-origin[0],p[1]+target[1]-origin[1])}
  }else{
   const anchor=xy(start,pin),u=vec(start,pin,driver.id),v=[target[0]-anchor[0],target[1]-anchor[1]],norm=dot(u,u);
   if(norm<1e-20)return;
   let real=dot(u,v)/norm,imag=cross(u,v)/norm;
   const magnitude=Math.hypot(real,imag);
   if(magnitude<1e-10)return;
   if(related.some(r=>r.kind==='fixed_length'&&r.value!==0)){real/=magnitude;imag/=magnitude}
   for(const id of free){const [x,y]=vec(start,pin,id);set(id,anchor[0]+real*x-imag*y,anchor[1]+imag*x+real*y)}
  }
  return checked(free);
 };
 const pointerDistance=target&&driverIndex!==undefined?Math.hypot(target[0]-start[driverIndex],target[1]-start[driverIndex+1]):0;
 const fallback:{free:Set<string>;variables:number[]}[]=[];
 const tried=new Set<string>();
 for(const anchors of anchorOptions){
  const signature=[...anchors].sort().join(',');
  if(tried.has(signature))continue;
  tried.add(signature);
  const free=component(anchors);
  const variables=reference.flatMap((p,i)=>free.has(p.id)?[2*i,2*i+1]:[]);
  seed(free);
  const exact=checked(free);
  const driverMovement=driver&&driverIndex!==undefined?Math.hypot(values[driverIndex]-start[driverIndex],values[driverIndex+1]-start[driverIndex+1]):0;
  if(exact&&(!driver||!initial.valid||pointerDistance<1e-10||driverMovement>Math.max(1e-10,pointerDistance*1e-4)))return exact;
  if(!variables.length){if(exact)return exact;continue}
  const mobility=variables.map(i=>driverIndex!==undefined&&Math.floor(i/2)===Math.floor(driverIndex/2)?1/32:followers.has(reference[Math.floor(i/2)].id)?1:1/4);
  const correct=(columns:number[],weights:number[],until:number)=>{
   let projected=checked(free);
   if(projected)return projected;
   if(correctProjection(values,columns,weights,equations,limits,()=>{projected=checked(free);return !!projected},until))return projected;
  };
  if(!exact&&initial.valid&&driverIndex!==undefined&&driverMovement>1e-10&&variables.length>2&&(startsAtOpenEnd||nearOpenEnd(values))){
   // At an almost singular endpoint, the old Jacobian can make a legal
   // handle look locked. Check whether its new locus position can be held
   // while the attached points recover their geometry.
   const attached=variables.filter(i=>i!==driverIndex&&i!==driverIndex+1);
   const result=correct(attached,attached.map(i=>mobility[variables.indexOf(i)]),Math.min(deadline,performance.now()+4));
   if(result)return result;
   seed(free);
  }
  const tangent=initial.valid&&driverIndex!==undefined&&target
   ?dragTangent(start,variables,mobility,equations,driverIndex,[target[0]-start[driverIndex],target[1]-start[driverIndex+1]])
   :undefined;
  if(tangent&&!tangent.movable)continue;
  // Forward construction can restore a dependent handle before its supports
  // have moved. Start from the joint tangent step in that case (e.g. dragging
  // a midpoint drives the point on its defining circle).
  if(exact&&(!tangent||Math.hypot(...tangent.step)<1e-10))return exact;
  if(!exact){const similar=trySimilarity(free);if(similar)return similar}
  for(const fraction of driver&&initial.valid?[1,.5,.25,.125]:[1]){
   if(performance.now()>=deadline)break;
   seed(free,fraction);
   if(exact&&tangent)for(const [j,i] of variables.entries())values[i]=start[i]+fraction*tangent.step[j];
   const projected=correct(variables,mobility,deadline);
   if(projected)return projected;
  }
  if(exact)return exact;
  fallback.push({free,variables});
  // With a real degree of freedom, keep this reference frame even when the
  // target is off its locus. Smaller valid steps are tried before holding it.
  if(driver&&initial.valid)break;
 }
 const checks=[...equations.flatMap(f=>[(x:number[])=>1e-9-f(x),(x:number[])=>1e-9+f(x)]),...limits];
 for(const {free,variables} of fallback){
  if(performance.now()>=deadline)break;
  seed(free);
  const coordinates=variables.map(i=>values[i]);
  const desired=driver&&openLoci.length&&clearance>0?xy(values,driver.id):target;
  const callback=(_n:number,_m:number,x:number[],con:number[])=>{
   if(performance.now()>=deadline)throw new Error('Display projection budget reached');
   for(const [j,i] of variables.entries())values[i]=x[j];
   for(const [j,check] of checks.entries())con[j]=check(values);
   let cost=0;
   for(const i of variables)cost+=driverIndex!==undefined&&desired&&(i===driverIndex||i===driverIndex+1)?10000*(values[i]-desired[i-driverIndex])**2:(values[i]-start[i])**2*(followers.has(reference[Math.floor(i/2)].id)?1:30);
   return cost;
  };
  try{
   nlp.FindMinimum(callback,coordinates.length,checks.length,coordinates,Math.max(.015,Math.min(.3,pointerDistance)),1e-9,0,1000);
   for(const [j,i] of variables.entries())values[i]=coordinates[j];
   const result=checked(free);
   if(result)return result;
  }catch{/* The caller keeps the last checked frame if placement times out. */}
 }
 if(initial.valid&&driver&&!fallback.length)return {...initial,points:reference};
 return rejected();
}
