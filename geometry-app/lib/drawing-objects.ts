import type {Problem,Relation} from './geometry';
import {ratioLoci} from './ratio-loci';

/** Visible geometry only. Adding an edge here never adds a mathematical premise. */
export function drawingObjects(problem:Problem){
 const segments:Problem['segments']=[],circles:Problem['circles']=[];
 const edges=new Set<string>(),rounds=new Set<string>(),ids=new Set(problem.points.map(p=>p.id));
 const segment=(a:string,b:string,id?:string)=>{
  if(a===b||!ids.has(a)||!ids.has(b))return;
  const key=[a,b].sort().join('|');if(edges.has(key))return;
  edges.add(key);segments.push({id:id??'display-'+key,points:[a,b]});
 };
 const circle=(c:Problem['circles'][number])=>{
  const key=[c.center,c.through,c.end??'',c.end?c.orientation??'ccw':''].join('|');
  if(rounds.has(key))return;rounds.add(key);circles.push(c);
 };
 for(const s of problem.segments)segment(s.points[0],s.points[1],s.id);
 for(const c of problem.circles)circle(c);
 const angle=(a:string[])=>{segment(a[0],a[1]);segment(a[1],a[2])};
 const triangle=(a:string[])=>{segment(a[0],a[1]);segment(a[1],a[2]);segment(a[2],a[0])};
 const relation=(r:Relation)=>{
  const a=r.args;
  switch(r.kind){
   case'equal_length':case'length_ratio':case'parallel':case'perpendicular':
    segment(a[0],a[1]);segment(a[2],a[3]);break;
   case'fixed_length':segment(a[0],a[1]);break;
   case'midpoint':segment(a[1],a[2]);segment(a[0],a[1]);segment(a[0],a[2]);break;
   case'on_segment':segment(a[1],a[2]);break;
   case'inside_triangle':triangle(a.slice(1));break;
   case'same_side':case'opposite_side':segment(a[2],a[3]);break;
   case'collinear':segment(a[0],a[1]);segment(a[1],a[2]);break;
   case'fixed_angle':case'angle_value':angle(a);break;
   case'equal_angle':angle(a.slice(0,3));angle(a.slice(3));break;
   case'similar_triangles':triangle(a.slice(0,3));triangle(a.slice(3));break;
   case'minimize':for(let i=0;i<a.length;i+=2)segment(a[i],a[i+1]);break;
   case'inside_circle':case'outside_circle':case'on_circle':case'on_arc':circle({id:'display-'+r.id,center:a[1],through:a[2],...(r.kind==='on_arc'?{end:a[3],orientation:r.orientation}:{})});break;
  }
 };
 for(const r of problem.conditions)if(r.enabled)relation(r);
 relation(problem.goal);
 return {segments,circles,loci:ratioLoci(problem)};
}
