import type {Point,Problem} from './geometry';

export type RatioLocus={id:string;point:string;a:string;b:string;ratio:number};
export type RatioLocusGeometry={kind:'circle';cx:number;cy:number;r:number}|{kind:'line';a:{x:number;y:number};b:{x:number;y:number}};

/** Fit ordinary loci completely. Near k=1, retain the useful local view of a huge circle. */
export function ratioLocusBounds(points:Point[],loci:RatioLocus[]){
 const span=Math.max(1e-3,Math.max(...points.map(p=>p.x))-Math.min(...points.map(p=>p.x)),Math.max(...points.map(p=>p.y))-Math.min(...points.map(p=>p.y)));
 return loci.flatMap(locus=>{const g=ratioLocusGeometry(points,locus);return g?.kind==='circle'&&g.r<=50*span?[{x:g.cx-g.r,y:g.cy-g.r},{x:g.cx+g.r,y:g.cy+g.r}]:[]});
}

/** PA = k PB defines a locus from the two anchors; no independent center or hidden premise is added. */
export function ratioLoci(problem:Problem):RatioLocus[]{
 const ids=new Set(problem.points.map(p=>p.id)),seen=new Set<string>(),loci:RatioLocus[]=[];
 for(const relation of problem.conditions){
  const {args,value}=relation;
  if(!relation.enabled||relation.kind!=='length_ratio'||args.length!==4||typeof value!=='number'||!Number.isFinite(value)||value<=0||args.some(id=>!ids.has(id)))continue;
  const first=args.slice(0,2),second=args.slice(2);
  if(first[0]===first[1]||second[0]===second[1])continue;
  const common=first.filter(id=>second.includes(id));
  if(common.length!==1)continue;
  const point=common[0],a=first.find(id=>id!==point)!,b=second.find(id=>id!==point)!;
  const key=JSON.stringify([point,a,b,value]);if(seen.has(key))continue;seen.add(key);
  loci.push({id:'ratio-locus-'+relation.id,point,a,b,ratio:value});
 }
 return loci;
}

export function ratioLocusGeometry(points:Point[],locus:RatioLocus):RatioLocusGeometry|undefined{
 const a=points.find(p=>p.id===locus.a),b=points.find(p=>p.id===locus.b),k=locus.ratio;
 if(!a||!b||![a.x,a.y,b.x,b.y,k].every(Number.isFinite)||k<=0)return;
 const dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy);
 if(!Number.isFinite(length)||length===0)return;
 if(k===1){
  const x=a.x/2+b.x/2,y=a.y/2+b.y/2,ux=-dy/length,uy=dx/length;
  return {kind:'line',a:{x:x-ux,y:y-uy},b:{x:x+ux,y:y+uy}};
 }
 // Use a reciprocal for k > 1 to avoid squaring large ratios; (1-k)(1+k)
 // also retains precision when the circle is large and approaches the k=1 line.
 const t=k>1?1/k:k,denominator=(1-t)*(1+t),origin=k>1?b:a,other=k>1?a:b;
 const factor=t*t/denominator,cx=origin.x+factor*(origin.x-other.x),cy=origin.y+factor*(origin.y-other.y),r=t*length/Math.abs(denominator);
 if(![cx,cy,r].every(Number.isFinite)||r<=0)return;
 return {kind:'circle',cx,cy,r};
}
