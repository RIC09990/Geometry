'use client';
import {useEffect,useRef,useState} from 'react';
import {Sparkles} from 'lucide-react';
import {api,type Problem,type Proof,type TopicAnswer} from '@/lib/geometry';
import {useT,useLanguage} from '@/lib/i18n';
import {TopicKeyButton,useTopicCredentials} from './topic-key';
import {boardImage} from '@/lib/board-image';
import {AiResponse} from './ai-response';
import {AiSources,type SearchReply} from './ai-sources';
import {topicAnswerText} from '@/lib/topic-answer';
export function ProofIdeas({problem,onResult,disabled,saved}:{problem:Problem;onResult:(proofs:Proof[],version:number,answer:TopicAnswer)=>void;disabled:boolean;saved?:TopicAnswer}){
 const t=useT(),{language}=useLanguage(),credentials=useTopicCredentials(),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const [webSearch,setWebSearch]=useState(true),[answer,setAnswer]=useState(''),[sources,setSources]=useState<SearchReply>({});
 const controller=useRef<AbortController|undefined>(undefined),sequence=useRef(0);
 const context=JSON.stringify([problem.id,problem.version,problem.conditions,problem.goal]);
 useEffect(()=>{controller.current?.abort();sequence.current++;setBusy(false);setMessage('');setAnswer('');setSources({});return()=>{controller.current?.abort();sequence.current++}},[context,credentials.mode,credentials.key,credentials.config]);
 useEffect(()=>{if(saved?.version===problem.version){setAnswer(topicAnswerText(saved.content));setSources(saved)}},[saved,problem.version]);
 async function find(){const token=++sequence.current,abort=new AbortController();controller.current=abort;setBusy(true);setMessage('');try{const reply=await api<{proofs:Proof[];version:number;message:string;answer:string}&SearchReply>('ai/proof-ideas',{problem,language,webSearch,diagram:boardImage(problem),keyMode:credentials.mode,...credentials.options},abort.signal,credentials.headers);if(token!==sequence.current||abort.signal.aborted)return;onResult(reply.proofs,reply.version,{content:reply.answer,version:reply.version,sources:reply.sources,searchStatus:reply.searchStatus});setAnswer(reply.answer);setSources(reply);setMessage(reply.message||(!reply.proofs.length&&!reply.answer?t('本次没有找到新的证明路线。'):''))}catch(e){if(!abort.signal.aborted)setMessage((e as Error).message)}finally{if(token===sequence.current)setBusy(false)}}
 return <div className="proof-ideas"><div className="proof-ideas-actions"><button className="button secondary" disabled={disabled||busy||!credentials.configured} onClick={()=>void find()}><Sparkles size={16}/>{t(busy?'正在整理解答…':'AI 解答与多解')}</button><label className="ai-web-toggle"><input type="checkbox" checked={webSearch} onChange={e=>setWebSearch(e.target.checked)} disabled={busy}/>{t('联网搜索')}</label>{!credentials.configured&&<TopicKeyButton/>}</div>{message&&<p role="status">{message}</p>}{answer&&<div className="ai-topic-answer"><AiResponse content={answer}/><AiSources sources={sources.sources} searchStatus={sources.searchStatus}/></div>}</div>;
}
