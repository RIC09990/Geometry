import test from 'node:test';
import assert from 'node:assert/strict';
import {ratioLoci,ratioLocusGeometry,ratioLocusBounds} from '../lib/ratio-loci';
import {drawingObjects} from '../lib/drawing-objects';
import type {Problem} from '../lib/geometry';
const source=():Problem=>({schemaVersion:1,id:'ratio',title:'distance ratio',version:1,
 points:[{id:'A',x:-2,y:1},{id:'B',x:2,y:4},{id:'P',x:0,y:3},{id:'Z',x:3,y:-2}],segments:[],circles:[],constructions:[],
 conditions:[{id:'condition',kind:'length_ratio',args:['P','A','P','B'],value:2,enabled:true,toggleable:true}],
 goal:{id:'goal',kind:'minimize',args:['P','A','P','B'],weights:[1,.5],enabled:true,toggleable:true},nondegenerate:{distinct:true,triangles:[]}});
const close=(a:number,b:number,tolerance=1e-8)=>assert.ok(Math.abs(a-b)<=tolerance*Math.max(1,Math.abs(a),Math.abs(b)),`${a} differs from ${b}`);
const distance=(a:{x:number;y:number},b:{x:number;y:number})=>Math.hypot(a.x-b.x,a.y-b.y);

test('Every point on an Apollonius locus satisfies its distance ratio for either segment orientation',()=>{
 for(const args of [['P','A','P','B'],['A','P','P','B'],['P','A','B','P'],['A','P','B','P']])for(const ratio of [.25,.5,2,4,1-1e-6,1+1e-6]){
  const problem=source();problem.conditions[0]={...problem.conditions[0],args,value:ratio};
  const locus=ratioLoci(problem)[0],geometry=ratioLocusGeometry(problem.points,locus)!;
  assert.equal(geometry.kind,'circle');if(geometry.kind!=='circle')continue;
  const a=problem.points[0],b=problem.points[1];
  for(let i=0;i<32;i++){const angle=i/32*Math.PI*2,p={x:geometry.cx+geometry.r*Math.cos(angle),y:geometry.cy+geometry.r*Math.sin(angle)};close(distance(p,a),ratio*distance(p,b))}
 }
});

test('Ratio exactly one renders the perpendicular bisector, including distant samples',()=>{
 const problem=source();problem.conditions[0].value=1;
 const geometry=ratioLocusGeometry(problem.points,ratioLoci(problem)[0])!;
 assert.equal(geometry.kind,'line');if(geometry.kind!=='line')return;
 for(const t of [-100,-1,0,.5,1,100]){const p={x:geometry.a.x+t*(geometry.b.x-geometry.a.x),y:geometry.a.y+t*(geometry.b.y-geometry.a.y)};close(distance(p,problem.points[0]),distance(p,problem.points[1]))}
});

test('Loci track anchor motion and point renaming without keeping an independent center',()=>{
 const problem=source(),original=ratioLoci(problem)[0],geometry=ratioLocusGeometry(problem.points,original)!;
 const moved=problem.points.map(p=>({...p,x:2*p.x+7,y:2*p.y-3})),next=ratioLocusGeometry(moved,original)!;
 assert.equal(geometry.kind,'circle');assert.equal(next.kind,'circle');
 if(geometry.kind==='circle'&&next.kind==='circle'){close(next.cx,2*geometry.cx+7);close(next.cy,2*geometry.cy-3);close(next.r,2*geometry.r)}
 const rename:Record<string,string>={P:'H',A:'E',B:'F',Z:'G'};
 problem.points=problem.points.map(p=>({...p,id:rename[p.id]}));problem.conditions[0].args=problem.conditions[0].args.map(id=>rename[id]);
 assert.deepEqual(ratioLocusGeometry(problem.points,ratioLoci(problem)[0]),geometry);
});

test('Only supported enabled premises produce loci; a goal never becomes a locus constraint',()=>{
 const problem=source();assert.equal(drawingObjects(problem).loci.length,1);
 problem.conditions[0].enabled=false;problem.goal={...problem.conditions[0],enabled:true};assert.deepEqual(ratioLoci(problem),[]);
 problem.conditions[0].enabled=true;
 for(const value of [0,-1,NaN,Infinity]){problem.conditions[0].value=value;assert.deepEqual(ratioLoci(problem),[])}
 problem.conditions[0].value=2;
 for(const args of [['A','P','B','Z'],['A','P','P','A'],['A','A','A','B'],['P','A','P','missing']]){problem.conditions[0].args=args;assert.deepEqual(ratioLoci(problem),[])}
});

test('Degenerate anchors are not misrepresented as a circle or perpendicular bisector',()=>{
 const problem=source(),locus=ratioLoci(problem)[0];
 const points=problem.points.map(p=>p.id==='B'?{...p,x:-2,y:1}:p);
 assert.equal(ratioLocusGeometry(points,locus),undefined);
 assert.equal(ratioLocusGeometry(points,{...locus,ratio:1}),undefined);
 assert.equal(ratioLocusGeometry(points.filter(p=>p.id!=='A'),locus),undefined);
 assert.equal(ratioLocusGeometry(points.map(p=>({...p,x:NaN})),locus),undefined);
});


test('Ordinary Apollonius circles fit completely while near-unit ratios retain a local view',()=>{
 const p=source(),loci=ratioLoci(p),g=ratioLocusGeometry(p.points,loci[0])!;assert.equal(g.kind,'circle');
 if(g.kind==='circle')assert.deepEqual(ratioLocusBounds(p.points,loci),[{x:g.cx-g.r,y:g.cy-g.r},{x:g.cx+g.r,y:g.cy+g.r}]);
 assert.deepEqual(ratioLocusBounds(p.points,[{...loci[0],ratio:1+1e-9}]),[]);
});
