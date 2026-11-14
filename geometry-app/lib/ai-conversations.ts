import type {AiUsage} from './ai-usage';
import type {ChatSummary} from './chat-context';
import type {ChatMessage} from './ai-chat-session';

export type ConversationSummary={id:string;title:string;createdAt:number;updatedAt:number;messageCount:number;preview:string};
export type StoredImage={name:string;dataUrl:string};
export type ConversationMessage={role:'user'|'assistant';content:string;reasoning?:string;images?:StoredImage[];
 sources?:{title:string;url:string}[];searchStatus?:string|null;mode?:string;elapsedMs?:number;usage?:AiUsage};
export type ConversationDocument={id:string;title:string;createdAt:number;updatedAt:number;messages:ConversationMessage[];lastUsage?:AiUsage|null;summary?:ChatSummary|null};

async function request<T>(path:string,init?:RequestInit):Promise<T>{
 let response:Response;
 try{response=await fetch(path,{...init,headers:{'Content-Type':'application/json',...(init?.headers||{})}})}
 catch{throw new Error('暂时无法连接本机计算服务，请确认“启动 Geometry.cmd”窗口仍在运行。')}
 if(!response.ok){
  let detail='';
  try{const data=await response.json() as {detail?:unknown};detail=typeof data?.detail==='string'?data.detail:''}catch{}
  throw new Error(detail||'本机会话记录暂不可用，请稍后重试。');
 }
 return response.json() as Promise<T>;
}

export const listConversations=(query='')=>request<ConversationSummary[]>('/api/ai/conversations'+(query?`?q=${encodeURIComponent(query)}`:''));
export const readConversation=(id:string)=>request<ConversationDocument>(`/api/ai/conversations/${id}`);
export const saveConversation=(document:{id:string;title:string;messages:ConversationMessage[];lastUsage?:AiUsage;summary?:ChatSummary})=>
 request<ConversationSummary>('/api/ai/conversations',{method:'POST',body:JSON.stringify(document)});
export const renameConversation=(id:string,title:string)=>request<ConversationSummary>(`/api/ai/conversations/${id}`,{method:'PATCH',body:JSON.stringify({title})});
export const deleteConversation=(id:string)=>request<{deleted:boolean}>(`/api/ai/conversations/${id}`,{method:'DELETE'});

/** Project one rendered message onto the stored shape; PDF and report fields stay out. */
export function storedMessage(message:ChatMessage):ConversationMessage{
 const value:ConversationMessage={role:message.role,content:message.content};
 if(message.reasoning!==undefined)value.reasoning=message.reasoning;
 if(message.images?.length)value.images=message.images.map(({name,dataUrl})=>({name,dataUrl}));
 if(message.sources?.length)value.sources=message.sources.map(({title,url})=>({title,url}));
 if(message.searchStatus!==undefined)value.searchStatus=message.searchStatus;
 if(typeof message.mode==='string')value.mode=message.mode;
 if(typeof message.elapsedMs==='number')value.elapsedMs=message.elapsedMs;
 if(message.usage)value.usage=message.usage;
 return value;
}

export function restoredMessages(document:ConversationDocument):ChatMessage[]{
 return document.messages.map(message=>({id:crypto.randomUUID(),role:message.role,content:message.content,
  ...(message.reasoning!==undefined?{reasoning:message.reasoning}:{}),
  ...(message.images?.length?{images:message.images.map(({name,dataUrl})=>({name,dataUrl}))}:{}),
  ...(message.sources?.length?{sources:message.sources}:{}),
  ...(message.searchStatus!==undefined?{searchStatus:message.searchStatus}:{}),
  ...(typeof message.mode==='string'?{mode:message.mode as ChatMessage['mode']}:{mode:'conversation' as const}),
  ...(typeof message.elapsedMs==='number'?{elapsedMs:message.elapsedMs}:{}),
  ...(message.usage?{usage:message.usage}:{}),
  pdfEligible:false,grading:null}));
}
