import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {renderToStaticMarkup} from 'react-dom/server';
import React from 'react';
import {AiResponse} from '../components/geometry/ai-response';
import {ProofView} from '../components/geometry/proof-view';
import {mathMarkdown} from '../lib/math-markdown';
import {circleGeometry} from '../lib/arc';
import {drawingObjects} from '../lib/drawing-objects';
import {POST as proxyAi} from '../app/api/[...path]/route';
import catalogue from '../data/cases.json';
import type {Problem,Proof} from '../lib/geometry';
import {cleanProblem} from '../lib/geometry';
import {deleteTopic,listTopics,migrateLocalTopics,openTopic,readTopicDocument,saveTopic} from '../lib/topics';
import {aiProviders,detectAiProvider,suggestAiModel,thinkingLevel,officialDeepSeek,type AiProvider} from '../lib/ai-providers';
const preset=(i=0)=>structuredClone(catalogue[i]) as Problem;

test('Key format detection does not guess ambiguous tokens or subscription credentials',()=>{
 assert.equal(detectAiProvider(' sk-proj-test-only-not-real '),'openai');
 assert.equal(detectAiProvider('sk-svcacct-test-only-not-real'),'openai');
 assert.equal(detectAiProvider('sk-ant-api03-test-only-not-real'),'anthropic');
 assert.equal(detectAiProvider('AIza'+'x'.repeat(35)),'gemini');
 for(const key of ['sk-ambiguous-not-real','sk-ant-oat01-not-an-api-key','AIza','garbage',''])assert.equal(detectAiProvider(key),null);
});
test('Automatic model selection excludes non-chat models and uses returned IDs only',()=>{
 const ms=(...ids:string[])=>ids.map(id=>({id,name:id}));
 assert.equal(suggestAiModel('openai',ms('gpt-image-1','gpt-4o-mini-tts','gpt-4.1-mini','gpt-5-mini','gpt-5-pro','gpt-5.1-codex')),'gpt-5-mini');
 assert.equal(suggestAiModel('anthropic',ms('claude-opus-4-6','claude-sonnet-4-6','claude-sonnet-4-5')),'claude-sonnet-4-6');
 assert.equal(suggestAiModel('gemini',ms('gemini-2.5-flash','gemini-3-flash-preview','gemini-2.5-flash-image')),'gemini-2.5-flash');
 assert.equal(suggestAiModel('openai',ms('text-embedding-3-large')),'');
 assert.equal(suggestAiModel('deepseek',ms('deepseek-flash','deepseek-v4-pro','deepseek-chat')),'deepseek-flash');
 assert.equal(suggestAiModel('deepseek',ms('deepseek-v4-pro','deepseek-chat')),'');
 assert.equal(suggestAiModel('deepseek',[]),'');
});
test('Thinking controls default to Max for official DeepSeek and stay opt-in elsewhere',()=>{
 const official:AiProvider={...aiProviders.deepseek.config,model:'user-selected-model',reasoningEffort:undefined};
 const initial=structuredClone(official);
 assert.equal(thinkingLevel(official),'max');
 assert.equal(thinkingLevel({...official,reasoningEffort:'medium'}),'high');
 assert.equal(thinkingLevel({...official,reasoningEffort:'high'}),'high');
 assert.equal(thinkingLevel({...official,reasoningEffort:'low'}),'low');
 assert.equal(thinkingLevel({...official,reasoningEffort:'max'}),'max');
 assert.equal(thinkingLevel({...official,baseUrl:'https://api.deepseek.com/v1',protocol:'responses'}),'max');
 assert.equal(thinkingLevel({...official,protocol:'anthropic'}),undefined);
 assert.deepEqual(official,initial);
 const relay:AiProvider={provider:'compatible',baseUrl:'https://relay.example.com/v1',protocol:'chat',model:'deepseek-v4.1-flash'};
 assert.equal(thinkingLevel(relay),'');
 assert.equal(thinkingLevel({...relay,reasoningEffort:'max'}),'max');
 assert.equal(thinkingLevel({...relay,reasoningEffort:'medium'}),'high');
 assert.equal(thinkingLevel({...relay,reasoningEffort:'low'}),'low');
 assert.equal(thinkingLevel({...relay,protocol:'responses'}),'');
 assert.equal(thinkingLevel({...relay,protocol:'gemini'}),undefined);
 assert.equal(thinkingLevel({...relay,provider:''}),undefined);
 assert.equal(officialDeepSeek(relay),false);
 assert.equal(officialDeepSeek({...official,baseUrl:'http://api.deepseek.com'}),false);
 assert.equal(officialDeepSeek({...official,baseUrl:'https://api.deepseek.com.example/v1'}),false);
 for(const provider of ['openai','anthropic','gemini','compatible'])assert.ok(!Object.hasOwn(aiProviders[provider].config,'reasoningEffort'));
});
test('The selected DeepSeek thinking level reaches the API with the original question',async()=>{
 const priorFetch=globalThis.fetch,origin=process.env.GEOMETRY_API_ORIGIN;process.env.GEOMETRY_API_ORIGIN='http://127.0.0.1:8001';
 const payload={provider:aiProviders.deepseek.config,messages:[{role:'user',content:'2x=6 是否等价于 x=3？'}]};
 globalThis.fetch=async(url,init)=>{
  assert.equal(String(url),'http://127.0.0.1:8001/api/ai/chat');
  const body=JSON.parse(await new Response(init?.body).text());
  assert.deepEqual(body,payload);
  assert.equal(body.provider.reasoningEffort,'max');
  assert.equal(body.provider.model,'deepseek-flash');
  return Response.json({content:'两式等价。'});
 };
 try{const response=await proxyAi(new Request('http://127.0.0.1:3000/api/ai/chat',{method:'POST',headers:{'X-AI-Api-Key':'isolated-thinking-test'},body:JSON.stringify(payload)}),{params:Promise.resolve({path:['ai','chat']})});assert.equal(response.status,200)}
 finally{globalThis.fetch=priorFetch;if(origin===undefined)delete process.env.GEOMETRY_API_ORIGIN;else process.env.GEOMETRY_API_ORIGIN=origin}
});
test('Model discovery proxy forwards only the entered personal key and selected provider',async()=>{
 const priorFetch=globalThis.fetch,origin=process.env.GEOMETRY_API_ORIGIN;process.env.GEOMETRY_API_ORIGIN='http://127.0.0.1:8001';
 globalThis.fetch=async(url,init)=>{assert.equal(String(url),'http://127.0.0.1:8001/api/ai/models');assert.equal((init?.headers as Record<string,string>)['X-AI-Api-Key'],'test-only-key');assert.equal(JSON.parse(await new Response(init?.body).text()).provider.provider,'gemini');return Response.json({models:[]})};
 try{const response=await proxyAi(new Request('http://127.0.0.1:3000/api/ai/models',{method:'POST',headers:{'X-AI-Api-Key':'test-only-key'},body:JSON.stringify({provider:{provider:'gemini'}})}),{params:Promise.resolve({path:['ai','models']})});assert.equal(response.status,200)}
 finally{globalThis.fetch=priorFetch;if(origin===undefined)delete process.env.GEOMETRY_API_ORIGIN;else process.env.GEOMETRY_API_ORIGIN=origin}
});

