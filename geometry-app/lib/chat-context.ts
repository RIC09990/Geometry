import type {AiImage} from './ai-files';

export type ChatContextMessage={role:'user'|'assistant';content:string;images?:AiImage[]};
export type ChatSummary={text:string;through:number};

/** Send every retained turn. Length is bounded by compaction, never by dropping turns. */
export function buildChatContext(messages:readonly ChatContextMessage[],summary?:ChatSummary):ChatContextMessage[]{
 if(!messages.length)return [];
 if(messages[messages.length-1].role!=='user')throw new Error('The current request must be a user message');
 const first=messages.findIndex(message=>message.role==='user');
 const start=summary?Math.min(Math.max(summary.through,first),messages.length-1):first;
 const selected=messages.slice(start).map(message=>({role:message.role,content:message.content,
  ...(message.role==='user'&&message.images?.length?{images:message.images.map(({name,dataUrl})=>({name,dataUrl}))}:{})}));
 return summary?[{role:'assistant',content:'早期对话摘要：\n'+summary.text},...selected]:selected;
}

/** Rough prompt size when the provider reports no usage: half a token per
 * character plus a fixed cost per image. */
export function contextTokens(messages:readonly ChatContextMessage[]){
 let tokens=0;
 for(const message of messages)tokens+=Array.from(message.content).length*.5+(message.images?.length??0)*1100;
 return Math.round(tokens);
}

/** Index that starts the newest complete turns; 0 when there are no more turns to compact. */
export function recentTurnStart(messages:readonly ChatContextMessage[],turns:number):number{
 let seen=0;
 for(let i=messages.length-1;i>=0;i--){
  if(messages[i].role!=='user')continue;
  seen++;
  if(seen===turns)return i;
 }
 return 0;
}

/** Index of the current request, used when fewer turns exist than compaction keeps. */
export function lastUserIndex(messages:readonly ChatContextMessage[]):number{
 for(let i=messages.length-1;i>=0;i--)if(messages[i].role==='user')return i;
 return 0;
}
