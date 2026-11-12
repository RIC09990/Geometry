'use client';
import 'katex/dist/katex.min.css';
import {useState,type CSSProperties} from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import {Copy,Check} from 'lucide-react';
import {mathMarkdown} from '@/lib/math-markdown';
import {useT} from '@/lib/i18n';
import {ExportPdfButton,type PdfExportOptions} from './export-pdf-button';
export function AiResponse({content,showCopy=true,style,exportPdf}:{content:string;showCopy?:boolean;style?:CSSProperties;exportPdf?:PdfExportOptions}){
 const t=useT(),[copied,setCopied]=useState(false);
 async function copy(){try{await navigator.clipboard.writeText(content);setCopied(true)}catch{setCopied(false)}}
 return <><div className="ai-markdown" style={style}><Markdown remarkPlugins={[remarkGfm,remarkMath]} rehypePlugins={[[rehypeKatex,{throwOnError:false,trust:false,maxExpand:1000,maxSize:20}]]} components={{a:({children,...props})=><a {...props} target="_blank" rel="noopener noreferrer">{children}</a>}}>{mathMarkdown(content)}</Markdown></div>{showCopy&&<button className="text-button ai-copy" onClick={()=>void copy()}>{copied?<Check size={13}/>:<Copy size={13}/>} {t(copied?'已复制':'复制回复')}</button>}{exportPdf&&<ExportPdfButton content={content} {...exportPdf}/>}</>;
}
