'use client';
import {useEffect,useRef,useState} from 'react';
import {Download} from 'lucide-react';
import {useLanguage,useT} from '@/lib/i18n';
import {exportAnswerPdf,type PdfFile,type PdfExportInput} from '@/lib/pdf-export';
import type {AiImage} from '@/lib/ai-files';

const NO_IMAGES:AiImage[]=[];
export type PdfExportOptions=Pick<PdfExportInput,'images'|'grading'>;
export function ExportPdfButton({content,images=NO_IMAGES,grading}:PdfExportOptions&{content:string}){
 const t=useT(),{language}=useLanguage();
 const [file,setFile]=useState<{pdf:PdfFile;content:string;images:AiImage[];grading:PdfExportInput['grading'];language:string}>(),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const request=useRef<AbortController|null>(null);
 useEffect(()=>{request.current?.abort();request.current=null;setFile(undefined);setError('');setBusy(false);return()=>request.current?.abort()},[content,images,grading,language]);
 async function generate(){
  if(busy||!content.trim())return;
  const controller=new AbortController();request.current=controller;setBusy(true);setError('');
  try{const pdf=await exportAnswerPdf({content,images,grading,language},controller.signal);if(request.current===controller&&!controller.signal.aborted)setFile({pdf,content,images,grading,language})}
  catch(e){if(!controller.signal.aborted)setError((e as Error).message)}
  finally{if(request.current===controller){setBusy(false);request.current=null}}
 }
 const currentFile=file&&file.content===content&&file.images===images&&file.grading===grading&&file.language===language?file.pdf:undefined;
 return <>{currentFile?<a className="text-button ai-copy" href={currentFile.dataUrl} download={currentFile.name}><Download size={13}/>{t('下载 PDF')}</a>:<button type="button" className="text-button ai-copy" disabled={busy||!content.trim()} onClick={()=>void generate()}><Download size={13}/>{t(busy?'正在生成 PDF…':'导出 PDF')}</button>}{error&&<p role="status" className="ai-error">{t(error)}</p>}</>;
}
