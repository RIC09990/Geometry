'use client';
import {useT} from '@/lib/i18n';
import Link from 'next/link';
import {useLayoutEffect,useRef,type CSSProperties} from 'react';
import {Home,Layers,BookOpen,ChevronRight,Bot} from 'lucide-react';
import {useAiChatActivity} from '@/lib/ai-chat-state';

const items=[{href:'/',label:'首页',Icon:Home},{href:'/ai',label:'AI',Icon:Bot},{href:'/cases',label:'探索',Icon:Layers},{href:'/about',label:'说明',Icon:BookOpen}];
// Shared by route instances in this browser; never written during server rendering.
let lastActiveIndex:number|undefined;

export function SideNavigation({activeIndex,reduceMotion}:{activeIndex:number;reduceMotion:boolean}){
 const t=useT(),activity=useAiChatActivity();
 const indicator=useRef<HTMLSpanElement>(null);
 const origin=useRef<{target:number;from:number;reduceMotion:boolean}|null>(null);
 useLayoutEffect(()=>{
  if(!origin.current||origin.current.target!==activeIndex)origin.current={target:activeIndex,from:lastActiveIndex??activeIndex,reduceMotion};
  else if(origin.current.reduceMotion!==reduceMotion)origin.current={target:activeIndex,from:activeIndex,reduceMotion};
  lastActiveIndex=activeIndex;
  const el=indicator.current;
  if(!el||reduceMotion||window.matchMedia('(prefers-reduced-motion: reduce)').matches||origin.current.from===activeIndex)return;
  const nav=el.parentElement!;
  const links=nav.querySelectorAll<HTMLAnchorElement>('a');
  const from=links[origin.current.from].offsetTop;
  const to=links[activeIndex].offsetTop;
  const animation=el.animate([{transform:`translateY(${from}px)`},{transform:`translateY(${to}px)`}],{duration:380,easing:'cubic-bezier(.22,.8,.25,1)'});
  return()=>animation.cancel();
 },[activeIndex,reduceMotion]);
 return <nav aria-label={t("主导航")} className="sliding-navigation" style={{'--nav-index':activeIndex} as CSSProperties}><span ref={indicator} className="nav-indicator" aria-hidden="true"/>{t(items.map(({href,label,Icon},index)=><Link key={href} href={href} aria-label={t(label)} aria-current={index===activeIndex?'page':undefined} className={index===activeIndex?'active':''}><Icon size={24}/><span>{t(label)}</span>{index===1&&activity&&<small className="nav-ai-status" role="status">{t(activity==='thinking'?'思考中…':'已回复')}</small>}<ChevronRight size={16} className="nav-arrow"/></Link>))}</nav>;
}
