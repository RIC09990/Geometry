import test from 'node:test';
import assert from 'node:assert/strict';
import {listConversations,readConversation,renameConversation,deleteConversation,saveConversation,
 storedMessage,restoredMessages,type ConversationSummary} from '../lib/ai-conversations';
import type {ChatMessage} from '../lib/ai-chat-session';

const summary:ConversationSummary={id:'11111111-1111-4111-8111-111111111111',title:'等腰三角形',
 createdAt:1,updatedAt:2,messageCount:2,preview:'等腰三角形为什么会成立？'};

function mockFetch(response:Response|(()=>Response)){
 const calls:{url:string;init:RequestInit|undefined}[]=[];
 const prior=globalThis.fetch;
 globalThis.fetch=async(url,init)=>{calls.push({url:String(url),init});return typeof response==='function'?response():response};
 return {calls,restore:()=>{globalThis.fetch=prior}};
}

test('Listing encodes the search query and returns summaries',async()=>{
 const mock=mockFetch(Response.json([summary]));
 try{
  const items=await listConversations('等腰 三角');
  assert.equal(mock.calls[0].url,'/api/ai/conversations?q='+encodeURIComponent('等腰 三角'));
  assert.deepEqual(items,[summary]);
 }finally{mock.restore()}
});

test('Saving posts the conversation document as JSON',async()=>{
 const mock=mockFetch(Response.json(summary));
 try{
  const document={id:summary.id,title:'',messages:[{role:'user' as const,content:'问题'}],lastUsage:{promptTokens:10}};
  await saveConversation(document);
  assert.equal(mock.calls[0].url,'/api/ai/conversations');
  assert.equal(mock.calls[0].init?.method,'POST');
  assert.deepEqual(JSON.parse(String(mock.calls[0].init?.body)),document);
  assert.equal((mock.calls[0].init?.headers as Record<string,string>)['Content-Type'],'application/json');
 }finally{mock.restore()}
});

test('Reading, renaming and deleting use their own verbs',async()=>{
 const mock=mockFetch(()=>Response.json({deleted:true}));
 try{
  await readConversation(summary.id);
  await renameConversation(summary.id,'新名字');
  await deleteConversation(summary.id);
  assert.deepEqual(mock.calls.map(call=>call.init?.method??'GET'),['GET','PATCH','DELETE']);
  assert.equal(mock.calls[1].url,'/api/ai/conversations/'+summary.id);
  assert.deepEqual(JSON.parse(String(mock.calls[1].init?.body)),{title:'新名字'});
 }finally{mock.restore()}
});

test('Server errors keep the readable detail',async()=>{
 const mock=mockFetch(new Response(JSON.stringify({detail:'这次对话超过本机存储上限。'}),{status:413}));
 try{await assert.rejects(saveConversation({id:summary.id,title:'',messages:[]}),/超过本机存储上限/)}
 finally{mock.restore()}
});

test('Stored messages drop PDF and report fields while keeping reasoning and usage',()=>{
 const message:ChatMessage={id:'m1',role:'assistant',content:'答案',mode:'homework',pdfEligible:true,
  grading:{score:90,maximum:100,basis:'卷面',items:[]},reportPdf:{name:'a.pdf',dataUrl:'data:application/pdf;base64,AA'},
  exportImages:[{name:'题.png',dataUrl:'data:image/png;base64,AA'}],reasoning:'先想',elapsedMs:1200,
  usage:{promptTokens:10,cachedTokens:4,completionTokens:2},sources:[{title:'来源',url:'https://example.com/a'}],
  searchStatus:'found'};
 const stored=storedMessage(message);
 assert.deepEqual(stored,{role:'assistant',content:'答案',reasoning:'先想',mode:'homework',elapsedMs:1200,
  usage:{promptTokens:10,cachedTokens:4,completionTokens:2},sources:[{title:'来源',url:'https://example.com/a'}],
  searchStatus:'found'});
});

test('Restored messages regain ids, defaults and attachments',()=>{
 const messages=restoredMessages({id:summary.id,title:'t',createdAt:1,updatedAt:2,lastUsage:null,messages:[
  {role:'user',content:'看图',images:[{name:'题.png',dataUrl:'data:image/png;base64,AA'}]},
  {role:'assistant',content:'答案',reasoning:'想',elapsedMs:900,usage:{completionTokens:3}}]});
 assert.equal(messages.length,2);
 assert.ok(messages[0].id.length>=8);
 assert.equal(messages[1].role,'assistant');
 assert.equal(messages[1].content,'答案');
 assert.equal(messages[1].reasoning,'想');
 assert.equal(messages[1].mode,'conversation');
 assert.equal(messages[1].grading,null);
 assert.equal(messages[0].images?.[0].name,'题.png');
});
