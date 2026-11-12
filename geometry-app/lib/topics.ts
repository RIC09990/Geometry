import {browserStorage} from '@/lib/browser-storage';
import {cleanProblem, readRecords, type Problem, type Analysis, type RecordEntry} from './geometry';

export type Topic = {id:string;problem:Problem;recognizedText:string;createdAt:string;updatedAt:string;result?:Analysis};
const KEY='geometry.topics.v1';
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
export function readTopics():Topic[]{
 try{const items=JSON.parse(browserStorage.getItem(KEY)||'[]');return Array.isArray(items)?items.filter(v=>v&&/^custom-/.test(v.id)&&v.problem?.id===v.id&&Array.isArray(v.problem.conditions)):[]}catch{return[]}
}
export function saveTopic(topic:Topic){
 const value={...topic,problem:cleanProblem(topic.problem),updatedAt:new Date().toISOString()};
 browserStorage.setItem(KEY,JSON.stringify([...readTopics().filter(t=>t.id!==topic.id),value]));
 window.dispatchEvent(new Event('geometry-topics'));
}
export function deleteTopic(id:string){
 if(!readTopics().some(t=>t.id===id))return;
 browserStorage.setItem(KEY,JSON.stringify(readTopics().filter(t=>t.id!==id)));
 browserStorage.setItem('geometry.records.v1',JSON.stringify(readRecords().filter(r=>r.problem.id!==id)));
 browserStorage.removeItem('geometry.draft.'+id);browserStorage.removeItem('geometry.original.'+id);
 window.dispatchEvent(new Event('geometry-topics'));window.dispatchEvent(new Event('geometry-records'));
}
export function openTopic(topic:Topic){
 browserStorage.setItem('geometry.draft.'+topic.id,JSON.stringify(topic.problem));
 browserStorage.setItem('geometry.original.'+topic.id,JSON.stringify(topic.problem));
}
