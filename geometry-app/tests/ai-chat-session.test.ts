import test from 'node:test';
import assert from 'node:assert/strict';
import {createAiChatSession,type ChatReply} from '../lib/ai-chat-session';
import type {AiStreamEvent} from '../lib/ai-stream';

const options={language:'zh' as const,keyMode:'personal' as const,headers:{'X-AI-Api-Key':'isolated-background-key'},emptyPrompt:'请查看附件。'};
function controlled(){
 const calls:{body:Record<string,unknown>;signal:AbortSignal;resolve:(reply:ChatReply)=>void;reject:(error:Error)=>void}[]=[];
 const session=createAiChatSession((body,signal)=>new Promise((resolve,reject)=>calls.push({body,signal,resolve,reject})));
 return {session,calls};
}
const solution=(content:string):ChatReply=>({mode:'solution',pdfEligible:false,grading:null,content,finishReason:'stop'});
const grading=(content:string):ChatReply=>({mode:'homework',pdfEligible:true,content,grading:{score:null,maximum:100,basis:'检查本次作答',items:[{label:content,verdict:'incorrect',feedback:'需订正'}]},reportPdf:{name:content+'.pdf',dataUrl:'data:application/pdf;base64,JVBERi0x'}});

test('Leaving AI while thinking keeps the request alive; returning restores its single completed reply',async()=>{
 const {session,calls}=controlled();let changes=0;
 const hide=session.show(),unsubscribe=session.subscribe(()=>changes++);
 session.update({draft:'三动点加权最值，请批改我的联合取等论证。'});const pending=session.send(options);
 assert.equal(session.getActivity(),'thinking');hide();unsubscribe();const seen=changes;
 assert.equal(calls[0].signal.aborted,false,'page cleanup may detach a view, not cancel its request');
 calls[0].resolve(grading('CURRENT-THREE-POINT'));await pending;
 assert.equal(changes,seen,'unmounted page subscribers cannot receive updates');
 assert.equal(session.getSnapshot().busy,false);assert.equal(session.getSnapshot().messages.length,2);
 assert.equal(session.getActivity(),'ready');assert.equal(session.getSnapshot().messages[1].reportPdf?.name,'CURRENT-THREE-POINT.pdf');
 const hideAgain=session.show();assert.equal(session.getActivity(),'');assert.equal(calls.length,1);hideAgain();
});

test('Repeated page switches during one request do not restart it or erase the pending conversation',async()=>{
 const {session,calls}=controlled();session.update({draft:'检查复杂动点约束'});const pending=session.send(options);
 for(let i=0;i<12;i++){
  const hide=session.show(),unsubscribe=session.subscribe(()=>{});
  assert.equal(session.getSnapshot().busy,true);assert.equal(session.getSnapshot().messages[0].content,'检查复杂动点约束');
  await session.send(options);unsubscribe();hide();
 }
 assert.equal(calls.length,1);assert.equal(calls[0].signal.aborted,false);
 calls[0].resolve(solution('约束分析完成'));await pending;assert.equal(session.getSnapshot().messages.length,2);
});

test('Stopping then starting a new request cannot let the old response overwrite the current result',async()=>{
 const {session,calls}=controlled();session.update({draft:'第一份作业'});const old=session.send(options);
 session.stop();assert.equal(calls[0].signal.aborted,true);assert.match(session.getSnapshot().error,/已停止/);
 session.update({draft:'本次的新题'});const latest=session.send(options);
 calls[0].resolve(grading('OLD-WORK'));await old;
 assert.equal(session.getSnapshot().busy,true);assert.equal(session.getSnapshot().messages.some(m=>m.content==='OLD-WORK'),false);
 calls[1].resolve(solution('CURRENT-SOLUTION'));await latest;
 const answer=session.getSnapshot().messages.at(-1)!;assert.equal(answer.content,'CURRENT-SOLUTION');assert.equal(answer.reportPdf,undefined);
});

