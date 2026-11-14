import type {ChatReply} from './ai-chat-session';

export type AiStreamEvent=
 |{type:'reasoning';text:string}
 |{type:'text';text:string}
 |{type:'status';code:string}
 |{type:'reset'}
 |{type:'done';reply:ChatReply}
 |{type:'error';detail:string};
export type AiStreamEmitter=(event:AiStreamEvent)=>void;

type RawFrame={kind:string;payload:Record<string,unknown>};
function frameEvent(frame:string):RawFrame|undefined{
 const data:string[]=[];let kind='';
 for(const line of frame.split(/\r?\n/)){
  if(!line||line.startsWith(':'))continue;
  const index=line.indexOf(':'),field=index<0?line:line.slice(0,index);
  const value=index<0?'':line.slice(index+1).replace(/^ /,'');
  if(field==='event')kind=value;else if(field==='data')data.push(value);
 }
 if(!data.length)return;
 let parsed:unknown;
 try{parsed=JSON.parse(data.join('\n'))}catch{return}
 if(!parsed||typeof parsed!=='object')return;
 return {kind,payload:parsed as Record<string,unknown>};
}
function visibleEvent({kind,payload}:RawFrame):AiStreamEvent|undefined{
 if(kind==='reasoning'&&typeof payload.text==='string')return {type:'reasoning',text:payload.text};
 if(kind==='text'&&typeof payload.text==='string')return {type:'text',text:payload.text};
 if(kind==='status'&&typeof payload.code==='string')return {type:'status',code:payload.code};
 if(kind==='reset')return {type:'reset'};
 return;
}

/** Decode one server-sent event frame; unknown or malformed frames are ignored. */
export function parseStreamFrame(frame:string):AiStreamEvent|undefined{
 const raw=frameEvent(frame);
 if(!raw)return;
 const event=visibleEvent(raw);
 if(event)return event;
 if(raw.kind==='done'&&typeof raw.payload.content==='string')return {type:'done',reply:raw.payload as unknown as ChatReply};
 if(raw.kind==='error')return {type:'error',detail:typeof raw.payload.detail==='string'?raw.payload.detail:'AI 服务暂时无法处理请求，请稍后重试。'};
 return;
}

/** Stream one request that ends with a JSON payload, forwarding progress events. */
export async function streamRequest<T>(path:string,body:unknown,signal:AbortSignal,headers:Record<string,string>|undefined,emit:AiStreamEmitter,missing='AI 服务返回的内容不完整，请重试。'):Promise<T>{
 let response:Response;
 try{response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','Accept':'text/event-stream',...headers},body:JSON.stringify(body),signal})}
 catch(error){if((error as Error).name==='AbortError')throw error;throw new Error('暂时无法连接本机计算服务，请确认“启动 Geometry.cmd”窗口仍在运行。')}
 if(!response.ok||!response.body){
  let detail='';
  try{const data=await response.json() as {detail?:unknown};detail=typeof data?.detail==='string'?data.detail:''}catch{}
  throw new Error(detail||'计算服务暂不可用，请检查服务是否启动。');
 }
 const reader=response.body.getReader(),decoder=new TextDecoder();
 let buffer='',done:unknown,failure:Error|undefined;
 const consume=(frame:string)=>{
  const raw=frameEvent(frame);
  if(!raw)return;
  if(raw.kind==='done'){done=raw.payload;return}
  if(raw.kind==='error'){failure=new Error(typeof raw.payload.detail==='string'?raw.payload.detail:'AI 服务暂时无法处理请求，请稍后重试。');return}
  const event=visibleEvent(raw);
  if(event)emit(event);
 };
 while(!failure){
  const chunk=await reader.read();
  if(chunk.done)break;
  buffer+=decoder.decode(chunk.value,{stream:true}).replace(/\r\n/g,'\n');
  let index:number;
  while((index=buffer.indexOf('\n\n'))>=0){
   const frame=buffer.slice(0,index);buffer=buffer.slice(index+2);consume(frame);
   if(failure)break;
  }
 }
 if(failure){await reader.cancel().catch(()=>{});throw failure}
 if(buffer.trim())consume(buffer);
 if(done===undefined)throw new Error(missing);
 return done as T;
}

/** Stream one tutor turn, forwarding events until the server sends its final reply. */
export async function streamChatReply(body:unknown,signal:AbortSignal,headers:Record<string,string>|undefined,emit:AiStreamEmitter):Promise<ChatReply>{
 return streamRequest<ChatReply>('/api/ai/chat/stream',body,signal,headers,emit,'AI 服务返回的回复格式不完整，请重试。');
}
