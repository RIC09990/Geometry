import {api} from './geometry';
import {buildChatContext,recentTurnStart,type ChatSummary} from './chat-context';
import {compactConversation} from './ai-compact';
import {attachmentImages,attachmentText,type AiAttachment,type AiImage} from './ai-files';
import {exportImagesForContext,type PdfFeedback} from './pdf-export';
import type {AiProvider} from './ai-providers';
import {streamChatReply,type AiStreamEmitter} from './ai-stream';
import type {AiUsage} from './ai-usage';

export type ChatReply=PdfFeedback&{content:string;finishReason?:string;sources?:{title:string;url:string}[];searchStatus?:string|null;reportError?:string;metrics?:AiUsage};
export type ChatMessage=ChatReply&{id:string;role:'user'|'assistant';images?:AiImage[];reasoning?:string;streaming?:boolean;elapsedMs?:number;usage?:AiUsage};
export type ChatSessionState={messages:ChatMessage[];draft:string;files:AiAttachment[];readingFiles:boolean;webSearch:boolean;busy:boolean;error:string;unread:boolean;streamStatus?:string;lastUsage?:AiUsage;conversationId:string;summary?:ChatSummary};
type SendOptions={language:'zh'|'en';keyMode:'disabled'|'server'|'personal';provider?:AiProvider;headers?:Record<string,string>;emptyPrompt:string};
type Transport=(body:Record<string,unknown>,signal:AbortSignal,headers?:Record<string,string>,emit?:AiStreamEmitter)=>Promise<ChatReply>;
const initialState=():ChatSessionState=>({messages:[],draft:'',files:[],readingFiles:false,webSearch:false,busy:false,error:'',unread:false,conversationId:crypto.randomUUID()});
const streamTransport:Transport=(body,signal,headers,emit)=>streamChatReply(body,signal,headers,emit??(()=>{}));
const requestTransport:Transport=(body,signal,headers)=>api<ChatReply>('ai/chat',body,signal,headers);
type CompactTransport=(body:{messages:{role:'user'|'assistant';content:string}[];language:'zh'|'en';keyMode:'personal'|'server';provider?:AiProvider},signal:AbortSignal,headers?:Record<string,string>)=>Promise<string>;
const COMPACT_TOKENS=24000,COMPACT_RECENT_TURNS=4;

