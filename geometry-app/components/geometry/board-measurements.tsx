import type {Point,Relation} from '@/lib/geometry';
import {useT} from '@/lib/i18n';
export function BoardMeasurements({points,goal}:{points:Point[];goal:Relation}){
 const t=useT(),byId=new Map(points.map(p=>[p.id,p]));
 const length=(ids:string[])=>{const a=byId.get(ids[0]),b=byId.get(ids[1]);return a&&b?Math.hypot(a.x-b.x,a.y-b.y):NaN};
 const angle=(ids:string[])=>{const [a,b,c]=ids.map(id=>byId.get(id));if(!a||!b||!c)return NaN;const u=[a.x-b.x,a.y-b.y],v=[c.x-b.x,c.y-b.y],n=Math.hypot(...u)*Math.hypot(...v);return n<1e-20?NaN:Math.atan2(Math.abs(u[0]*v[1]-u[1]*v[0]),u[0]*v[0]+u[1]*v[1])*180/Math.PI};
 const a=goal.args;let entries:{label:string;value:number;unit?:string}[]=[];
 if(['fixed_angle','angle_value'].includes(goal.kind))entries=[{label:'∠'+a.join(''),value:angle(a),unit:'°'}];
 if(goal.kind==='equal_angle')entries=[{label:'∠'+a.slice(0,3).join(''),value:angle(a.slice(0,3)),unit:'°'},{label:'∠'+a.slice(3).join(''),value:angle(a.slice(3)),unit:'°'}];
 if(goal.kind==='equal_length')entries=[{label:a.slice(0,2).join(''),value:length(a.slice(0,2))},{label:a.slice(2).join(''),value:length(a.slice(2))}];
 if(goal.kind==='minimize'){
  const terms=(goal.weights||[]).map((weight,i)=>({label:a.slice(i*2,i*2+2).join(''),value:length(a.slice(i*2,i*2+2)),weight}));
  entries=[...terms.map(({label,value})=>({label,value})),{label:terms.map(v=>(v.weight===1?'':v.weight)+v.label).join(' + '),value:terms.reduce((sum,v)=>sum+v.weight*v.value,0)}];
 }
 if(goal.kind==='midpoint')entries=[{label:a[0]+a[1],value:length([a[0],a[1]])},{label:a[0]+a[2],value:length([a[0],a[2]])}];
 if(goal.kind==='parallel'||goal.kind==='perpendicular'){
  const [p,q,r,s]=a.map(id=>byId.get(id));if(p&&q&&r&&s){const u=[q.x-p.x,q.y-p.y],v=[s.x-r.x,s.y-r.y],n=Math.hypot(...u)*Math.hypot(...v);entries=[{label:t('两线夹角'),value:n<1e-20?NaN:Math.atan2(Math.abs(u[0]*v[1]-u[1]*v[0]),Math.abs(u[0]*v[0]+u[1]*v[1]))*180/Math.PI,unit:'°'}]}
 }
 if(!entries.length)return null;
 return <div className="board-measurements" aria-label={t('当前图形的测量值')}><small>{t('当前图形')}</small>{entries.map((e,i)=><span key={i+':'+e.label}><span className="math">{e.label}</span><strong>{Number.isFinite(e.value)?e.value.toFixed(8)+(e.unit||''):'—'}</strong></span>)}</div>;
}