test('Public application proxy forwards generic provider credentials and configuration',async()=>{
 const priorFetch=globalThis.fetch,origin=process.env.GEOMETRY_API_ORIGIN;
 process.env.GEOMETRY_API_ORIGIN='http://127.0.0.1:8001';
 globalThis.fetch=async(url,init)=>{
  assert.equal(String(url),'http://127.0.0.1:8001/api/ai/chat');
  assert.equal((init?.headers as Record<string,string>)['X-AI-Api-Key'],'local-proxy-test-key');
  assert.equal(JSON.parse(await new Response(init?.body).text()).provider.model,'configured-model');
  return Response.json({content:'test reply'});
 };
 try{
  const response=await proxyAi(new Request('http://127.0.0.1:3000/api/ai/chat',{method:'POST',headers:{'X-AI-Api-Key':'local-proxy-test-key'},body:JSON.stringify({provider:{model:'configured-model'}})}),{params:Promise.resolve({path:['ai','chat']})});
  assert.equal(response.status,200);assert.equal(((await response.json()) as {content:string}).content,'test reply');
 }finally{globalThis.fetch=priorFetch;if(origin===undefined)delete process.env.GEOMETRY_API_ORIGIN;else process.env.GEOMETRY_API_ORIGIN=origin}
});

test('API proxy streams attachment uploads and responses through a real HTTP upstream', {timeout:10000},async()=>{
 const priorOrigin=process.env.GEOMETRY_API_ORIGIN,priorKey=process.env.GEOMETRY_SERVICE_KEY;
 const prefix=Buffer.from('{"attachment":"'+'a'.repeat(65536)),suffix=Buffer.from('几何'.repeat(32768)+'"}');
 const expectedBytes=prefix.length+suffix.length,expectedHash=createHash('sha256').update(prefix).update(suffix).digest('hex');
 let releaseUpload!:()=>void,releaseResponse!:()=>void;
 const upstreamReceivedData=new Promise<void>(resolve=>{releaseUpload=resolve});
 const finishResponse=new Promise<void>(resolve=>{releaseResponse=resolve});
 let inputEnded=false,upstreamReceivedBeforeInputEnded=false;
 let upstreamDetails:{method?:string;url?:string;personalKey?:string|string[];serviceKey?:string|string[]}|undefined;
 const upstream=createServer((request,response)=>{
  void (async()=>{
   upstreamDetails={method:request.method,url:request.url,personalKey:request.headers['x-ai-api-key'],serviceKey:request.headers['x-geometry-service-key']};
   const hash=createHash('sha256');let bytes=0;
   for await(const chunk of request){bytes+=chunk.length;hash.update(chunk);upstreamReceivedBeforeInputEnded ||= !inputEnded;releaseUpload()}
   response.writeHead(202,{'Content-Type':'application/json'});response.write('{"bytes":');
   await finishResponse;
   response.end(bytes+',"sha256":'+JSON.stringify(hash.digest('hex'))+'}');
  })().catch(error=>response.destroy(error));
 });
 await new Promise<void>((resolve,reject)=>{upstream.once('error',reject);upstream.listen(0,'127.0.0.1',()=>resolve())});
 const address=upstream.address();assert.ok(address&&typeof address!=='string');
 process.env.GEOMETRY_API_ORIGIN='http://127.0.0.1:'+address.port;process.env.GEOMETRY_SERVICE_KEY='stream-test-service-key';
 let sentPrefix=false;
 const body=new ReadableStream<Uint8Array>({
  async pull(controller){
   if(!sentPrefix){sentPrefix=true;controller.enqueue(prefix);return}
   let timer:ReturnType<typeof setTimeout>|undefined;
   try{await Promise.race([upstreamReceivedData,new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(new Error('Upstream must receive the first chunk before the upload is complete')),3000)})])}
   finally{clearTimeout(timer)}
   inputEnded=true;controller.enqueue(suffix);controller.close();
  },
 });
 try{
  const options:RequestInit&{duplex:'half'}={method:'POST',headers:{'Content-Type':'application/json','X-AI-Api-Key':'stream-test-personal-key'},body,duplex:'half',signal:AbortSignal.timeout(7000)};
  const response=await proxyAi(new Request('http://localhost/api/ai/import-topic',options),{params:Promise.resolve({path:['ai','import-topic']})});
  assert.equal(response.status,202);assert.equal(response.headers.get('Content-Type'),'application/json');assert.equal(response.headers.get('Cache-Control'),'no-store');
  assert.equal(upstreamReceivedBeforeInputEnded,true,'The proxy must forward data before the client finishes uploading');
  assert.deepEqual(upstreamDetails,{method:'POST',url:'/api/ai/import-topic',personalKey:'stream-test-personal-key',serviceKey:'stream-test-service-key'});
  const reader=response.body!.getReader(),first=await reader.read();assert.equal(first.done,false);
  let reply=new TextDecoder().decode(first.value);assert.equal(reply,'{"bytes":','Response chunks must arrive before the upstream response finishes');
  releaseResponse();
  while(true){const chunk=await reader.read();if(chunk.done)break;reply+=new TextDecoder().decode(chunk.value)}
  assert.deepEqual(JSON.parse(reply),{bytes:expectedBytes,sha256:expectedHash});
 }finally{
  releaseUpload();releaseResponse();upstream.closeAllConnections();await new Promise<void>(resolve=>upstream.close(()=>resolve()));
  if(priorOrigin===undefined)delete process.env.GEOMETRY_API_ORIGIN;else process.env.GEOMETRY_API_ORIGIN=priorOrigin;
  if(priorKey===undefined)delete process.env.GEOMETRY_SERVICE_KEY;else process.env.GEOMETRY_SERVICE_KEY=priorKey;
 }
});