/** One in-memory session per root provider. Route subscribers do not own its request. */
export function createAiChatSession(transport:Transport=streamTransport,fallback:Transport|undefined=transport===streamTransport?requestTransport:undefined,compact:CompactTransport=compactConversation){
 let state=initialState(),request:AbortController|undefined,visibleViews=0;
 let liveStream:{conversation:ChatMessage[];message:ChatMessage}|undefined;
 const listeners=new Set<()=>void>();
 const update=(change:Partial<ChatSessionState>|((current:ChatSessionState)=>Partial<ChatSessionState>))=>{
  state={...state,...(typeof change==='function'?change(state):change)};for(const listener of listeners)listener();
 };
 const cancel=(message='')=>{
  const pending=request;request=undefined;pending?.abort();
  const partial=liveStream;
  if(partial&&(partial.message.content||partial.message.reasoning))update({messages:[...partial.conversation,{...partial.message,streaming:false}]});
  liveStream=undefined;
  if(pending||state.busy)update({busy:false,streamStatus:undefined,...(message?{error:message}:{})});
 };
 return {
  getSnapshot:()=>state,
  getActivity:()=>state.busy?'thinking':state.unread?'ready':'',
  subscribe:(listener:()=>void)=>{listeners.add(listener);return()=>{listeners.delete(listener)}},
  update,
  show:()=>{visibleViews++;if(state.unread)update({unread:false});let shown=true;return()=>{if(shown){shown=false;visibleViews=Math.max(0,visibleViews-1)}}},
  stop:()=>cancel('已停止等待回复。'),
  credentialsChanged:()=>cancel('连接配置已改变，本次请求已停止。'),
  newConversation:()=>{cancel();update({...initialState(),webSearch:state.webSearch})},
  loadConversation:(document:{id:string;messages:ChatMessage[];lastUsage?:AiUsage;summary?:ChatSummary})=>{cancel();const webSearch=state.webSearch;update({...initialState(),conversationId:document.id,messages:document.messages,lastUsage:document.lastUsage,summary:document.summary,webSearch})},
  dispose:()=>{cancel();listeners.clear()},
  async send(options:SendOptions){
   if(state.busy||state.readingFiles||(!state.draft.trim()&&!state.files.length)||options.keyMode==='disabled')return;
   const submittedDraft=state.draft,submittedFiles=state.files,images=attachmentImages(submittedFiles),turnId=crypto.randomUUID();
   const conversation:ChatMessage[]=[...state.messages,{id:turnId,role:'user',content:(submittedDraft.trim()||options.emptyPrompt)+attachmentText(submittedFiles),...(images.length?{images}:{})}];
   const abort=new AbortController();request=abort;
   let summary=state.summary;
   const recentStart=recentTurnStart(conversation,COMPACT_RECENT_TURNS);
   if((state.lastUsage?.promptTokens??0)>=COMPACT_TOKENS&&recentStart>0){
    const earlier=[...(summary?[{role:'assistant' as const,content:'早期对话摘要：\n'+summary.text}]:[]),...conversation.slice(summary?.through??0,recentStart)];
    if(earlier.length>1){
     update({streamStatus:'compacting'});
     try{
      const text=await compact({messages:earlier.map(({role,content})=>({role,content})),language:options.language,keyMode:options.keyMode as 'personal'|'server',...(options.provider?{provider:options.provider}:{})},abort.signal,options.headers);
      summary={text,through:recentStart};
      update({summary});
     }catch{summary=state.summary}
    }
   }
   if(request!==abort)return;
   update({streamStatus:undefined});
   const context=buildChatContext(conversation,summary);
   if(JSON.stringify(context).length>47*1024*1024){update({error:'本轮附件超过接口容量，请新建对话后分批发送。'});return}
   const body={messages:context,language:options.language,webSearch:state.webSearch,keyMode:options.keyMode,sessionId:state.conversationId,...(options.provider?{provider:options.provider}:{})};
   const startedAt=Date.now(),assistantId=turnId+':answer';
   let streamed:ChatMessage={id:assistantId,role:'assistant',mode:'conversation',pdfEligible:false,grading:null,content:'',streaming:true};
   let received=false,flushTimer:ReturnType<typeof setTimeout>|undefined,lastFlush=0;
   const paint=(message:ChatMessage)=>{liveStream={conversation,message};update({messages:[...conversation,message]})};
   const flush=()=>{flushTimer=undefined;lastFlush=Date.now();paint({...streamed})};
   const schedule=()=>{const now=Date.now();if(now-lastFlush>=80)flush();else if(!flushTimer)flushTimer=setTimeout(flush,80)};
   const emit:AiStreamEmitter=event=>{
    if(request!==abort)return;
    received=true;
    if(event.type==='reasoning'){streamed={...streamed,reasoning:(streamed.reasoning||'')+event.text};liveStream={conversation,message:streamed};schedule()}
    else if(event.type==='text'){streamed={...streamed,content:streamed.content+event.text};liveStream={conversation,message:streamed};schedule()}
    else if(event.type==='status'){update({streamStatus:event.code})}
    else if(event.type==='reset'){streamed={...streamed,content:'',reasoning:''};liveStream={conversation,message:streamed};flush()}
   };
   const finish=(reply:ChatReply)=>{
    if(flushTimer){clearTimeout(flushTimer);flushTimer=undefined}
    liveStream=undefined;
    const message:ChatMessage={...reply,id:assistantId,role:'assistant',streaming:false,reasoning:streamed.reasoning,elapsedMs:Date.now()-startedAt,usage:reply.metrics,exportImages:exportImagesForContext(context)};
    update({messages:[...conversation,message],lastUsage:reply.metrics,streamStatus:undefined,
     unread:visibleViews===0,error:reply.finishReason==='length'?'本次回复达到长度上限，可以继续提问。':''});
   };
   update({messages:conversation,draft:'',files:[],busy:true,error:'',unread:false,streamStatus:undefined});
   try{
    const reply=await transport(body,abort.signal,options.headers,emit);
    if(request!==abort||abort.signal.aborted)return;
    finish(reply);
   }catch(error){
    if(request!==abort||abort.signal.aborted)return;
    let failure=error as Error;
    if(!received&&fallback){
     try{const reply=await fallback(body,abort.signal,options.headers);if(request!==abort||abort.signal.aborted)return;finish(reply);return}
     catch(fallbackError){failure=fallbackError as Error}
    }
    if(flushTimer){clearTimeout(flushTimer);flushTimer=undefined}
    if(received&&(streamed.content||streamed.reasoning)){
     paint({...streamed,streaming:false});
     update({error:failure.message,unread:visibleViews===0});
    }else{
     update(current=>({error:failure.message,draft:current.draft||submittedDraft,
      files:[...submittedFiles,...current.files.filter(file=>!submittedFiles.some(sent=>sent.id===file.id))],messages:conversation.slice(0,-1),unread:visibleViews===0}));
    }
   }finally{
    if(flushTimer){clearTimeout(flushTimer);flushTimer=undefined}
    liveStream=undefined;
    if(request===abort){request=undefined;update({busy:false,streamStatus:undefined})}
   }
  },
 };
}
export type AiChatSession=ReturnType<typeof createAiChatSession>;
