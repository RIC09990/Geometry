'use client';
import {useT} from '@/lib/i18n';
import {ReactNode,useEffect,useRef} from 'react';
import {X} from 'lucide-react';
export function Modal({title,children,onClose,wide=false}:{title:string;children:ReactNode;onClose:()=>void;wide?:boolean}){
 const t=useT();
 const ref=useRef<HTMLDialogElement>(null);useEffect(()=>{ref.current?.showModal()},[]);
 return <dialog ref={ref} className={'modal '+(wide?'wide':'')} onCancel={onClose} onClick={e=>{if(e.target===ref.current)onClose()}}><header><h2>{t(title)}</h2><button className="icon-button" onClick={onClose} aria-label={t("关闭")}><X size={22}/></button></header>{t(children)}</dialog>;
}
