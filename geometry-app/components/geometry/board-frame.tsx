'use client';
import {useEffect,useRef,useState,type ReactNode} from 'react';
import {Maximize,Minimize,RotateCcw} from 'lucide-react';
import {useT} from '@/lib/i18n';
export function BoardFrame({children,title,onFit}:{children:ReactNode;title?:string;onFit:()=>void}){
 const t=useT(),ref=useRef<HTMLElement>(null),[expanded,setExpanded]=useState(false);
 useEffect(()=>{
  if(!expanded)return;const el=ref.current!,overflow=document.body.style.overflow,root=document.documentElement,gutter=root.style.scrollbarGutter,rootOverflow=root.style.overflow;
  document.body.style.overflow='hidden';root.style.overflow='hidden';root.style.scrollbarGutter='auto';if(document.fullscreenElement!==el){el.setAttribute('popover','manual');el.showPopover()}
  const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();setExpanded(false)}};
  document.addEventListener('keydown',escape);
  const fullChange=()=>{if(!document.fullscreenElement)setExpanded(false)};document.addEventListener('fullscreenchange',fullChange);
  return()=>{document.removeEventListener('keydown',escape);document.removeEventListener('fullscreenchange',fullChange);if(el.matches(':popover-open'))el.hidePopover();el.removeAttribute('popover');if(document.fullscreenElement===el)void document.exitFullscreen();document.body.style.overflow=overflow;root.style.scrollbarGutter=gutter;root.style.overflow=rootOverflow};
 },[expanded]);
 const toggle=async()=>{if(expanded){setExpanded(false);return}const el=ref.current!;if(document.fullscreenEnabled){try{await el.requestFullscreen()}catch{ /* The in-app browser may permit only viewport expansion. */ }}setExpanded(true)};
 return <section ref={ref} className={'board-paper '+(expanded?'board-expanded':'')} aria-label={t('几何画板')}>
  <div className="board-top"><span><span className="live-dot"/>{t(title||'动态几何画板')}</span><div className="board-view-controls">
   <button type="button" className="text-button view-control" onClick={onFit}><RotateCcw size={15}/>{t('重置视图')}</button>
   <button type="button" className="text-button view-control" aria-pressed={expanded} onClick={()=>void toggle()}>{expanded?<Minimize size={15}/>:<Maximize size={15}/>} {t(expanded?'退出全屏':'全屏')}</button>
  </div></div>{children}
 </section>;
}