for(const action of ['credentialsChanged','newConversation','dispose'] as const)test(`${action} explicitly cancels a background request and rejects its late reply`,async()=>{
 const {session,calls}=controlled();session.update({draft:'待处理作答'});const pending=session.send(options);
 session[action]();assert.equal(calls[0].signal.aborted,true);calls[0].resolve(grading('LATE-OLD-REPORT'));await pending;
 assert.equal(session.getSnapshot().busy,false);assert.equal(session.getSnapshot().messages.some(m=>m.reportPdf?.name==='LATE-OLD-REPORT.pdf'),false);
 if(action==='newConversation')assert.deepEqual(session.getSnapshot().messages,[]);
});

test('Each conversation keeps one session id and a new conversation starts another',async()=>{
 const {session,calls}=controlled();
 session.update({draft:'第一问'});const first=session.send(options);calls[0].resolve(solution('答一'));await first;
 session.update({draft:'第二问'});const second=session.send(options);calls[1].resolve(solution('答二'));await second;
 const id=calls[0].body.sessionId as string;
 assert.match(id,/^[0-9a-f-]{36}$/);
 assert.equal(calls[1].body.sessionId,id);
 session.newConversation();session.update({draft:'新对话'});
 const third=session.send(options);calls[2].resolve(solution('答三'));await third;
 assert.match(calls[2].body.sessionId as string,/^[0-9a-f-]{36}$/);
 assert.notEqual(calls[2].body.sessionId,id);
});

test('A failure received off-page preserves the retry text, attachments and visible error',async()=>{
 const {session,calls}=controlled();const files=[{id:'work-page',name:'work.png',dataUrl:'data:image/png;base64,synthetic'}];
 session.update({draft:'批改这份作业',files,webSearch:true});const pending=session.send(options);
 calls[0].reject(new Error('模型连接暂时不可用'));await pending;
 const state=session.getSnapshot();assert.equal(state.draft,'批改这份作业');assert.deepEqual(state.files,files);
 assert.equal(state.messages.length,0);assert.equal(state.busy,false);assert.match(state.error,/模型连接暂时不可用/);
 assert.equal(state.unread,true);assert.equal(state.webSearch,true);session.show();assert.equal(session.getSnapshot().unread,false);
});

test('Navigation preserves an unsent draft and uploads without starting a model request',()=>{
 const {session,calls}=controlled(),files=[{id:'text',name:'notes.md',dataUrl:'',text:'推理草稿'}];
 session.update({draft:'尚未发送的证明',files,webSearch:true});const hide=session.show();hide();session.show();
 assert.equal(session.getSnapshot().draft,'尚未发送的证明');assert.deepEqual(session.getSnapshot().files,files);
 assert.equal(session.getSnapshot().webSearch,true);assert.equal(calls.length,0);
});

test('A later text grading cannot reuse a previous report’s images after off-page completion',async()=>{
 const {session,calls}=controlled();session.update({draft:'原图批改',files:[{id:'old',name:'old.png',dataUrl:'data:image/png;base64,old'}]});
 const first=session.send(options);calls[0].resolve(grading('OLD-REPORT'));await first;
 session.update({draft:'普通知识讲解'});const second=session.send(options);calls[1].resolve(solution('普通解答'));await second;
 session.update({draft:'本次文本作答需要订正'});const third=session.send(options);calls[2].resolve(grading('NEW-REPORT'));await third;
 const messages=session.getSnapshot().messages;
 assert.deepEqual(messages.at(-1)?.exportImages,[]);assert.equal(messages.at(-1)?.reportPdf?.name,'NEW-REPORT.pdf');
 assert.equal(messages[3].reportPdf,undefined);assert.equal(messages[1].exportImages?.[0].name,'old.png');
 const context=calls[2].body.messages as Record<string,unknown>[];
 assert.equal(context.some(m=>'reportPdf' in m||'grading' in m||'id' in m),false);
});

test('Root sessions are isolated and never copy credentials into observable conversation state',async()=>{
 const first=controlled(),second=controlled();first.session.update({draft:'仅第一会话'});const pending=first.session.send(options);
 assert.equal(second.session.getSnapshot().messages.length,0);assert.equal(second.session.getSnapshot().busy,false);
 assert.equal(JSON.stringify(first.session.getSnapshot()).includes('isolated-background-key'),false);
 first.calls[0].resolve(solution('完成'));await pending;
 assert.equal(new Set(first.session.getSnapshot().messages.map(m=>m.id)).size,2);
});