test('Enabled conditions draw both referenced segments, with no duplicate or hidden premise',()=>{
 const p=preset();p.segments=[];p.goal={id:'goal',kind:'fixed_length',args:['A','B'],value:3,enabled:true,toggleable:false};
 p.conditions=[{id:'new-edge',kind:'equal_length',args:['A','D','C','D'],enabled:true,toggleable:true}];
 const original=structuredClone(p);let drawing=drawingObjects(p);
 assert.ok(drawing.segments.some(s=>s.points.slice().sort().join('')==='CD'));
 p.segments=[{id:'cd',points:['D','C']}];drawing=drawingObjects(p);
 assert.equal(drawing.segments.filter(s=>s.points.slice().sort().join('')==='CD').length,1);
 p.conditions[0].enabled=false;p.segments=[];
 assert.equal(drawingObjects(p).segments.some(s=>s.points.slice().sort().join('')==='CD'),false);
 assert.equal(original.conditions.length,1);assert.deepEqual(original.goal,p.goal);
});
test('Goal arms and implicit circle/arc geometry are drawn without constraining motion',()=>{
 const p=preset();p.segments=[];p.circles=[];
 p.goal={id:'goal',kind:'equal_angle',args:['B','A','D','A','C','D'],enabled:true,toggleable:false};
 p.conditions=[{id:'arc',kind:'on_arc',args:['D','A','B','C'],orientation:'cw',enabled:true,toggleable:true}];
 const before=structuredClone(p),drawing=drawingObjects(p);
 for(const pair of ['AB','AD','AC','CD'])assert.ok(drawing.segments.some(s=>s.points.slice().sort().join('')===pair));
 assert.equal(drawing.circles[0].end,'C');assert.equal(drawing.circles[0].orientation,'cw');assert.deepEqual(p,before);
});


