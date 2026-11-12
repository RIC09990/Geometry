// Local website gateway. All application services stay on loopback.
import http from 'node:http';
import {pathToFileURL} from 'node:url';
import {createBrotliCompress,createGzip,constants} from 'node:zlib';
import {pipeline} from 'node:stream';
import {compressibleAsset,preferredEncoding,responseCacheControl,staticAssetPath} from './local-assets.mjs';
const host='127.0.0.1';
const getApi=new Set(['/api/cases','/api/ai/status']);
const postApi=new Set(['/api/validate','/api/analyze','/api/check-step','/api/ai/models','/api/ai/chat','/api/ai/review-proof','/api/ai/export-pdf','/api/ai/import-topic','/api/ai/proof-ideas']);
const common={'cache-control':'no-store, max-age=0','x-content-type-options':'nosniff','referrer-policy':'same-origin'};
function reply(res,status,body){res.writeHead(status,{'Content-Type':'application/json; charset=utf-8',...common});res.end(JSON.stringify(body));}
function varyEncoding(value){return [...new Set(String(value||'').split(',').map(s=>s.trim()).filter(Boolean).concat('Accept-Encoding'))].join(', ');}

export function createLocalGateway({instance,serviceKey,apiPort=8001,frontendPort=3101}={}){
// Bound duplicate compression work without retaining pages, replies or user data.
const compressedCache=new Map();let cachedBytes=0;
function cacheCompressed(key,body){
  if(body.length>2*1024*1024)return;
  while(compressedCache.size>=32||cachedBytes+body.length>8*1024*1024){
    const oldest=compressedCache.keys().next().value;if(oldest===undefined)break;
    cachedBytes-=compressedCache.get(oldest).length;compressedCache.delete(oldest);
  }
  const previous=compressedCache.get(key);if(previous)cachedBytes-=previous.length;
  compressedCache.set(key,body);cachedBytes+=body.length;
}
const server=http.createServer((req,res)=>{
  let url;
  try{url=new URL(req.url,'http://localhost');decodeURIComponent(url.pathname);}catch{return reply(res,400,{detail:'Invalid path'});}
  const pathname=decodeURIComponent(url.pathname);
  if(pathname==='/__geometry_local_status'&&req.method==='GET')return reply(res,200,{running:true,instance});
  const api=pathname.startsWith('/api/');
  // Client-side navigation requests the same public page with a .rsc suffix.
  const pagePath=pathname.endsWith('.rsc')?pathname.slice(0,-4):pathname;
  const page=/^\/(?:$|ai\/?$|cases(?:\/[a-zA-Z0-9_-]+)?\/?$|about(?:\/[a-zA-Z0-9_-]+)?\/?$)/.test(pagePath);
  if(api ? !(req.method==='GET'&&getApi.has(pathname)||req.method==='POST'&&postApi.has(pathname))
    : !['GET','HEAD'].includes(req.method)||!(page||staticAssetPath(pathname)))
    return reply(res,404,{detail:'Not found'});
  if(pathname.includes('..')||pathname.endsWith('.map')||pathname.includes('\\'))return reply(res,404,{detail:'Not found'});
  const limit=api?(pathname.startsWith('/api/ai/')?48*1024*1024:262144):0;
  const length=Number(req.headers['content-length']||0);
  if(!Number.isSafeInteger(length)||length<0||length>limit)return reply(res,413,{detail:'Request too large'});
  const asset=!api&&staticAssetPath(pathname),encoding=asset?preferredEncoding(req.headers['accept-encoding']):null;
  const textPath=asset&&/\.(?:js|mjs|css|json|svg)$/i.test(pathname);
  // Forward only browser headers needed by this app; never trust public routing or service headers.
  const headers={host:`${host}:${api?apiPort:frontendPort}`};
  for(const key of ['accept','accept-language','accept-encoding','content-type','content-length','rsc','next-router-state-tree','next-router-prefetch','next-router-segment-prefetch','next-url','x-vinext-interception-context','x-vinext-mounted-slots','x-vinext-rsc-render-mode','x-vinext-client-reuse-manifest','x-ai-api-key','x-deepseek-api-key',...(!api?['if-none-match','if-modified-since']:[])]){
    if(req.headers[key]!==undefined)headers[key]=req.headers[key];
  }
  // The gateway provides Brotli itself for static text; no double encoding of upstream gzip.
  if(encoding&&textPath)headers['accept-encoding']='identity';
  if(api)headers['x-geometry-service-key']=serviceKey;
  const upstream=http.request({hostname:host,port:api?apiPort:frontendPort,path:req.url,method:req.method,headers},incoming=>{
    const status=incoming.statusCode??502,outgoing={...incoming.headers,...common};
    outgoing['cache-control']=responseCacheControl(pathname,status,req.headers,incoming.headers);
    for(const name of ['connection','keep-alive','transfer-encoding','server','x-powered-by'])delete outgoing[name];
    if(textPath)outgoing.vary=varyEncoding(outgoing.vary);
    const compress=status===200&&encoding&&compressibleAsset(pathname,String(incoming.headers['content-type']||''))&&!incoming.headers['content-encoding'];
    if(!compress){res.writeHead(status,outgoing);pipeline(incoming,res,()=>{});return;}
    outgoing.vary=varyEncoding(outgoing.vary);outgoing['content-encoding']=encoding;
    delete outgoing['content-length'];delete outgoing['content-md5'];delete outgoing['accept-ranges'];
    if(outgoing.etag&&!String(outgoing.etag).startsWith('W/'))outgoing.etag='W/'+outgoing.etag;
    if(req.method==='HEAD'){res.writeHead(status,outgoing);incoming.resume();res.end();return;}
    const key=outgoing['cache-control'].startsWith('public,')&&incoming.headers.etag?pathname+'|'+incoming.headers.etag+'|'+encoding:null;
    const cached=key&&compressedCache.get(key);
    if(cached){outgoing['content-length']=cached.length;res.writeHead(status,outgoing);incoming.resume();res.end(cached);return;}
    const compressor=encoding==='br'?createBrotliCompress({params:{[constants.BROTLI_PARAM_QUALITY]:5}}):createGzip({level:6});
    let bytes=0,chunks=[];
    if(key)compressor.on('data',chunk=>{bytes+=chunk.length;if(bytes<=2*1024*1024)chunks.push(chunk);else chunks=[];});
    compressor.on('end',()=>{if(key&&chunks.length&&bytes<=2*1024*1024)cacheCompressed(key,Buffer.concat(chunks));});
    res.writeHead(status,outgoing);pipeline(incoming,compressor,res,()=>{});
  });
  // Keep the gateway outside the 300s AI budget so the app's 504 reaches the UI.
  upstream.setTimeout(315000,()=>upstream.destroy(new Error('timeout')));
  upstream.on('error',()=>{if(!res.headersSent)reply(res,503,{detail:'本机服务正在恢复，请稍后重试。'});else res.destroy();});
  let bytes=0;
  req.on('data',chunk=>{bytes+=chunk.length;if(bytes>limit){upstream.destroy();if(!res.headersSent)reply(res,413,{detail:'Request too large'});req.destroy();}});
  req.on('aborted',()=>upstream.destroy());req.on('error',()=>upstream.destroy());
  res.on('close',()=>{if(!res.writableEnded)upstream.destroy();});
  req.pipe(upstream);
});
server.on('upgrade',(_req,socket)=>socket.destroy());
server.requestTimeout=130000;server.headersTimeout=10000;server.maxHeadersCount=64;
return server;
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  createLocalGateway({instance:process.env.GEOMETRY_LOCAL_INSTANCE,serviceKey:process.env.GEOMETRY_SERVICE_KEY})
    .listen(3000,host,()=>console.log('Geometry local gateway ready on 127.0.0.1:3000'));
}