function streaming(){
 const calls:{body:Record<string,unknown>;emit:(event:AiStreamEvent)=>void;resolve:(reply:ChatReply)=>void;reject:(error:Error)=>void}[]=[];
 const session=createAiChatSession((body,signal,headers,emit)=>new Promise((resolve,reject)=>calls.push({body,emit:emit!,resolve,reject})));
 return {session,calls};
}
const streamedReply:ChatReply={mode:'solution',pdfEligible:false,grading:null,content:'结论',finishReason:'stop',
 metrics:{promptTokens:1200,cachedTokens:600,completionTokens:30,tokensPerSecond:12.5}};

test('Streaming builds one assistant turn with reasoning, usage and elapsed time',async()=>{
 const {session,calls}=streaming();session.update({draft:'请解释'});const pending=session.send(options);
 calls[0].emit({type:'reasoning',text:'先想'});
 calls[0].emit({type:'text',text:'结论'});
 calls[0].resolve(streamedReply);await pending;
 const state=session.getSnapshot(),answer=state.messages.at(-1)!;
 assert.equal(state.messages.length,2);
 assert.equal(answer.content,'结论');assert.equal(answer.reasoning,'先想');assert.equal(answer.streaming,false);
 assert.equal(typeof answer.elapsedMs,'number');
 assert.deepEqual(state.lastUsage,streamedReply.metrics);
 assert.equal(state.busy,false);
});

test('A failure after partial output keeps the shown text and reports the error',async()=>{
 const {session,calls}=streaming();session.update({draft:'请解释'});const pending=session.send(options);
 calls[0].emit({type:'text',text:'半句'});
 calls[0].reject(new Error('连接中断'));await pending;
 const state=session.getSnapshot(),answer=state.messages.at(-1)!;
 assert.equal(state.messages.length,2);assert.equal(answer.content,'半句');assert.equal(answer.streaming,false);
 assert.match(state.error,/连接中断/);assert.equal(state.busy,false);
});

test('Stopping mid-stream keeps what was already shown',async()=>{
 const {session,calls}=streaming();session.update({draft:'请解释'});void session.send(options);
 calls[0].emit({type:'text',text:'半句'});session.stop();
 const state=session.getSnapshot(),answer=state.messages.at(-1)!;
 assert.equal(state.messages.length,2);assert.equal(answer.content,'半句');assert.equal(answer.streaming,false);
 assert.match(state.error,/已停止/);
});

test('A stream that fails before its first event falls back to the plain request',async()=>{
 const fallback:Record<string,unknown>[]=[];
 const session=createAiChatSession(
  ()=>Promise.reject(new Error('流式不可用')),
  body=>{fallback.push(body);return Promise.resolve(streamedReply)});
 session.update({draft:'请解释'});await session.send(options);
 assert.equal(fallback.length,1);
 assert.equal(session.getSnapshot().messages.at(-1)?.content,'结论');
});
test('Early turns are summarized once the previous prompt exceeds the budget',async()=>{
 const bodies:Record<string,unknown>[]=[],compactions:{messages:{role:string;content:string}[]}[]=[];
 const reply:ChatReply={mode:'conversation',pdfEligible:false,grading:null,content:'答',finishReason:'stop',metrics:{promptTokens:30000}};
 const session=createAiChatSession(
  body=>{bodies.push(body);return Promise.resolve(reply)},
  undefined,
  async body=>{compactions.push(body);return '摘要文本'});
 for(let i=0;i<5;i++){session.update({draft:'问题'+i});await session.send(options)}
 assert.equal(compactions.length,1);
 assert.deepEqual(session.getSnapshot().summary,{text:'摘要文本',through:2});
 const messages=bodies.at(-1)?.messages as {role:string;content:string}[];
 assert.equal(messages[0].role,'assistant');
 assert.match(messages[0].content,/早期对话摘要/);
 assert.equal(messages.length,8);
});
