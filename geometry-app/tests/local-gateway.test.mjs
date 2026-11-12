import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {once} from 'node:events';
import {brotliDecompressSync,gunzipSync,gzipSync} from 'node:zlib';
import {createLocalGateway} from '../scripts/local-gateway.mjs';

async function listen(server){server.listen(0,'127.0.0.1');await once(server,'listening');return server.address().port;}
async function close(server){server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
function request(port,path,headers={},method='GET',body){
 return new Promise((resolve,reject)=>{
  const req=http.request({host:'127.0.0.1',port,path,headers,method},res=>{
   const chunks=[];res.on('data',c=>chunks.push(c));res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,body:Buffer.concat(chunks)}));res.on('error',reject);
  });req.on('error',reject);req.end(body);
 });
}

test('Real gateway HTTP compression, cache negotiation and private-route boundaries',async t=>{
 const payload=Buffer.from(('export const geometry="ABCDEFGHIJKLMNOPQRSTUVWXYZ";\n').repeat(5000));
 let receivedEncoding='',conditional='',upstreamCount=0,privateSequence=0;
 const frontend=http.createServer((req,res)=>{
  upstreamCount++;receivedEncoding=req.headers['accept-encoding'];conditional=req.headers['if-none-match'];
  if(req.url.endsWith('private.js')){
   const content=Buffer.from('private version '+(++privateSequence));
   res.writeHead(200,{'content-type':'application/javascript',etag:'"same-private-etag"','set-cookie':'private-test-only=1'});res.end(content);return;
  }
  if(req.url.endsWith('no-store.js')||req.url.endsWith('private-control.js')){
   const content=Buffer.from('private version '+(++privateSequence));
   res.writeHead(200,{'content-type':'application/javascript',etag:'"same-private-etag"','cache-control':req.url.endsWith('no-store.js')?'no-store':'private, max-age=30'});res.end(content);return;
  }
  if(req.url.endsWith('credential.js')){
   const content=Buffer.from('credential version '+(++privateSequence));
   res.writeHead(200,{'content-type':'application/javascript',etag:'"same-credential-etag"'});res.end(content);return;
  }
  if(req.url.endsWith('missing.js')){res.writeHead(404,{'content-type':'application/javascript'});res.end('missing');return;}
  if(req.headers['if-none-match']?.replace(/^W\//,'')==='"script-v1"'){res.writeHead(304,{etag:'"script-v1"'});res.end();return;}
  if(req.url.startsWith('/_next/static/')){
   if(req.url.endsWith('already.js')){const zipped=gzipSync(payload);res.writeHead(200,{'content-type':'application/javascript','content-encoding':'gzip','content-length':zipped.length});res.end(zipped);return;}
   res.writeHead(200,{'content-type':'application/javascript; charset=utf-8','content-length':payload.length,etag:'"script-v1"',vary:'Accept'});res.end(payload);return;
  }
  const rsc=req.url.endsWith('.rsc')||req.headers.rsc==='1';
  res.writeHead(200,{'content-type':rsc?'text/x-component':'text/html; charset=utf-8',etag:'"shell-v1"'});res.end(rsc?'rsc-data':'<!doctype html><html>Geometry</html>');
 });
 const api=http.createServer((req,res)=>{assert.equal(req.headers['x-geometry-service-key'],'test-only-service');res.writeHead(200,{'content-type':'application/json'});res.end('{"content":"test-only-answer"}');});
 const frontendPort=await listen(frontend),apiPort=await listen(api);
 const gateway=createLocalGateway({instance:'test-only-instance',serviceKey:'test-only-service',frontendPort,apiPort});
 const port=await listen(gateway);
 t.after(async()=>{await close(gateway);await close(frontend);await close(api);});
 const path='/_next/static/chunks/test-hash.js';
 const br=await request(port,path,{'accept-encoding':'gzip, br'});
 assert.equal(br.status,200);assert.equal(br.headers['content-encoding'],'br');assert.equal(receivedEncoding,'identity');
 assert.deepEqual(brotliDecompressSync(br.body),payload);assert.ok(br.body.length<payload.length/10);
 assert.equal(br.headers['cache-control'],'public, max-age=604800, immutable');assert.match(br.headers.vary,/Accept-Encoding/);assert.match(br.headers.vary,/Accept/);
 assert.equal(br.headers.etag,'W/"script-v1"');assert.equal(br.headers['content-length'],undefined);
 const cached=await request(port,path,{'accept-encoding':'br'});
 assert.deepEqual(cached.body,br.body);assert.equal(Number(cached.headers['content-length']),br.body.length);assert.equal(upstreamCount,2);
 const gzip=await request(port,path,{'accept-encoding':'br;q=0,gzip'});
 assert.equal(gzip.headers['content-encoding'],'gzip');assert.deepEqual(gunzipSync(gzip.body),payload);
 const identity=await request(port,path,{'accept-encoding':'identity'});
 assert.equal(identity.headers['content-encoding'],undefined);assert.deepEqual(identity.body,payload);assert.match(identity.headers.vary,/Accept-Encoding/);
 const head=await request(port,path,{'accept-encoding':'br'},'HEAD');
 assert.equal(head.status,200);assert.equal(head.body.length,0);assert.equal(head.headers['content-encoding'],'br');assert.equal(head.headers['content-length'],undefined);
 const unchanged=await request(port,path,{'accept-encoding':'br','if-none-match':br.headers.etag});
 assert.equal(conditional,br.headers.etag);assert.equal(unchanged.status,304);assert.equal(unchanged.body.length,0);assert.equal(unchanged.headers['content-encoding'],undefined);assert.match(unchanged.headers.vary,/Accept-Encoding/);
 assert.equal(unchanged.headers['cache-control'],'public, max-age=604800, immutable');
 const already=await request(port,'/_next/static/chunks/already.js',{'accept-encoding':'br,gzip'});
 assert.equal(already.headers['content-encoding'],'gzip');assert.deepEqual(gunzipSync(already.body),payload);
 const missing=await request(port,'/_next/static/chunks/missing.js',{'accept-encoding':'br'});
 assert.equal(missing.status,404);assert.equal(missing.headers['cache-control'],'no-store, max-age=0');assert.equal(missing.headers['content-encoding'],undefined);
 for(const path of ['/','/ai'])assert.equal((await request(port,path)).headers['cache-control'],'private, max-age=0, must-revalidate');
 for(const [path,headers] of [['/ai.rsc',{}],['/ai',{rsc:'1'}],['/api/cases',{}],['/__geometry_local_status',{}]]){
  assert.equal((await request(port,path,headers)).headers['cache-control'],'no-store, max-age=0');
 }
 const ai=await request(port,'/api/ai/chat',{'content-type':'application/json','content-length':'2','accept-encoding':'br'},'POST','{}');
 assert.equal(ai.headers['cache-control'],'no-store, max-age=0');assert.equal(ai.headers['content-encoding'],undefined);assert.equal(JSON.parse(ai.body).content,'test-only-answer');
 assert.equal((await request(port,'/_next/static/chunks/private.js.map')).status,404);
 assert.equal((await request(port,'/server/ai.py')).status,404);
 for(const name of ['private.js','no-store.js','private-control.js','credential.js']){
  const headers={'accept-encoding':'br',...(name==='credential.js'?{'x-ai-api-key':'test-only-key'}:{})};
  const first=await request(port,'/_next/static/chunks/'+name,headers),second=await request(port,'/_next/static/chunks/'+name,headers);
  assert.equal(first.headers['cache-control'],'no-store, max-age=0');assert.equal(second.headers['cache-control'],'no-store, max-age=0');
  assert.notDeepEqual(brotliDecompressSync(first.body),brotliDecompressSync(second.body),'private bytes must not come from RAM cache');
 }
});
