import type {ChatReply} from './ai-chat-session';

export type AiStreamEvent=
 |{type:'reasoning';text:string}
 |{type:'text';text:string}
 |{type:'status';code:string}
 |{type:'reset'}
 |{type:'done';reply:ChatReply}
 |{type:'error';detail:string};
export type AiStreamEmitter=(event:AiStreamEvent)=>void;

/** Decode one server-sent event frame; unknown or malformed frames are ignored. */
export function parseStreamFrame(frame:string):AiStreamEvent|undefined{
 const data:string[]=[];let event='';
 for(const line of frame.split(/\r?\n/)){
  if(!line||line.startsWith(':'))continue;
  const index=line.indexOf(':'),field=index<0?line:line.slice(0,index);
  const value=index<0?'':line.slice(index+1).replace(/^ /,'');
  if(field==='event')event=value;else if(field==='data')data.push(value);
 }
 if(!data.length)return;
 let parsed:unknown;
 try{parsed=JSON.parse(data.join('\n'))}catch{return}
 if(!parsed||typeof parsed!=='object')return;
 const payload=parsed as Record<string,unknown>;
 if(event==='reasoning'&&typeof payload.text==='string')return {type:'reasoning',text:payload.text};
 if(event==='text'&&typeof payload.text==='string')return {type:'text',text:payload.text};
 if(event==='status'&&typeof payload.code==='string')return {type:'status',code:payload.code};
 if(event==='reset')return {type:'reset'};
 if(event==='done'&&typeof payload.content==='string')return {type:'done',reply:payload as unknown as ChatReply};
 if(event==='error')return {type:'error',detail:typeof payload.detail==='string'?payload.detail:'AI 服务暂时无法处理请求，请稍后重试。'};
 return;
}

/** Stream one tutor turn, forwarding events until the server sends its final reply. */
export async function streamChatReply(body:unknown,signal:AbortSignal,headers:Record<string,string>|undefined,emit:AiStreamEmitter):Promise<ChatReply>{
 let response:Response;
 try{response=await fetch('/api/ai/chat/stream',{method:'POST',headers:{'Content-Type':'application/json','Accept':'text/event-stream',...headers},body:JSON.stringify(body),signal})}
 catch(error){if((error as Error).name==='AbortError')throw error;throw new Error('暂时无法连接本机计算服务，请确认“启动 Geometry.cmd”窗口仍在运行。')}
 if(!response.ok||!response.body){
  let detail='';
  try{const data=await response.json() as {detail?:unknown};detail=typeof data?.detail==='string'?data.detail:''}catch{}
  throw new Error(detail||'计算服务暂不可用，请检查服务是否启动。');
 }
 const reader=response.body.getReader(),decoder=new TextDecoder();
 let buffer='',reply:ChatReply|undefined,failure:Error|undefined;
 const dispatch=(frame:string)=>{
  const event=parseStreamFrame(frame);
  if(!event)return;
  if(event.type==='done'){reply=event.reply;return}
  if(event.type==='error'){failure=new Error(event.detail);return}
  emit(event);
 };
 while(!failure){
  const {done,value}=await reader.read();
  if(done)break;
  buffer+=decoder.decode(value,{stream:true}).replace(/\r\n/g,'\n');
  let index:number;
  while((index=buffer.indexOf('\n\n'))>=0){
   const frame=buffer.slice(0,index);buffer=buffer.slice(index+2);dispatch(frame);
   if(failure)break;
  }
 }
 if(failure){await reader.cancel().catch(()=>{});throw failure}
 if(buffer.trim())dispatch(buffer);
 if(!reply)throw new Error('AI 服务返回的回复格式不完整，请重试。');
 return reply;
}
