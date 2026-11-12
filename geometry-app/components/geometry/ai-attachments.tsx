'use client';
import {useRef,useState} from 'react';
import {Paperclip,X,FileText} from 'lucide-react';
import {readAiFiles,type AiAttachment} from '@/lib/ai-files';
import {useT} from '@/lib/i18n';
export function AiAttachments({files,onChange,onReadingChange,disabled=false,label}:{files:AiAttachment[];onChange:(files:AiAttachment[])=>void;onReadingChange?:(reading:boolean)=>void;disabled?:boolean;label?:string}){
 const t=useT(),input=useRef<HTMLInputElement>(null),[reading,setReading]=useState(''),[error,setError]=useState('');
 async function add(list:FileList|null){if(!list?.length||disabled||reading)return;setError('');onReadingChange?.(true);try{const next=await readAiFiles(Array.from(list),setReading);const all=[...files,...next];if(all.reduce((sum,f)=>sum+f.dataUrl.length+(f.text?.length||0),0)>45*1024*1024)throw new Error('附件超过单次请求容量，请分批发送。');onChange(all)}catch(e){setError((e as Error).message)}finally{setReading('');onReadingChange?.(false);if(input.current)input.current.value=''}}
 return <div className="ai-attachments"><input ref={input} type="file" multiple accept="image/png,image/jpeg,image/webp,image/gif,application/pdf,.txt,.md" className="visually-hidden" aria-label={t('上传图片或文件')} onChange={e=>void add(e.target.files)} disabled={disabled||!!reading}/><button type="button" className="text-button" disabled={disabled||!!reading} onClick={()=>input.current?.click()}><Paperclip size={15}/>{t(label||'上传图片／文件')}</button>{reading&&<span role="status">{t('正在读取：')}{reading}</span>}
  {!!files.length&&<div className="attachment-list">{files.map(file=><div className="attachment-preview" key={file.id}>{file.dataUrl?<img src={file.dataUrl} alt={file.name}/>:<FileText size={25}/>}<span>{file.name}</span><button type="button" className="icon-button" aria-label={t('移除附件')+' '+file.name} disabled={disabled||!!reading} onClick={()=>onChange(files.filter(f=>f.id!==file.id))}><X size={14}/></button></div>)}</div>}{error&&<p className="attachment-error" role="alert">{t(error)}</p>}
 </div>;
}
