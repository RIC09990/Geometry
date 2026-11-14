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
import {AiThinking,AiElapsed,AiDebugBar} from './ai-debug';
import {AiKeyDialog} from './ai-key-dialog';
import {AiResponse} from './ai-response';
import {AiRelief} from './ai-material';
import {HomeworkReport,feedbackBody} from './homework-report';
import {AiConversations} from './ai-conversations';
import {listConversations,readConversation,saveConversation,renameConversation,deleteConversation,storedMessage,restoredMessages,type ConversationSummary} from '@/lib/ai-conversations';
import type {Preferences} from './app';

type Status={configured:boolean;model:string;message:string};
export function AiChat({prefs}:{prefs:Preferences}){
 const t=useT();const {language}=useLanguage();const credentials=useAiCredentials();
 const {session,state}=useAiChatState();const {messages,draft,busy,error,webSearch,files,readingFiles,streamStatus,lastUsage,summary}=state;
 const [status,setStatus]=useState<Status>();const [checking,setChecking]=useState(false);
 const [keyOpen,setKeyOpen]=useState(false);
 const end=useRef<HTMLDivElement>(null);
 const [items,setItems]=useState<ConversationSummary[]>([]);
 const [saveError,setSaveError]=useState('');
 const skipSave=useRef(false);
 const configured=credentials.ready&&(credentials.mode==='personal'?!!credentials.key:credentials.mode==='server'&&!!status?.configured);
 async function check(){setChecking(true);try{setStatus(await api<Status>('ai/status'))}catch(e){session.update({error:(e as Error).message})}finally{setChecking(false)}}
 useEffect(()=>{try{browserStorage.removeItem('geometry.active-problem.v1')}catch{};void check();return session.show()},[session]);
 useEffect(()=>{let cancelled=false;listConversations().then(list=>{if(!cancelled)setItems(list)}).catch(error=>{if(!cancelled)setSaveError((error as Error).message)});return()=>{cancelled=true}},[]);
 useEffect(()=>{
  if(skipSave.current){skipSave.current=false;return}
  if(!messages.length||busy)return;
  const timer=setTimeout(()=>{
   saveConversation({id:state.conversationId,title:'',messages:messages.map(storedMessage),lastUsage:state.lastUsage,...(state.summary?{summary:state.summary}:{})})
    .then(summary=>{setItems(current=>[summary,...current.filter(item=>item.id!==summary.id)].sort((a,b)=>b.updatedAt-a.updatedAt));setSaveError('')})
    .catch(error=>setSaveError('会话保存失败：'+(error as Error).message));
  },400);
  return ()=>clearTimeout(timer);
 },[messages,busy,state.conversationId,state.lastUsage]);
 useEffect(()=>{end.current?.scrollIntoView({block:'nearest'})},[messages,busy]);
 const openKey=()=>setKeyOpen(true);
 async function send(e:FormEvent){
  e.preventDefault();if((!draft.trim()&&!files.length)||busy||readingFiles||!configured)return;
  await session.send({language,keyMode:credentials.mode,...credentials.options,headers:credentials.headers,emptyPrompt:t('请查看附件。')});
 }
 const streaming=messages.at(-1)?.streaming===true;
 const statusLabel=streamStatus==='searching'?'正在检索资料…':streamStatus==='verifying'?'正在复核…':streamStatus==='retrying'?'正在重新生成…':'正在生成回复…';
 async function select(id:string){if(id===state.conversationId)return;try{const document=await readConversation(id);skipSave.current=true;session.loadConversation({id:document.id,messages:restoredMessages(document),lastUsage:document.lastUsage??undefined,summary:document.summary??undefined})}catch(error){setSaveError((error as Error).message)}}
 function startNew(){session.newConversation()}
 async function remove(id:string){try{await deleteConversation(id);setItems(current=>current.filter(item=>item.id!==id));if(id===state.conversationId)session.newConversation()}catch(error){setSaveError((error as Error).message)}}
 async function rename(id:string,title:string){try{const summary=await renameConversation(id,title);setItems(current=>current.map(item=>item.id===id?summary:item))}catch(error){setSaveError((error as Error).message)}}
 async function search(query:string){try{setItems(await listConversations(query))}catch(error){setSaveError((error as Error).message)}}
 const configMessage=checking?'正在检查连接配置…':credentials.mode==='disabled'?'AI 已停用。重新填写 API Key 后才能发送。':credentials.mode==='personal'?'密钥存储在本次浏览器会话：刷新不丢，关闭浏览器后需要重填。':'填写 API Key 后即可开始对话。';
 return <>
  <div className="ai-shell">
   <AiConversations items={items} activeId={state.conversationId} onSelect={select} onNew={startNew} onDelete={remove} onRename={rename} onSearch={search}/>
  <section className={'ai-chat'+(messages.length?' has-conversation':'')} aria-label={t('AI 几何学习助手')}>
   <AiRelief/>
   <div className="ai-chat-toolbar"><div className="ai-toolbar-actions">
    <button className="ai-toolbar-button" disabled={busy||readingFiles||!messages.length} onClick={startNew}><SquarePen size={18}/><span>{t('新对话')}</span></button>
    <button className="ai-toolbar-button" onClick={openKey}><KeyRound size={18}/><span>{t(configured?'管理 API Key':'填写 API Key')}</span></button>
    {credentials.mode==='server'&&<button className="text-button" disabled={checking} onClick={check}><RefreshCw size={14}/>{t('重新检查')}</button>}
   </div></div>
   {!messages.length&&<header className="ai-heading"><h1>{t('今天研究什么？')}</h1></header>}
   <p className="visually-hidden" id="ai-connection-status" role="status">{!configured||checking?t(configMessage):t('Geometry小助手')}</p>
   <div className="ai-messages" role="log" aria-label={t('AI 对话记录')} aria-live="polite">
    {summary&&<p className="ai-summary">{t('早期对话已压缩为摘要')}</p>}
    {messages.map(m=><div key={m.id} className={'ai-message ai-'+m.role}><small>{m.role==='user'?t('你'):t('Geometry小助手')}</small>{m.role==='assistant'?<>{m.reasoning!==undefined&&<AiThinking reasoning={m.reasoning} streaming={m.streaming}/>}{m.streaming?<pre className="ai-stream-text">{m.content||'…'}</pre>:<><HomeworkReport reply={m}/><AiResponse content={feedbackBody(m.content,m)} exportPdf={feedbackPdfOptions(m)}/></>}<AiSources sources={m.sources} searchStatus={m.searchStatus}/>{prefs.aiDebug&&typeof m.elapsedMs==='number'&&<AiElapsed milliseconds={m.elapsedMs}/>}</>:<><p>{m.content}</p>{!!m.images?.length&&<div className="message-images">{m.images.map((image,j)=><img key={j} src={image.dataUrl} alt={image.name}/>)}</div>}</>}</div>)}
    {busy&&!streaming&&<div className="ai-message ai-assistant"><small>{t('Geometry小助手')}</small><p className="ai-thinking"><span className="spinner"/>{t(statusLabel)}</p></div>}<div ref={end}/>
   </div>
   {error&&<p className="ai-error" role="alert">{t(error)}</p>}
   {saveError&&<p className="ai-error" role="alert">{saveError}</p>}
   <form className="ai-compose" onSubmit={send}>
    <textarea aria-label={t('给 AI 的消息')} placeholder={t('输入你的问题，或上传题目和解答…')} maxLength={100000} rows={2} disabled={busy} value={draft} onChange={e=>session.update({draft:e.target.value})} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();e.currentTarget.form?.requestSubmit()}}}/>
    <div className="ai-compose-bottom">
     <AiAttachments files={files} disabled={busy||readingFiles} onChange={files=>session.update({files})} onReadingChange={readingFiles=>session.update({readingFiles})} label="上传"/>
     <label className="ai-web-toggle"><input type="checkbox" checked={webSearch} onChange={e=>session.update({webSearch:e.target.checked})} disabled={busy}/><Globe size={19}/><span>{t("联网搜索")}</span></label>
     {busy?<button type="button" className="button secondary ai-send" onClick={()=>session.stop()}><Square size={17}/>{t('停止')}</button>:<button className="button primary ai-send" aria-describedby="ai-connection-status" title={!configured?t(configMessage):undefined} disabled={readingFiles||(!draft.trim()&&!files.length)||!configured||checking}><Send size={18}/>{t('发送')}</button>}
    </div>
   {prefs.aiDebug&&(lastUsage||busy)&&<AiDebugBar usage={lastUsage} status={streamStatus}/>}
   </form>
  </section>
  </div>
  {keyOpen&&<AiKeyDialog serverConfigured={status?.configured} onClose={()=>setKeyOpen(false)}/>}
 </>;
}
