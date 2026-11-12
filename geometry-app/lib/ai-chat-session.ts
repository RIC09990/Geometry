import {api} from './geometry';
import {buildChatContext} from './chat-context';
import {attachmentImages,attachmentText,type AiAttachment,type AiImage} from './ai-files';
import {exportImagesForContext,type PdfFeedback} from './pdf-export';
import type {AiProvider} from './ai-providers';

export type ChatReply=PdfFeedback&{content:string;finishReason?:string;sources?:{title:string;url:string}[];searchStatus?:string|null;reportError?:string};
export type ChatMessage=ChatReply&{id:string;role:'user'|'assistant';images?:AiImage[]};
export type ChatSessionState={messages:ChatMessage[];draft:string;files:AiAttachment[];readingFiles:boolean;webSearch:boolean;busy:boolean;error:string;unread:boolean};
type SendOptions={language:'zh'|'en';keyMode:'disabled'|'server'|'personal';provider?:AiProvider;headers?:Record<string,string>;emptyPrompt:string};
type Transport=(body:Record<string,unknown>,signal:AbortSignal,headers?:Record<string,string>)=>Promise<ChatReply>;
const initialState=():ChatSessionState=>({messages:[],draft:'',files:[],readingFiles:false,webSearch:false,busy:false,error:'',unread:false});

/** One in-memory session per root provider. Route subscribers do not own its request. */
export function createAiChatSession(transport:Transport=(body,signal,headers)=>api<ChatReply>('ai/chat',body,signal,headers)){
 let state=initialState(),request:AbortController|undefined,visibleViews=0;
 const listeners=new Set<()=>void>();
 const update=(change:Partial<ChatSessionState>|((current:ChatSessionState)=>Partial<ChatSessionState>))=>{
  state={...state,...(typeof change==='function'?change(state):change)};for(const listener of listeners)listener();
 };
 const cancel=(message='')=>{const pending=request;request=undefined;pending?.abort();if(pending||state.busy)update({busy:false,...(message?{error:message}:{})})};
 return {
  getSnapshot:()=>state,
  getActivity:()=>state.busy?'thinking':state.unread?'ready':'',
  subscribe:(listener:()=>void)=>{listeners.add(listener);return()=>{listeners.delete(listener)}},
  update,
  show:()=>{visibleViews++;if(state.unread)update({unread:false});let shown=true;return()=>{if(shown){shown=false;visibleViews=Math.max(0,visibleViews-1)}}},
  stop:()=>cancel('已停止等待回复。'),
  credentialsChanged:()=>cancel('连接配置已改变，本次请求已停止。'),
  newConversation:()=>{cancel();update({...initialState(),webSearch:state.webSearch})},
  dispose:()=>{cancel();listeners.clear()},
  async send(options:SendOptions){
   if(state.busy||state.readingFiles||(!state.draft.trim()&&!state.files.length)||options.keyMode==='disabled')return;
   const submittedDraft=state.draft,submittedFiles=state.files,images=attachmentImages(submittedFiles),turnId=crypto.randomUUID();
   const conversation:ChatMessage[]=[...state.messages,{id:turnId,role:'user',content:(submittedDraft.trim()||options.emptyPrompt)+attachmentText(submittedFiles),...(images.length?{images}:{})}];
   const context=buildChatContext(conversation);
   if(JSON.stringify(context).length>47*1024*1024){update({error:'本轮附件超过接口容量，请新建对话后分批发送。'});return}
   const abort=new AbortController();request=abort;
   const body={messages:context,language:options.language,webSearch:state.webSearch,keyMode:options.keyMode,...(options.provider?{provider:options.provider}:{})};
   update({messages:conversation,draft:'',files:[],busy:true,error:'',unread:false});
   try{
    const reply=await transport(body,abort.signal,options.headers);
    if(request!==abort||abort.signal.aborted)return;
    update({messages:[...conversation,{...reply,id:turnId+':answer',role:'assistant',exportImages:exportImagesForContext(context)}],
     unread:visibleViews===0,error:reply.finishReason==='length'?'本次回复达到长度上限，可以继续提问。':''});
   }catch(error){
    if(request!==abort||abort.signal.aborted)return;
    update(current=>({error:(error as Error).message,draft:current.draft||submittedDraft,
     files:[...submittedFiles,...current.files.filter(file=>!submittedFiles.some(sent=>sent.id===file.id))],messages:conversation.slice(0,-1),unread:visibleViews===0}));
   }finally{if(request===abort){request=undefined;update({busy:false})}}
  },
 };
}
export type AiChatSession=ReturnType<typeof createAiChatSession>;
