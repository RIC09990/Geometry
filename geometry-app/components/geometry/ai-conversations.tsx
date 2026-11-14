'use client';
import {Check,Pencil,Plus,Search,Trash2,X} from 'lucide-react';
import {useEffect,useRef,useState} from 'react';
import {useT} from '@/lib/i18n';
import type {ConversationSummary} from '@/lib/ai-conversations';

type Props={items:ConversationSummary[];activeId:string;onSelect:(id:string)=>void;onNew:()=>void;
 onDelete:(id:string)=>void;onRename:(id:string,title:string)=>void;onSearch:(query:string)=>void};

export function AiConversations({items,activeId,onSelect,onNew,onDelete,onRename,onSearch}:Props){
 const t=useT();
 const [query,setQuery]=useState(''),[editing,setEditing]=useState(''),[draft,setDraft]=useState('');
 const [confirming,setConfirming]=useState(''),[mounted,setMounted]=useState(false);
 const search=useRef(onSearch);search.current=onSearch;
 const firstQuery=useRef(true);
 useEffect(()=>setMounted(true),[]);
 useEffect(()=>{
  if(firstQuery.current){firstQuery.current=false;return}
  const timer=setTimeout(()=>search.current(query),250);
  return()=>clearTimeout(timer);
 },[query]);
 useEffect(()=>{
  if(!confirming)return;
  const timer=setTimeout(()=>setConfirming(''),3000);
  return()=>clearTimeout(timer);
 },[confirming]);
 const startRename=(item:ConversationSummary)=>{setEditing(item.id);setDraft(item.title)};
 const commitRename=()=>{const title=draft.trim();if(editing&&title)onRename(editing,title);setEditing('')};
 const remove=(id:string)=>{
  if(confirming===id){onDelete(id);setConfirming('');return}
  setConfirming(id);
 };
 const time=(value:number)=>mounted?new Date(value*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'';
 return <aside className="ai-sessions" aria-label={t('会话列表')}>
  <div className="ai-sessions-head">
   <button type="button" className="ai-session-new" onClick={onNew}><Plus size={15}/>{t('新对话')}</button>
   <label className="ai-session-search"><Search size={13}/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder={t('搜索历史')} aria-label={t('搜索历史')}/></label>
  </div>
  <div className="ai-session-list">
   {items.length?items.map(item=><div key={item.id} className={'ai-session'+(item.id===activeId?' active':'')}>
    {editing===item.id?<div className="ai-session-rename-row">
     <input className="ai-session-rename" autoFocus value={draft} maxLength={120} onChange={event=>setDraft(event.target.value)} onBlur={commitRename}
      onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();commitRename()}else if(event.key==='Escape'){setEditing('')}}}/>
     <button type="button" aria-label={t('重命名')} onClick={commitRename}><Check size={13}/></button>
     <button type="button" aria-label={t('取消')} onClick={()=>setEditing('')}><X size={13}/></button>
    </div>:<>
     <button type="button" className="ai-session-open" onClick={()=>onSelect(item.id)} title={item.preview}>
      <span className="ai-session-title">{item.title}</span>
      <small>{time(item.updatedAt)}{item.messageCount?' · '+item.messageCount:''}</small>
     </button>
     <div className="ai-session-actions">
      <button type="button" aria-label={t('重命名')} onClick={()=>startRename(item)}><Pencil size={12}/></button>
      <button type="button" aria-label={t(confirming===item.id?'确认删除?':'删除')} className={confirming===item.id?'confirm':''} onClick={()=>remove(item.id)}>
       {confirming===item.id?<Check size={12}/>:<Trash2 size={12}/>}
      </button>
     </div>
    </>}
   </div>):<p className="ai-session-empty">{t('还没有历史会话')}</p>}
  </div>
 </aside>;
}
