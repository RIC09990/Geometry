import type {AiImage} from './ai-files';

export type ChatContextMessage={role:'user'|'assistant';content:string;images?:AiImage[]};

const MAX_TURNS=4,MAX_MESSAGES=8,MAX_CHARACTERS=12000;

/** Keep recent complete turns without rewriting the current request or UI history. */
export function buildChatContext(messages:readonly ChatContextMessage[]):ChatContextMessage[]{
 if(!messages.length)return [];
 if(messages[messages.length-1].role!=='user')throw new Error('The current request must be a user message');
 const turns:ChatContextMessage[][]=[];
 for(const message of messages){
  if(message.role==='user')turns.push([message]);
  else if(turns.length)turns[turns.length-1].push(message);
 }
 const current=turns[turns.length-1],selected=[current];
 let count=current.length,characters=current.reduce((sum,message)=>sum+Array.from(message.content).length,0);
 for(let i=turns.length-2;i>=0&&selected.length<MAX_TURNS;i--){
  const turn=turns[i],size=turn.reduce((sum,message)=>sum+Array.from(message.content).length,0);
  // Do not bridge a discarded turn with older context, or cut through a formula.
  if(count+turn.length>MAX_MESSAGES||characters+size>MAX_CHARACTERS)break;
  selected.unshift(turn);count+=turn.length;characters+=size;
 }
 const context=selected.flat();
 let latestImages=-1;
 for(let i=context.length-1;i>=0;i--)if(context[i].role==='user'&&context[i].images?.length){latestImages=i;break}
 return context.map((message,i)=>({role:message.role,content:message.content,
  ...(i===latestImages?{images:message.images!.map(({name,dataUrl})=>({name,dataUrl}))}:{})}));
}
