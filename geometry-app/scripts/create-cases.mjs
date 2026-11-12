import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const cataloguePath=fileURLToPath(new URL('../data/cases.json',import.meta.url));
const R=(id,kind,args,toggleable=true)=>({id,kind,args:args.split(' '),enabled:true,toggleable});
const P=(id,x,y)=>({id,x,y});
const make=(id,title,points,lines,conditions,goal,triangles,description,tag)=>({schemaVersion:1,id,title,version:1,points,segments:lines.split(' ').map(l=>({id:l,points:l.split('')})),circles:[],conditions,goal,nondegenerate:{distinct:true,triangles:triangles.map(t=>t.split(''))},constructions:[],description,tag});
export const cases=[
make('isosceles','等腰三角形', [P('A',0,3.5),P('B',-3,-1.5),P('C',3,-1.5),P('D',0,-1.5)],'AB AC BC AD', [R('equal-sides','equal_length','A B A C'),R('interior','on_segment','D B C',false),R('midpoint','midpoint','D B C'),R('altitude','perpendicular','A D B C')],R('goal','equal_angle','B A D D A C'),['ABC'],'当中线与高线的条件改变，角平分线还成立吗？','条件探究'),
make('midline','三角形中位线', [P('A',0,3.5),P('B',-3,-1.5),P('C',3,-1.5),P('D',-1.5,1),P('E',1.5,1)],'AB AC BC DE', [R('d-on','on_segment','D A B',false),R('e-on','on_segment','E A C',false),R('d-mid','midpoint','D A B'),R('e-mid','midpoint','E A C')],R('goal','parallel','D E B C'),['ABC'],'连接两边中点，观察平行关系的依据。','中点 · 平行'),
make('bisector','垂直平分线', [P('A',-3,-1),P('B',3,-1),P('M',0,-1),P('P',0,3)],'AB PM PA PB', [R('m-on','on_segment','M A B',false),R('m-mid','midpoint','M A B'),R('p-perp','perpendicular','P M A B')],R('goal','equal_length','P A P B'),['PAB'],'到两个端点等距，需要哪些条件共同成立？','垂直 · 等距'),
make('parallelogram','平行四边形的对边', [P('A',-2,-1.5),P('B',2,-1.5),P('C',3,2),P('D',-1,2)],'AB BC CD DA', [R('ab-parallel','parallel','A B C D'),R('ad-parallel','parallel','A D B C')],R('goal','equal_length','A B C D'),['ABC'],'两组对边平行，如何支持对边相等？','平行 · 等长'),
make('base-angles','等腰三角形的底角', [P('A',0,3.5),P('B',-3,-1.5),P('C',3,-1.5)],'AB AC BC',[R('equal-sides','equal_length','A B A C')],R('goal','equal_angle','A B C B C A'),['ABC'],'从边的相等，走向角的相等。','边角关系')
];
/** The catalogue belongs to this project, regardless of the launcher's working directory. */
export function writeCases(destination=cataloguePath){
 fs.mkdirSync(path.dirname(destination),{recursive:true});
 fs.writeFileSync(destination,JSON.stringify(cases,null,2));
}

if(process.argv[1]&&pathToFileURL(path.resolve(process.argv[1])).href===import.meta.url){
 if(process.argv.includes('--check')){
  const stored=JSON.parse(fs.readFileSync(cataloguePath,'utf8'));
  if(JSON.stringify(stored)!==JSON.stringify(cases))throw new Error('The saved catalogue differs from its generation source');
  console.log(`${cases.length} catalogue entries match their generation source.`);
 }else writeCases();
}
