'use client';
import {useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {Bot,Send,Square} from 'lucide-react';
import {api,type Problem} from '@/lib/geometry';
import {useT,useLanguage} from '@/lib/i18n';
import {useAiCredentials} from '@/lib/ai-credentials';
import {AiResponse} from './ai-response';
import {AiAttachments} from './ai-attachments';
import {attachmentImages,attachmentText,type AiAttachment,type AiImage} from '@/lib/ai-files';
import {boardImage} from '@/lib/board-image';
import {AiSources,type SearchReply} from './ai-sources';
import {HomeworkReport,feedbackBody,type HomeworkFeedback} from './homework-report';
import {feedbackPdfOptions} from '@/lib/pdf-export';
export function ProofReview({problem}:{problem:Problem}){
 const t=useT(),{language}=useLanguage(),credentials=useAiCredentials();
 const [webSearch,setWebSearch]=useState(false),[readingFiles,setReadingFiles]=useState(false);const [files,setFiles]=useState<AiAttachment[]>([]);const [text,setText]=useState(''),[reply,setReply]=useState<{content:string;version:number;exportImages:AiImage[]}&SearchReply&HomeworkFeedback>(),[busy,setBusy]=useState(false),[error,setError]=useState(''),[serverConfigured,setServerConfigured]=useState(false);
 const controller=useRef<AbortController|undefined>(undefined);const sequence=useRef(0);
 useEffect(()=>{let alive=true;void api<{configured:boolean}>('ai/status').then(s=>{if(alive)setServerConfigured(s.configured)}).catch(()=>{});return()=>{alive=false;controller.current?.abort();sequence.current++}},[]);
 useEffect(()=>{controller.current?.abort();sequence.current++;setBusy(false)},[problem,credentials.key,credentials.mode,credentials.config]);
 const configured=credentials.ready&&(credentials.mode==='personal'?!!credentials.key:credentials.mode==='server'&&serverConfigured);
 async function review(){
  if(!configured||(!text.trim()&&!files.length)||busy||readingFiles)return;const abort=new AbortController(),token=++sequence.current;controller.current=abort;setBusy(true);setReply(undefined);setError('');
  const submittedImages=attachmentImages(files);
  try{const response=await api<{content:string;version:number}&SearchReply&HomeworkFeedback>('ai/review-proof',{problem,proofText:text+attachmentText(files),diagram:boardImage(problem),images:submittedImages,language,webSearch,keyMode:credentials.mode,...credentials.options},abort.signal,credentials.headers);if(token===sequence.current&&!abort.signal.aborted)setReply({...response,exportImages:submittedImages})}catch(e){if(!abort.signal.aborted)setError((e as Error).message)}finally{if(token===sequence.current)setBusy(false)}
 }
 return <section className="paper-panel proof-review"><div className="panel-heading"><h2><Bot size={18}/>{t('检查我的证明思路')}</h2></div>
  <form onSubmit={e=>{e.preventDefault();void review()}}><label className="field">{t('写下你的证明过程')}<textarea aria-label={t('写下你的证明过程')} rows={5} maxLength={100000} value={text} placeholder={t('例如：因为 AB＝AC，D 是 BC 的中点，所以…')} onChange={e=>{controller.current?.abort();sequence.current++;setBusy(false);setText(e.target.value);setReply(undefined)}}/></label>
   <AiAttachments files={files} onReadingChange={setReadingFiles} onChange={value=>{controller.current?.abort();sequence.current++;setBusy(false);setFiles(value);setReply(undefined)}} disabled={busy}/><label className="ai-web-toggle"><input type="checkbox" checked={webSearch} disabled={busy} onChange={e=>setWebSearch(e.target.checked)}/>{t("联网搜索")}</label><p className="review-context">{t("已关联当前图形、已知条件和求证目标")}</p><div className="proof-review-actions">{!configured?<Link href="/ai" className="text-button">{t('到 AI 页填写 API Key')}</Link>:<small>{t('使用 AI 页的同一个 API Key')}</small>}{busy?<button type="button" className="button secondary" onClick={()=>{controller.current?.abort();sequence.current++;setBusy(false)}}><Square size={14}/>{t('停止')}</button>:<button type="submit" className="button primary" disabled={readingFiles||!configured||(!text.trim()&&!files.length)}><Send size={15}/>{t('检查思路')}</button>}</div>
  </form>{error&&<p role="alert" className="ai-error">{t(error)}</p>}{reply&&<div className={'proof-review-result '+(reply.version!==problem.version?'stale-result':'')} role="status"><small>{t(reply.version!==problem.version?'条件已改变，以下批注已过期':'AI 批注 · 非形式化验证')}</small><HomeworkReport reply={reply.version===problem.version?reply:{...reply,pdfEligible:false}}/><AiResponse content={feedbackBody(reply.content,reply)} exportPdf={reply.version===problem.version?feedbackPdfOptions(reply):undefined}/><AiSources sources={reply.sources} searchStatus={reply.searchStatus}/></div>}
 </section>;
}
