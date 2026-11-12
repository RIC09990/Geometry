import type {AiImage} from './ai-files';
import type {ChatContextMessage} from './chat-context';
import {api} from './geometry';

export type PdfGrading={score:number|null;maximum:number|null;basis:string;items:{label:string;verdict:'correct'|'incorrect'|'partial'|'unclear';feedback:string;studentWork?:string;correction?:string;location?:{imageIndex:number;x:number;y:number}|null}[]};
export type PdfFile={name:string;dataUrl:string};
export type PdfExportInput={content:string;language:'zh'|'en';images?:AiImage[];grading?:PdfGrading|null};

/** A report is bound to this submission, not the latest image in history. */
export function exportImagesForContext(context:readonly ChatContextMessage[]):AiImage[]{
 const latest=context.at(-1),source=latest?.role==='user'?latest.images||[]:[];
 return source.map(({name,dataUrl})=>({name,dataUrl}));
}

export type PdfFeedback={mode?:'solution'|'homework'|'conversation';pdfEligible?:boolean;grading?:PdfGrading|null;reportPdf?:PdfFile;exportImages?:AiImage[]};
export function canExportFeedback(reply:PdfFeedback){return reply.mode==='homework'&&reply.pdfEligible===true&&!!reply.grading?.items.length;}
export function feedbackPdfOptions(reply:PdfFeedback){return canExportFeedback(reply)&&!reply.reportPdf?{images:reply.exportImages,grading:reply.grading}:undefined;}

export async function exportAnswerPdf(input:PdfExportInput,signal?:AbortSignal):Promise<PdfFile>{
 const {reportPdf}=await api<{reportPdf:PdfFile}>('ai/export-pdf',input,signal);
 if(!reportPdf||typeof reportPdf.name!=='string'||!reportPdf.dataUrl?.startsWith('data:application/pdf;base64,JVBERi0'))throw new Error('PDF 文件生成失败，请重试。');
 return reportPdf;
}