test('Arc framing includes only its stated sweep and keeps radius unchanged',()=>{
 const points=[{id:'O',x:0,y:0},{id:'A',x:12,y:0},{id:'B',x:0,y:12}];
 const arc=circleGeometry(points,{center:'O',through:'A',end:'B'})!;
 assert.equal(arc.radius,12);assert.ok(Math.abs(arc.sweep-Math.PI/2)<1e-10);
 assert.ok(arc.samples.every(p=>p.x>=-1e-10&&p.y>=-1e-10));
 const reversed=circleGeometry(points,{center:'O',through:'B',end:'A',orientation:'cw'})!;
 assert.ok(Math.abs(reversed.sweep-arc.sweep)<1e-10);
});
test('AI fraction and bold text render as math and strong elements',()=>{
 const content=String.raw`梯形中位线：**两底和的一半。 ** 若两底为 \(a\)、\(b\)，则 \[m=\frac{a+b}{2}\]`;
 const html=renderToStaticMarkup(React.createElement(AiResponse,{content}));
 assert.match(html,/<strong>两底和的一半。<\/strong>/);assert.match(html,/class="katex/);assert.match(html,/mfrac/);assert.doesNotMatch(html,/katex-error/);
});
test('AI proof rules render inline and display fractions without an additional copy control',()=>{
 const proof:Proof={id:'ai-rule-render',title:'A candidate proof',engine:'AI',status:'candidate',assumptionIds:[],assumptionNodes:[],steps:[{
  id:'step-1',statement:'The ratios are equal.',premises:[],
  rule:'由相似三角形，\\(\\frac{AB}{AC}=\\frac{BD}{DC}\\)。因此 \\[\\frac{AB+AC}{AC}=1+\\frac{BD}{DC}\\]',
 }]};
 const html=renderToStaticMarkup(React.createElement(ProofView,{proof,problem:preset(),conditionNames:new Map()}));
 const rule=html.split('<div class="step-rule">')[1]?.split('<details class="dependencies">')[0];
 assert.ok(rule,'The rule must render in its own block');
 assert.match(rule,/由相似三角形/);assert.match(rule,/class="katex"/);assert.match(rule,/class="katex-display"/);assert.match(rule,/mfrac/);
 assert.doesNotMatch(rule,/katex-error|ai-copy|\\\(|\\\[/);
 assert.match(rule,/font-size:10px;color:#a28c6b/);
 assert.equal((html.match(/class="text-button ai-copy"/g)||[]).length,1,'Only the existing statement copy control remains');
 assert.doesNotMatch(html,/<small><div/);
});

test('Non-AI proof rules retain their plain small-text rendering',()=>{
 const proof:Proof={id:'newclid',title:'A proof',engine:'Newclid',status:'found',assumptionIds:[],assumptionNodes:[],steps:[{id:'step-1',statement:'AB = AC',rule:'SSS',premises:[]}]};
 const html=renderToStaticMarkup(React.createElement(ProofView,{proof,problem:preset(),conditionNames:new Map()}));
 assert.match(html,/<small>SSS<\/small>/);assert.doesNotMatch(html,/step-rule|ai-copy|ai-markdown/);
});

test('Math normalization leaves code examples intact and never enables raw HTML',()=>{
 assert.equal(mathMarkdown('`\\(a\\)`'),'`\\(a\\)`');
 const html=renderToStaticMarkup(React.createElement(AiResponse,{content:'<script>alert(1)</script>'}));assert.doesNotMatch(html,/<script>/);
});






test('Saving and deleting a custom topic goes through the local store',async()=>{
 const store=new Map<string,string>(),calls:{url:string;method:string}[]=[];
 const previousStorage=Object.getOwnPropertyDescriptor(globalThis,'localStorage'),previousWindow=Object.getOwnPropertyDescriptor(globalThis,'window'),previousFetch=globalThis.fetch;
 Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:(k:string)=>store.get(k)||null,setItem:(k:string,v:string)=>store.set(k,v),removeItem:(k:string)=>store.delete(k)}});
 Object.defineProperty(globalThis,'window',{configurable:true,value:{dispatchEvent:()=>true,localStorage:globalThis.localStorage}});
 globalThis.fetch=async(url,init)=>{calls.push({url:String(url),method:init?.method||'GET'});return Response.json({deleted:true,id:'custom-test'})};
 try{
  const p={...preset(),id:'custom-test'},topic={id:p.id,problem:p,recognizedText:'test',createdAt:'test',updatedAt:'test'};
  await saveTopic(topic);openTopic(topic);
  assert.deepEqual(calls[0],{url:'/api/topics',method:'POST'});
  store.set('geometry.records.v1',JSON.stringify([{problem:{id:'isosceles'}},{problem:{id:topic.id}}]));
  await deleteTopic(topic.id);
  assert.deepEqual(calls[1],{url:'/api/topics/'+topic.id,method:'DELETE'});
  assert.equal(store.has('geometry.draft.'+topic.id),false);
  assert.equal(JSON.parse(store.get('geometry.records.v1')!)[0].problem.id,'isosceles');
  store.set('geometry.topics.v1',JSON.stringify([topic]));
  assert.equal(await migrateLocalTopics(),1);
  assert.equal(store.has('geometry.topics.v1'),false);
  assert.equal(calls[2].url,'/api/topics');
 }finally{
  globalThis.fetch=previousFetch;
  if(previousStorage)Object.defineProperty(globalThis,'localStorage',previousStorage);else Reflect.deleteProperty(globalThis,'localStorage');
  if(previousWindow)Object.defineProperty(globalThis,'window',previousWindow);else Reflect.deleteProperty(globalThis,'window');
 }
});

test('Saved topic documents can be restored without parsing ordinary attachments as topics',()=>{
 const p=cleanProblem({...preset(),id:'custom-restored'});
 assert.deepEqual(readTopicDocument(JSON.stringify(p)),p);
 assert.deepEqual(readTopicDocument(JSON.stringify({problem:p,recognizedText:'题目文字'})),p);
 assert.equal(readTopicDocument('这是一道三角形题目'),undefined);
 assert.equal(readTopicDocument('{"schemaVersion":1,"id":"custom-bad"}'),undefined);
});
