import type {AiImage} from './ai-files';

export type ChatContextMessage={role:'user'|'assistant';content:string;images?:AiImage[]};
export type ChatSummary={text:string;through:number};

const KEEP_TURNS=12,KEEP_MESSAGES=24,KEEP_CHARACTERS=24000;
const TRIM_TURNS=6,TRIM_MESSAGES=12,TRIM_CHARACTERS=12000;

/** Keep recent complete turns without rewriting the current request or UI history. */
export function buildChatContext(messages:readonly ChatContextMessage[],summary?:ChatSummary):ChatContextMessage[]{
 if(!messages.length)return [];
 if(messages[messages.length-1].role!=='user')throw new Error('The current request must be a user message');
 const start=summary?Math.min(Math.max(summary.through,0),messages.length-1):0;
 const selected=select(messages.slice(start));
 return summary?[{role:'assistant',content:'早期对话摘要：\n'+summary.text},...selected]:selected;
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

function select(messages:readonly ChatContextMessage[]):ChatContextMessage[]{
 const turns:ChatContextMessage[][]=[];
 for(const message of messages){
  if(message.role==='user')turns.push([message]);
  else if(turns.length)turns[turns.length-1].push(message);
 }
 const all=turns.flat();
 if(turns.length<=KEEP_TURNS&&all.length<=KEEP_MESSAGES&&characters(all)<=KEEP_CHARACTERS)return copy(all);
 const selected=[turns[turns.length-1]];
 let count=selected[0].length,size=characters(selected[0]);
 for(let i=turns.length-2;i>=0;i--){
  const turn=turns[i],turnSize=characters(turn);
  // Do not bridge a discarded turn with older context, or cut through a formula.
  if(selected.length>=TRIM_TURNS||count+turn.length>TRIM_MESSAGES||size+turnSize>TRIM_CHARACTERS)break;
  selected.unshift(turn);count+=turn.length;size+=turnSize;
 }
 return copy(selected.flat());
}

function characters(messages:readonly ChatContextMessage[]){
 return messages.reduce((sum,message)=>sum+Array.from(message.content).length,0);
}

function copy(messages:readonly ChatContextMessage[]):ChatContextMessage[]{
 return messages.map(message=>({role:message.role,content:message.content,
  ...(message.role==='user'&&message.images?.length?{images:message.images.map(({name,dataUrl})=>({name,dataUrl}))}:{})}));
}
