import {browserStorage} from '@/lib/browser-storage';
import catalogue from '@/data/cases.json';
import {spatialStatement} from './spatial-conditions';
export type Point = { id: string; x: number; y: number; fixed?:boolean };
export type Relation = { id: string; kind: string; args: string[]; enabled: boolean; toggleable: boolean; description?:string; value?:number|null; weights?:number[]; coordinates?:number[]; orientation?:'ccw'|'cw' };
export type Problem = { schemaVersion: 1; id: string; title: string; version: number; points: Point[]; segments: {id:string;points:string[]}[]; circles:{id:string;center:string;through:string;end?:string|null;orientation?:'ccw'|'cw'}[]; conditions: Relation[]; goal: Relation; nondegenerate:{distinct:boolean;triangles:string[][]}; constructions: never[];sourceText?:string };
export type ProofStep = {id:string;statement:string;rule?:string;premises:string[];affected?:boolean;missing?:string[];checkStatus?:string;checkedRelation?:Relation};
export type Proof = {id:string;title:string;engine:string;status:string;steps:ProofStep[];assumptionIds:string[];assumptionNodes:ProofStep[];raw?:string;input?:string;limitations?:string[];verification?:string};
export type Analysis = {aiAnswer?:TopicAnswer;version:number;outcome:'proven'|'optimized'|'counterexample'|'inconsistent'|'unknown';message:string;proofs:Proof[];search:{status:string;message?:string;raw?:string;input?:string;limitations?:string[]};impact:{proofId:string;title:string;removed:string[];affected:string[];steps:ProofStep[];engine:string}[];elapsed:number;engine?:string;angleAnswer?:{value:number;args:string[]};optimization?:{minimum?:string;value:number;movingPoint?:string;position?:number[];certificate:{verified:boolean;method?:string}};counterexample?:{coordinates:Record<string,string[]>;verified:boolean;checks:{id:string;passed:boolean}[];exact:boolean;engine:string}};
export type RecordEntry = {key:string;name:string;problem:Problem;time:string;result?:Analysis;saved:boolean};
export type TopicAnswer={content:string;version:number;sources?:{title:string;url:string}[];searchStatus?:string|null};
export const cases = catalogue as (Problem & {description:string;tag:string})[];
export const clone = <T,>(v:T):T=>JSON.parse(JSON.stringify(v));
/** Upgrade explicit coordinate premises in older saved/AI drafts, without inferring facts from a sketch. */
export function normalizeDrawingProblem(problem:Problem):Problem{
 let changed=false;
 let conditions=problem.conditions.map(r=>{
  if(r.kind!=='free_text'||!r.description)return r;
  const spatial=spatialStatement(r.description);
  if(spatial&&spatial.args.every(id=>problem.points.some(p=>p.id===id))&&(!r.args.length||(r.args.length===spatial.args.length&&r.args.every(id=>spatial.args.includes(id))))){changed=true;return {...r,...spatial}}
  let source=r.description.trim().replace(/[（]/g,'(').replace(/[）]/g,')').replace(/[，]/g,',').replace(/[−–]/g,'-');
  if(source.startsWith('\\(')&&source.endsWith('\\)'))source=source.slice(2,-2).trim();
  else if(source.startsWith('$')&&source.endsWith('$'))source=source.replace(/^\$+|\$+$/g,'').trim();
  source=source.replace(/\\left|\\right/g,'');
  // Match the entire statement. Fractions remain text until the coordinate
  // schema can preserve exact rationals instead of turning 1/3 into a decimal.
  const number='([+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?)';
  const match=source.match(new RegExp('^(?:(?:已知)?(?:定点|点))?\\s*([A-Z][0-9]?)\\s*(?:(?:的)?坐标(?:为|是))?\\s*(?:=|为)?\\s*\\(\\s*'+number+'\\s*,\\s*'+number+'\\s*\\)\\s*[。.;；]?$'));
  if(!match||!problem.points.some(p=>p.id===match[1])||(r.args.length>0&&(r.args.length!==1||r.args[0]!==match[1])))return r;
  const coordinates=match.slice(2).map(Number);
  if(!coordinates.every(v=>Number.isFinite(v)&&Math.abs(v)<=10000))return r;
  changed=true;return {...r,kind:'fixed_point',args:[match[1]],coordinates};
 });
 if(changed)conditions=conditions.filter((r,i)=>!(problem.conditions[i].kind==='free_text'&&problem.conditions[i].description?.includes('free_text')&&r.kind==='inside_triangle'&&conditions.some((other,j)=>j!==i&&!problem.conditions[j].description?.includes('free_text')&&other.kind===r.kind&&JSON.stringify(other.args)===JSON.stringify(r.args))));
 return changed?{...problem,conditions}:problem;
}
export const cleanProblem=(p:Problem):Problem=>{const {schemaVersion,id,title,version,points,segments,circles,conditions,goal,nondegenerate,constructions,sourceText}=normalizeDrawingProblem(p);return clone({schemaVersion,id,title,version,points:points.map(({fixed,...point})=>point),segments,circles,conditions,goal,nondegenerate,constructions,...(sourceText?{sourceText}:{})});};
export function text(r:Relation):string {const a=r.args;switch(r.kind){case'inside_triangle':return`${a[0]} 在△${a.slice(1).join('')}内部（不含边界）`;case'inside_circle':case'outside_circle':return`${a[0]} 在以 ${a[1]} 为圆心、过 ${a[2]} 的圆${r.kind==='inside_circle'?'内':'外'}（不含圆周）`;case'same_side':case'opposite_side':return`${a[0]}、${a[1]} 在直线 ${a[2]}${a[3]} 的${r.kind==='same_side'?'同':'异'}侧（不在线上）`;case'fixed_point':return`${a[0]} = (${r.coordinates?.join(', ')})（固定坐标）`;case'free_text':return r.description||'';case'equal_length':return`${a[0]}${a[1]} = ${a[2]}${a[3]}`;case'midpoint':return`${a[0]} 是 ${a[1]}${a[2]} 中点`;case'perpendicular':return`${a[0]}${a[1]} ⟂ ${a[2]}${a[3]}`;case'parallel':return`${a[0]}${a[1]} ∥ ${a[2]}${a[3]}`;case'collinear':return`${a.join('、')} 共线`;case'on_segment':return`${a[0]} 在线段 ${a[1]}${a[2]} 上（不含端点）`;case'equal_angle':return`∠${a.slice(0,3).join('')} = ∠${a.slice(3).join('')}`;case'length_ratio':return`${a[0]}${a[1]} = ${r.value} × ${a[2]}${a[3]}`;case'similar_triangles':return`△${a.slice(0,3).join('')} ∽ △${a.slice(3).join('')}`;case'fixed_angle':return`∠${a.join('')} = ${r.value}°`;case'angle_value':return`求 ∠${a.join('')} 的度数`;case'fixed_length':return`${a[0]}${a[1]} = ${r.value}`;case'on_arc':return`${a[0]} 在以 ${a[1]} 为圆心的弧 ${a[2]}${a[3]} 上`;case'minimize':return`求 ${a.filter((_,i)=>i%2===0).map((_,i)=>((r.weights?.[i]??1)===1?'':r.weights?.[i])+a.slice(i*2,i*2+2).join('')).join(' + ')} 的最小值`;case'on_circle':return`${a[0]} 在以 ${a[1]} 为圆心、过 ${a[2]} 的圆上`;default:return`暂不支持：${r.kind}`;}}
export async function api<T>(endpoint:string,body?:unknown,signal?:AbortSignal,extraHeaders?:Record<string,string>):Promise<T>{
 let response:Response;try{response=await fetch('/api/'+endpoint,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json',...extraHeaders}:extraHeaders,body:body?JSON.stringify(body):undefined,signal});}catch(e){if((e as Error).name==='AbortError')throw e;throw new Error('暂时无法连接本机计算服务，请确认“启动 Geometry.cmd”窗口仍在运行。');}
 if(!response.ok){let d:any;try{d=await response.json()}catch{};throw new Error(typeof d?.detail==='string'?d.detail:Array.isArray(d?.detail)?d.detail.map((v:{msg:string;type?:string})=>v.type==='extra_forbidden'?'页面与计算服务版本不同步，请稍后重试。':v.msg).join('；'):'计算服务暂不可用，请检查服务是否启动。');}return response.json();
}
const RECORDS='geometry.records.v1';
export function readRecords():RecordEntry[]{try{const data=JSON.parse(browserStorage.getItem(RECORDS)||'[]');return Array.isArray(data)?data:[]}catch{return[]}}
export function writeRecord(entry:RecordEntry){const all=readRecords();const next=[entry,...all.filter(r=>r.key!==entry.key)].slice(0,60);browserStorage.setItem(RECORDS,JSON.stringify(next));window.dispatchEvent(new Event('geometry-records'));}
export const outcomeText={proven:'结论已核验',optimized:'最小值已核验',counterexample:'已验证反例',inconsistent:'条件无法同时满足',unknown:'当前无法判断'};
