import type {ChatContextMessage} from './chat-context';
import type {AiProvider} from './ai-providers';

export type CompactBody={messages:ChatContextMessage[];language:'zh'|'en';keyMode:'personal'|'server';provider?:AiProvider};

/** Ask the provider to summarize early turns once; the caller persists the text. */
export async function compactConversation(body:CompactBody,signal:AbortSignal,headers?:Record<string,string>):Promise<string>{
 let response:Response;
 try{response=await fetch('/api/ai/compact',{method:'POST',signal,headers:{'Content-Type':'application/json',...(headers||{})},body:JSON.stringify(body)})}
 catch{throw new Error('暂时无法连接本机计算服务，请确认“启动 Geometry.cmd”窗口仍在运行。')}
 if(!response.ok){
  let detail='';
  try{const data=await response.json() as {detail?:unknown};detail=typeof data?.detail==='string'?data.detail:''}catch{}
  throw new Error(detail||'AI 服务暂时无法压缩对话，请稍后重试。');
 }
 const data=await response.json() as {summary?:unknown};
 const summary=typeof data?.summary==='string'?data.summary.trim():'';
 if(!summary)throw new Error('AI 服务返回了空摘要，请稍后重试。');
 return summary;
}
