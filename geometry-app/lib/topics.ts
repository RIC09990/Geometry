import {browserStorage} from '@/lib/browser-storage';
import {cleanProblem, readRecords, type Analysis, type Problem, type RecordEntry} from './geometry';

export type Topic = {id:string;problem:Problem;recognizedText:string;createdAt:string;updatedAt:string;result?:Analysis};
export type TopicSummary = {id:string;title:string;createdAt:string;updatedAt:string;recognizedText:string};
const LEGACY_KEY='geometry.topics.v1';
const BASE='/api/topics';

/** Restore a matching snapshot without an older cache hiding a saved AI answer. */
export function restoreTopicAnalysis(problem:Problem,record?:RecordEntry,topic?:Topic):Analysis|undefined{
 const snapshot=JSON.stringify(cleanProblem(problem));
 const matching=(entry?:{problem:Problem;result?:Analysis})=>entry?.result?.version===problem.version&&JSON.stringify(cleanProblem(entry.problem))===snapshot?entry.result:undefined;
 const recent=matching(record),saved=matching(topic);
 const newestSaved=(Date.parse(topic?.updatedAt||'')||0)>(Date.parse(record?.time||'')||0);
 const candidates=newestSaved?[saved,recent]:[recent,saved];
 const result=candidates.find((value):value is Analysis=>!!value);
 if(!result)return;
 const answerSource=candidates.find(value=>value?.aiAnswer?.version===problem.version);
 if(!answerSource)return result.aiAnswer?{...result,aiAnswer:undefined,proofs:result.proofs.filter(proof=>!proof.id.startsWith('ai-'))}:result;
 if(answerSource===result)return result;
 return {...result,aiAnswer:answerSource.aiAnswer,proofs:[...result.proofs.filter(proof=>!proof.id.startsWith('ai-')),...answerSource.proofs.filter(proof=>proof.id.startsWith('ai-'))]};
}
/** A saved structured topic can be read without sending it to an AI service. */
export function readTopicDocument(source:string):Problem|undefined{
 try{const value=JSON.parse(source),p=value.problem||value;
  if(p.schemaVersion===1&&/^custom-[a-zA-Z0-9-]+$/.test(p.id)&&typeof p.title==='string'&&Array.isArray(p.points)&&Array.isArray(p.conditions)&&p.goal&&p.nondegenerate)return cleanProblem(p);
 }catch{/* Ordinary text attachments continue through image/text recognition. */}
}

async function request<T>(path:string,init?:RequestInit):Promise<T>{
 let response:Response;
 try{response=await fetch(path,{...init,headers:{'Content-Type':'application/json',...(init?.headers||{})}})}
 catch{throw new Error('暂时无法连接本机计算服务，请确认“启动 Geometry.cmd”窗口仍在运行。')}
 if(!response.ok){
  let detail='';
  try{const data=await response.json() as {detail?:unknown};detail=typeof data?.detail==='string'?data.detail:''}catch{}
  throw new Error(detail||'本机探究记录暂不可用，请稍后重试。');
 }
 return response.json() as Promise<T>;
}

export const listTopics=(query='')=>request<TopicSummary[]>(BASE+(query?`?q=${encodeURIComponent(query)}`:''));
export const loadTopic=(id:string)=>request<Topic>(`${BASE}/${id}`);
export async function saveTopic(topic:Topic){
 const saved=await request<TopicSummary>(BASE,{method:'POST',body:JSON.stringify(topic)});
 window.dispatchEvent(new Event('geometry-topics'));
 return saved;
}
export async function renameTopic(id:string,title:string){
 const saved=await request<TopicSummary>(`${BASE}/${id}`,{method:'PATCH',body:JSON.stringify({title})});
 window.dispatchEvent(new Event('geometry-topics'));
 return saved;
}
export async function deleteTopic(id:string){
 await request<{deleted:boolean}>(`${BASE}/${id}`,{method:'DELETE'});
 const records=readRecords().filter(record=>record.problem.id!==id);
 browserStorage.setItem('geometry.records.v1',JSON.stringify(records));
 browserStorage.removeItem('geometry.draft.'+id);browserStorage.removeItem('geometry.original.'+id);
 window.dispatchEvent(new Event('geometry-topics'));window.dispatchEvent(new Event('geometry-records'));
}
/** Move topics saved by earlier versions out of localStorage once. */
let migration:Promise<number>|undefined;
export function migrateLocalTopics(){
 return migration??=migrateTopics().finally(()=>{migration=undefined});
}
async function migrateTopics(){
 const raw=browserStorage.getItem(LEGACY_KEY);if(!raw)return 0;
 let items:Topic[]=[];
 try{items=JSON.parse(raw)}catch{return 0}
 if(!Array.isArray(items))return 0;
 let moved=0;
 for(const [index,topic] of items.entries()){
  if(!topic?.problem||!/^custom-/.test(topic.id))continue;
  try{await request<TopicSummary>(BASE,{method:'POST',body:JSON.stringify(topic)})}catch{return moved}
  moved++;
  const remaining=items.slice(index+1);
  if(remaining.length)browserStorage.setItem(LEGACY_KEY,JSON.stringify(remaining));
  else browserStorage.removeItem(LEGACY_KEY);
 }
 return moved;
}
export function openTopic(topic:Topic){
 browserStorage.setItem('geometry.draft.'+topic.id,JSON.stringify(topic.problem));
 browserStorage.setItem('geometry.original.'+topic.id,JSON.stringify(topic.problem));
}
