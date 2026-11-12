'use client';
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {Trash2,ArrowUpRight} from 'lucide-react';
import {readTopics,deleteTopic,openTopic,type Topic} from '@/lib/topics';
import {text} from '@/lib/geometry';
import {useT} from '@/lib/i18n';
import {GeometryBoard} from './board';
import {Modal} from './common';
export function TopicCards(){
 const t=useT();const [topics,setTopics]=useState<Topic[]>([]),[deleting,setDeleting]=useState<Topic>(),[error,setError]=useState('');
 useEffect(()=>{const update=()=>setTopics(readTopics());update();window.addEventListener('geometry-topics',update);window.addEventListener('storage',update);return()=>{window.removeEventListener('geometry-topics',update);window.removeEventListener('storage',update)}},[]);
 return <>{topics.map((topic,i)=><div className="custom-topic-card" key={topic.id}><article className={'case-card case-'+((i+5)%5)}><span className="tape" aria-hidden="true"/><div className="case-card-top"><span className="case-number">{String(i+6).padStart(2,'0')}</span><span className="case-tag">{t('我的例题')}</span></div><h2>{topic.problem.title}</h2><GeometryBoard problem={topic.problem} small readOnly/><p>{t('求证：')}{t(text(topic.problem.goal))}</p><Link className="case-enter" href={'/cases/'+topic.id} onClick={()=>openTopic(topic)}>{t('开始探索')}<ArrowUpRight size={19}/></Link></article><button className="topic-delete" aria-label={t('删除例题')+' '+topic.problem.title} title={t('删除例题')} onClick={()=>{setDeleting(topic);setError('')}}><Trash2 size={16}/></button></div>)}{deleting&&<Modal title={t('删除例题')} onClose={()=>setDeleting(undefined)}><p>{t('删除')}{deleting.problem.title}{t('及其本机记录？')}</p>{error&&<p className="attachment-error">{error}</p>}<div className="topic-confirm-actions"><button className="button secondary" onClick={()=>setDeleting(undefined)}>{t('取消')}</button><button className="button primary" onClick={()=>{try{deleteTopic(deleting.id);setDeleting(undefined)}catch{setError(t('删除未完成，请重试。'))}}}>{t('删除')}</button></div></Modal>}</>;
}
