'use client';
import {browserStorage} from '@/lib/browser-storage';
import {useT,useLanguage} from '@/lib/i18n';
import {useAiCredentials} from '@/lib/ai-credentials';
import {useAiChatState} from '@/lib/ai-chat-state';
import {useEffect,useRef,useState,type FormEvent} from 'react';
import {Send,Square,SquarePen,RefreshCw,KeyRound,Globe} from 'lucide-react';
import {api} from '@/lib/geometry';
import {feedbackPdfOptions} from '@/lib/pdf-export';
import {AiAttachments} from './ai-attachments';
import {AiSources} from './ai-sources';
import {AiKeyDialog} from './ai-key-dialog';
import {AiResponse} from './ai-response';
import {AiRelief} from './ai-material';
import {HomeworkReport,feedbackBody} from './homework-report';

type Status={configured:boolean;model:string;message:string};
export function AiChat(){
 const t=useT();const {language}=useLanguage();const credentials=useAiCredentials();
 const {session,state}=useAiChatState();const {messages,draft,busy,error,webSearch,files,readingFiles}=state;
 const [status,setStatus]=useState<Status>();const [checking,setChecking]=useState(false);
 const [keyOpen,setKeyOpen]=useState(false);
 const end=useRef<HTMLDivElement>(null);
 const configured=credentials.ready&&(credentials.mode==='personal'?!!credentials.key:credentials.mode==='server'&&!!status?.configured);
 async function check(){setChecking(true);try{setStatus(await api<Status>('ai/status'))}catch(e){session.update({error:(e as Error).message})}finally{setChecking(false)}}
 useEffect(()=>{try{browserStorage.removeItem('geometry.active-problem.v1')}catch{};void check();return session.show()},[session]);
 useEffect(()=>{end.current?.scrollIntoView({block:'nearest'})},[messages,busy]);
 const openKey=()=>setKeyOpen(true);
 async function send(e:FormEvent){
  e.preventDefault();if((!draft.trim()&&!files.length)||busy||readingFiles||!configured)return;
  await session.send({language,keyMode:credentials.mode,...credentials.options,headers:credentials.headers,emptyPrompt:t('请查看附件。')});
 }
 const configMessage=checking?'正在检查连接配置…':credentials.mode==='disabled'?'AI 已停用。重新填写 API Key 后才能发送。':credentials.mode==='personal'?'密钥仅保留在当前会话；刷新页面后需要重新填写。':'填写 API Key 后即可开始对话。';
 return <>
  <section className={'ai-chat'+(messages.length?' has-conversation':'')} aria-label={t('AI 几何学习助手')}>
   <AiRelief/>
   <div className="ai-chat-toolbar"><div className="ai-toolbar-actions">
    <button className="ai-toolbar-button" disabled={busy||readingFiles||!messages.length} onClick={()=>session.newConversation()}><SquarePen size={18}/><span>{t('新对话')}</span></button>
    <button className="ai-toolbar-button" onClick={openKey}><KeyRound size={18}/><span>{t(configured?'管理 API Key':'填写 API Key')}</span></button>
    {credentials.mode==='server'&&<button className="text-button" disabled={checking} onClick={check}><RefreshCw size={14}/>{t('重新检查')}</button>}
   </div></div>
   {!messages.length&&<header className="ai-heading"><h1>{t('今天研究什么？')}</h1></header>}
   <p className="visually-hidden" id="ai-connection-status" role="status">{!configured||checking?t(configMessage):t('Geometry小助手')}</p>
   <div className="ai-messages" role="log" aria-label={t('AI 对话记录')} aria-live="polite">
    {messages.map(m=><div key={m.id} className={'ai-message ai-'+m.role}><small>{m.role==='user'?t('你'):t('Geometry小助手')}</small>{m.role==='assistant'?<><HomeworkReport reply={m}/><AiResponse content={feedbackBody(m.content,m)} exportPdf={feedbackPdfOptions(m)}/><AiSources sources={m.sources} searchStatus={m.searchStatus}/></>:<><p>{m.content}</p>{!!m.images?.length&&<div className="message-images">{m.images.map((image,j)=><img key={j} src={image.dataUrl} alt={image.name}/>)}</div>}</>}</div>)}
    {busy&&<div className="ai-message ai-assistant"><small>{t('Geometry小助手')}</small><p className="ai-thinking"><span className="spinner"/>{t('正在生成回复…')}</p></div>}<div ref={end}/>
   </div>
   {error&&<p className="ai-error" role="alert">{t(error)}</p>}
   <form className="ai-compose" onSubmit={send}>
    <textarea aria-label={t('给 AI 的消息')} placeholder={t('输入你的问题，或上传题目和解答…')} maxLength={100000} rows={2} disabled={busy} value={draft} onChange={e=>session.update({draft:e.target.value})} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();e.currentTarget.form?.requestSubmit()}}}/>
    <div className="ai-compose-bottom">
     <AiAttachments files={files} disabled={busy||readingFiles} onChange={files=>session.update({files})} onReadingChange={readingFiles=>session.update({readingFiles})} label="上传"/>
     <label className="ai-web-toggle"><input type="checkbox" checked={webSearch} onChange={e=>session.update({webSearch:e.target.checked})} disabled={busy}/><Globe size={19}/><span>{t("联网搜索")}</span></label>
     {busy?<button type="button" className="button secondary ai-send" onClick={()=>session.stop()}><Square size={17}/>{t('停止')}</button>:<button className="button primary ai-send" aria-describedby="ai-connection-status" title={!configured?t(configMessage):undefined} disabled={readingFiles||(!draft.trim()&&!files.length)||!configured||checking}><Send size={18}/>{t('发送')}</button>}
    </div>
   </form>
  </section>
  {keyOpen&&<AiKeyDialog serverConfigured={status?.configured} onClose={()=>setKeyOpen(false)}/>}
 </>;
}
