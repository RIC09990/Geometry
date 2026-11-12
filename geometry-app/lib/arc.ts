import type {Point} from './geometry';
export type CircleShape={center:string;through:string;end?:string|null;orientation?:'cw'|'ccw'};
export function circleGeometry(points:Point[],circle:CircleShape){
 const center=points.find(p=>p.id===circle.center),start=points.find(p=>p.id===circle.through),end=points.find(p=>p.id===circle.end);
 if(!center||!start)return;
 const radius=Math.hypot(start.x-center.x,start.y-center.y),angle=Math.atan2(start.y-center.y,start.x-center.x),sign=circle.orientation==='cw'?-1:1;
 const sweep=end?(sign*(Math.atan2(end.y-center.y,end.x-center.x)-angle)+Math.PI*2)%(Math.PI*2):Math.PI*2;
 return {center,radius,angle,sign,sweep,samples:Array.from({length:33},(_,i)=>({x:center.x+radius*Math.cos(angle+sign*sweep*i/32),y:center.y+radius*Math.sin(angle+sign*sweep*i/32)}))};
}
