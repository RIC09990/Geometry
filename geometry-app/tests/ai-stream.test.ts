import test from 'node:test';
import assert from 'node:assert/strict';
import {parseStreamFrame,streamChatReply,type AiStreamEvent} from '../lib/ai-stream';
import type {ChatReply} from '../lib/ai-chat-session';

const reply:ChatReply={mode:'solution',pdfEligible:false,grading:null,content:'结论',finishReason:'stop',
 metrics:{promptTokens:1200,cachedTokens:600,completionTokens:30,tokensPerSecond:12.5}};

function respondWith(chunks:string[],status=200){
 const body=new ReadableStream<Uint8Array>({start(controller){
  for(const chunk of chunks)controller.enqueue(new TextEncoder().encode(chunk));
  controller.close();
 }});
 return new Response(body,{status,headers:{'Content-Type':status===200?'text/event-stream':'application/json'}});
}

async function collect(chunks:string[],status=200){
 const events:AiStreamEvent[]=[],priorFetch=globalThis.fetch;
 globalThis.fetch=async()=>respondWith(chunks,status);
 try{const value=await streamChatReply({},new AbortController().signal,undefined,event=>events.push(event));return {events,value}}
 finally{globalThis.fetch=priorFetch}
}

test('SSE frames decode into typed stream events',()=>{
 assert.deepEqual(parseStreamFrame('event: reasoning\ndata: {"text":"想"}'),{type:'reasoning',text:'想'});
 assert.deepEqual(parseStreamFrame('event: text\r\ndata: {"text":"答"}'),{type:'text',text:'答'});
 assert.deepEqual(parseStreamFrame('event: status\ndata: {"code":"searching"}'),{type:'status',code:'searching'});
 assert.deepEqual(parseStreamFrame('event: reset\ndata: {}'),{type:'reset'});
 assert.deepEqual(parseStreamFrame('event: error\ndata: {"detail":"连接中断"}'),{type:'error',detail:'连接中断'});
 assert.deepEqual(parseStreamFrame('event: done\ndata: '+JSON.stringify(reply)),{type:'done',reply});
 assert.equal(parseStreamFrame('event: unknown\ndata: {"x":1}'),undefined);
 assert.equal(parseStreamFrame('data: not json'),undefined);
});

test('A stream split across chunks still yields one final reply',async()=>{
 const done='event: done\ndata: '+JSON.stringify(reply)+'\n\n';
 const {events,value}=await collect([
  'event: reasoning\ndata: {"text":"先',
  '想"}\n\nevent: text\ndata: {"text":"结',
  '论"}\n\n',done.slice(0,10),done.slice(10)]);
 assert.deepEqual(events.map(event=>event.type),['reasoning','text']);
 assert.equal(value.content,'结论');
 assert.equal(value.metrics?.promptTokens,1200);
});

test('An error event rejects with its readable detail',async()=>{
 await assert.rejects(collect(['event: error\ndata: {"detail":"AI 服务繁忙"}\n\n']),/AI 服务繁忙/);
});

test('A non-2xx response reports the server detail',async()=>{
 await assert.rejects(collect([JSON.stringify({detail:'API Key 无效，请检查服务商和密钥是否匹配。'})],401),/API Key 无效/);
});

test('A stream that ends without a reply is rejected instead of guessed',async()=>{
 await assert.rejects(collect(['event: text\ndata: {"text":"半句"}\n\n']),/格式不完整/);
});
