'use client';
import {Download,Check,X,CircleHelp,Minus} from 'lucide-react';
import {useT} from '@/lib/i18n';
import {canExportFeedback,type PdfFeedback} from '@/lib/pdf-export';
export type HomeworkFeedback=PdfFeedback&{reportError?:string};
export function feedbackBody(content:string,reply:HomeworkFeedback){return reply.grading?content.replace(/^\s*(?:\*\*)?(?:作业得分|Homework score)[^\n]*\n*/i,''):content;}
export function HomeworkReport({reply}:{reply:HomeworkFeedback}){
 const t=useT(),eligible=canExportFeedback(reply);if(!eligible)return null;
 return <div className="homework-feedback"><div className="homework-score">{reply.grading&&<strong>{reply.grading.score===null?t('批改结果'):t('作业得分')+'：'+reply.grading.score+' / '+reply.grading.maximum}</strong>}{reply.reportPdf&&<a className="button secondary" href={reply.reportPdf.dataUrl} download={reply.reportPdf.name}><Download size={15}/>{t('下载批改 PDF')}</a>}</div>{reply.grading&&<div className="homework-marks">{reply.grading.items.map((item,i)=>{const Icon={correct:Check,incorrect:X,partial:Minus,unclear:CircleHelp}[item.verdict];return <span key={i} className={'homework-mark '+item.verdict} title={item.feedback}><Icon size={17}/>{item.label}</span>})}</div>}{reply.reportError&&<p role="status" className="ai-error">{t(reply.reportError)}</p>}</div>;
}
