import {circleGeometry} from './arc';
import {drawingObjects} from './drawing-objects';
import {ratioLocusGeometry,ratioLocusBounds} from './ratio-loci';
import {validateDrawing} from './display-constraints';
import type {Problem} from './geometry';
import type {AiImage} from './ai-files';
/** An actual image of the same structured drawing accompanies its exact conditions. */
export function boardImage(problem:Problem):AiImage|undefined{
 if(!validateDrawing(problem,problem.points).valid)return undefined;
 const canvas=document.createElement('canvas');canvas.width=1100;canvas.height=850;const ctx=canvas.getContext('2d')!;
 const drawing=drawingObjects(problem),points=new Map(problem.points.map(p=>[p.id,p])),xs=problem.points.map(p=>p.x),ys=problem.points.map(p=>p.y);
 for(const c of drawing.circles){const arc=circleGeometry(problem.points,c);if(arc){xs.push(...arc.samples.map(p=>p.x));ys.push(...arc.samples.map(p=>p.y))}}
 for(const p of ratioLocusBounds(problem.points,drawing.loci)){xs.push(p.x);ys.push(p.y)}
 const left=Math.min(...xs),right=Math.max(...xs),bottom=Math.min(...ys),top=Math.max(...ys),scale=Math.min(900/Math.max(right-left,.5),650/Math.max(top-bottom,.5));
 const xy=(id:string)=>{const p=points.get(id)!;return [550+(p.x-(left+right)/2)*scale,425-(p.y-(top+bottom)/2)*scale]};
 ctx.fillStyle='#fcf8ee';ctx.fillRect(0,0,1100,850);ctx.strokeStyle='#403830';ctx.lineWidth=3;
 for(const s of drawing.segments){const a=xy(s.points[0]),b=xy(s.points[1]);ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke()}
 for(const c of drawing.circles){const geometry=circleGeometry(problem.points,c);if(!geometry)continue;const a=xy(c.center);ctx.beginPath();ctx.arc(a[0],a[1],geometry.radius*scale,-geometry.angle,-geometry.angle-geometry.sign*geometry.sweep,geometry.sign===1);ctx.stroke()}
 ctx.save();ctx.setLineDash([6,6]);ctx.lineWidth=2;
 for(const locus of drawing.loci){
  const g=ratioLocusGeometry(problem.points,locus);if(!g)continue;
  const convert=(x:number,y:number)=>[550+(x-(left+right)/2)*scale,425-(y-(top+bottom)/2)*scale];
  ctx.beginPath();
  if(g.kind==='circle'){const [x,y]=convert(g.cx,g.cy);ctx.arc(x,y,g.r*scale,0,2*Math.PI)}
  else {const dx=g.b.x-g.a.x,dy=g.b.y-g.a.y,length=Math.hypot(dx,dy),extent=2000/scale;const a=convert(g.a.x-extent*dx/length,g.a.y-extent*dy/length),b=convert(g.a.x+extent*dx/length,g.a.y+extent*dy/length);ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1])}
  ctx.stroke();
 }
 ctx.restore();
 ctx.font='italic 27px Georgia';ctx.fillStyle='#352f29';
 for(const p of problem.points){const [x,y]=xy(p.id);ctx.beginPath();ctx.arc(x,y,5,0,Math.PI*2);ctx.fill();ctx.fillText(p.id,x+10,y-10)}
 return {name:'当前几何图形.png',dataUrl:canvas.toDataURL('image/png')};
}
