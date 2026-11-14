'use client';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {Check,Pencil,Plus,Search,Trash2} from 'lucide-react';
import {useEffect,useState} from 'react';
import {deleteTopic,listTopics,loadTopic,migrateLocalTopics,openTopic,renameTopic,type TopicSummary} from '@/lib/topics';
import {useT} from '@/lib/i18n';

export function TopicCards(){
 const t=useT(),router=useRouter();
 const [items,setItems]=useState<TopicSummary[]>([]),[query,setQuery]=useState(''),[error,setError]=useState('');
 const [editing,setEditing]=useState(''),[draft,setDraft]=useState(''),[confirming,setConfirming]=useState(''),[busy,setBusy]=useState(false);
 const refresh=async(value:string)=>{try{setItems(await listTopics(value));setError('')}catch(e){setError((e as Error).message)}};
 useEffect(()=>{let live=true;const update=()=>void refresh('');void (async()=>{await migrateLocalTopics().catch(()=>0);if(live)await refresh('')})();window.addEventListener('geometry-topics',update);return()=>{live=false;window.removeEventListener('geometry-topics',update)}},[]);
 useEffect(()=>{const timer=setTimeout(()=>void refresh(query),200);return()=>clearTimeout(timer)},[query]);
 const open=async(id:string)=>{setBusy(true);try{const topic=await loadTopic(id);openTopic(topic);router.push('/cases/'+id)}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 const commit=async()=>{const title=draft.trim();if(editing&&title){try{await renameTopic(editing,title)}catch(e){setError((e as Error).message)}}setEditing('')};
 const remove=async(id:string)=>{if(confirming!==id){setConfirming(id);return}try{await deleteTopic(id);setConfirming('')}catch(e){setError((e as Error).message)}};
 return <aside className="explore-topics" aria-label={t('探索列表')}>
  <Link className="explore-new" href="/cases/new"><Plus size={15}/>{t('新建')}</Link>
  <label className="explore-search"><Search size={13}/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder={t('搜索探究')} aria-label={t('搜索探究')}/></label>
  <div className="explore-list">
   {items.length?items.map(item=><div key={item.id} className="explore-item">
    {editing===item.id?<div className="explore-rename-row">
     <input autoFocus value={draft} maxLength={80} onChange={event=>setDraft(event.target.value)} onBlur={commit} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();commit()}else if(event.key==='Escape')setEditing('')}}/>
     <button type="button" aria-label={t('重命名')} onClick={commit}><Check size={13}/></button>
    </div>:<>
     <button type="button" className="explore-link" disabled={busy} onClick={()=>open(item.id)}>
      <span>{item.title}</span><small>{item.updatedAt.slice(5,16).replace('T',' ')}</small>
     </button>
     <div className="explore-actions">
      <button type="button" aria-label={t('重命名')} onClick={()=>{setEditing(item.id);setDraft(item.title)}}><Pencil size={12}/></button>
      <button type="button" aria-label={t(confirming===item.id?'确认删除?':'删除')} className={confirming===item.id?'confirm':''} onClick={()=>remove(item.id)}>{confirming===item.id?<Check size={12}/>:<Trash2 size={12}/>}</button>
     </div>
    </>}
   </div>):<p className="explore-empty">{t('还没有保存的探究')}</p>}
  </div>
  {error&&<p className="explore-error" role="alert">{error}</p>}
 </aside>;
}
