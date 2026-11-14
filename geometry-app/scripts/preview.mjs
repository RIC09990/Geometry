import http from 'node:http';
import net from 'node:net';
import {spawn} from 'node:child_process';
import {createWriteStream,existsSync,mkdirSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readExecutionProfile} from './execution-profile.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const host='127.0.0.1';
const logDirectory=path.join(root,'.local');
mkdirSync(logDirectory,{recursive:true});
const gatewayLog=createWriteStream(path.join(logDirectory,'preview-gateway.log'),{flags:'a'});
gatewayLog.on('error',error=>console.error('Preview log:',error.message));
function log(message){const line=`[${new Date().toISOString()}] ${message}\n`;gatewayLog.write(line);process.stdout.write(line)}

const serviceKey=process.env.GEOMETRY_SERVICE_KEY;
const python=path.join(root,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
const owned=new Set();
const sockets=new Set();
let stopping=false;
let pollTimer;
async function freeFrontendPort(){for(let port=3101;port<=3120;port++){const free=await new Promise(resolve=>{const listener=net.createServer();listener.once('error',()=>resolve(false));listener.listen(port,host,()=>listener.close(()=>resolve(true)))});if(free)return port;}throw new Error('没有可用的 Geometry 页面内部端口');}
const frontend={name:'frontend',port:await freeFrontendPort(),route:'/',ready:false,state:'starting',restarts:0,failures:0,generation:0};
const api={name:'api',port:8001,route:'/api/health',ready:false,state:'starting',restarts:0,failures:0,generation:0};
const services=[frontend,api];

function publicStatus(service){return {ready:service.ready,state:service.state,port:service.port,pid:service.child?.pid??null,httpStatus:service.httpStatus??null,lastCheckedAt:service.lastCheckedAt??null,lastError:service.lastError??null,restarts:service.restarts,retryAt:service.retryAt??null}}
function markUnavailable(service,error){service.ready=false;service.lastError=error.message||String(error)}

function probe(service){
 if(service.probing)return service.probing;
 const generation=service.generation;
 service.probing=new Promise(resolve=>{
  let settled=false;
  const finish=(status,error)=>{
   if(settled)return;settled=true;
   if(generation===service.generation&&!stopping){
    service.httpStatus=status??null;service.lastCheckedAt=new Date().toISOString();service.ready=status===200;
    if(service.ready){service.state='running';service.lastError=null}else if(error)service.lastError=error.message;
   }
   resolve();
  };
  const headers={Host:`${host}:3000`,Accept:service===frontend?'text/html':'application/json'};
  if(service===api&&serviceKey)headers['X-Geometry-Service-Key']=serviceKey;
  const request=http.get({hostname:host,port:service.port,path:service.route,headers,agent:false},response=>{response.resume();response.on('error',error=>finish(null,error));response.on('end',()=>finish(response.statusCode))});
  request.setTimeout(3000,()=>request.destroy(new Error('就绪检查超时')));
  request.on('error',error=>finish(null,error));
 }).finally(()=>{service.probing=undefined});
 return service.probing;
}

function start(service){
 if(stopping)return;
 service.generation++;service.ready=false;service.state='starting';service.retryAt=null;service.startedAt=Date.now();
 const output=createWriteStream(path.join(logDirectory,`preview-${service.name}.log`),{flags:'a'});
 output.on('error',error=>log(`${service.name} log error: ${error.message}`));
 let command,args;
 try{
  if(service===frontend){
   command=process.execPath;
   const hostFlag=readExecutionProfile()==='managed-linux'?'--host':'--hostname';
   args=['scripts/run-framework.mjs','dev',hostFlag,host,'--port',String(frontend.port)];
  }else{
   command=python;
   args=['-m','uvicorn','server.main:app','--host',host,'--port','8001','--no-access-log'];
   if(!existsSync(python))throw new Error('未找到 .venv Python；请按 README 安装计算服务依赖。');
  }
  const child=spawn(command,args,{cwd:root,windowsHide:true,detached:process.platform!=='win32',stdio:['ignore','pipe','pipe'],env:{...process.env,GEOMETRY_API_ORIGIN:`http://${host}:8001`,PYTHONIOENCODING:'utf-8',PYTHONUNBUFFERED:'1'}});
  service.child=child;owned.add(child);
  child.stdout.pipe(output,{end:false});child.stderr.pipe(output,{end:false});
  let finished=false;
  const ended=(reason)=>{
   if(finished)return;finished=true;owned.delete(child);output.end();
   if(service.child===child)service.child=undefined;
   service.ready=false;
   if(stopping)return;
   restart(service,reason);
  };
  child.once('error',error=>ended(error.message));
  child.once('exit',(code,signal)=>ended(`exit ${code??signal}`));
  log(`${service.name} starting on ${host}:${service.port} (PID ${child.pid??'pending'}).`);
 }catch(error){output.end();restart(service,error.message)}
}

function restart(service,reason){
 if(stopping||service.restartTimer)return;
 if(Date.now()-service.startedAt>30000)service.failures=0;
 service.failures++;service.restarts++;
 const delay=Math.min(1000*2**Math.min(service.failures-1,4),10000);
 service.ready=false;service.state='restarting';service.lastError=reason;service.retryAt=new Date(Date.now()+delay).toISOString();
 log(`${service.name} stopped (${reason}); retrying in ${delay/1000}s.`);
 service.restartTimer=setTimeout(()=>{service.restartTimer=undefined;start(service)},delay);
}

const updatingPage=`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Geometry 正在更新</title><style>html{color-scheme:light}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#ece7de;color:#382f25;font:16px/1.9 "Microsoft YaHei",sans-serif}main{max-width:540px;margin:24px;padding:36px;background:#fffc;border:1px solid #c9bda9;border-radius:18px;box-shadow:0 12px 45px #382f2510}h1{font-size:28px;line-height:1.4}small{color:#776a58}button{font:inherit;padding:8px 18px;background:#463a2c;color:#fff9ef;border:0;border-radius:5px;cursor:pointer}</style><main><small>GEOMETRY · 几何探究</small><h1>Geometry 正在更新</h1><p>页面正在启动或重新连接。你可以保持这个窗口打开，准备完成后会自动恢复。</p><p id="status" role="status" aria-live="polite">正在检查页面与计算服务…</p><button onclick="location.reload()">立即重试</button><p><small>你的本机探究记录仍保存在当前浏览器中。</small></p></main><script>async function retry(){try{const response=await fetch('/__geometry_ready',{cache:'no-store'});const state=await response.json();if(state.frontend.ready){location.reload();return}document.getElementById('status').textContent='页面：'+(state.frontend.ready?'已就绪':'正在恢复')+'；计算服务：'+(state.api.ready?'已就绪':'正在恢复')+'。将自动重试。'}catch{document.getElementById('status').textContent='正在重新连接，稍后将自动重试。'}setTimeout(retry,2000)}retry()</script></html>`;

function documentRequest(request,pathname){if(request.headers.rsc==='1'||new URL(request.url||'/',`http://${host}:3000`).searchParams.has('_rsc'))return false;return request.method==='GET'&&(request.headers.accept?.includes('text/html')||request.headers['sec-fetch-dest']==='document'||pathname==='/'||/^\/(?:cases(?:\/[^.]*)?|about)\/?$/.test(pathname))}
function unavailable(request,response,service,pathname){
 if(response.headersSent){response.destroy();return}
 if(service===api){response.writeHead(503,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','Retry-After':'2'});response.end(JSON.stringify({detail:'计算服务正在启动或重新连接，请稍后重试。'}));return}
 if(documentRequest(request,pathname)){response.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});response.end(updatingPage);return}
 response.writeHead(503,{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store','Retry-After':'2'});response.end('Geometry 页面服务正在恢复，请稍后重试。');
}

function proxy(request,response,service,pathname){
 const headers={...request.headers};delete headers.connection;delete headers['keep-alive'];delete headers['proxy-connection'];
 if(service===api&&serviceKey)headers['x-geometry-service-key']=serviceKey;
 const upstream=http.request({hostname:host,port:service.port,path:request.url,method:request.method,headers},incoming=>{
  if(service===frontend&&incoming.statusCode>=500&&documentRequest(request,pathname)){incoming.resume();unavailable(request,response,service,pathname);return}
  const outgoingHeaders={...incoming.headers};delete outgoingHeaders.connection;delete outgoingHeaders['keep-alive'];
  response.writeHead(incoming.statusCode??502,outgoingHeaders);
  incoming.on('error',()=>response.destroy());incoming.pipe(response);
 });
 // AI has a 300-second server budget covering all model passes and queueing.
 // Leave time for its explicit timeout response instead of cutting it off at 60s.
 const timeout=service===api&&pathname.startsWith('/api/ai/')?300000:60000;
 upstream.setTimeout(timeout,()=>upstream.destroy(new Error('上游请求超时')));
 upstream.on('error',error=>{markUnavailable(service,error);unavailable(request,response,service,pathname)});
 request.on('aborted',()=>upstream.destroy());
 request.on('error',()=>upstream.destroy());
 response.on('close',()=>{if(!response.writableEnded)upstream.destroy()});
 request.pipe(upstream);
}

const server=http.createServer(async(request,response)=>{
 try{
  const pathname=new URL(request.url||'/',`http://${host}:3000`).pathname;
  if(pathname==='/__geometry_ready'){
   await Promise.all(services.map(probe));
   if(response.destroyed)return;
   response.writeHead(200,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});
   response.end(JSON.stringify({ready:frontend.ready&&api.ready,frontend:publicStatus(frontend),api:publicStatus(api)}));return;
  }
  proxy(request,response,pathname==='/api'||pathname.startsWith('/api/')?api:frontend,pathname);
 }catch(error){log(`Gateway request error: ${error.message}`);if(!response.headersSent)response.writeHead(503,{'Content-Type':'text/plain; charset=utf-8'});response.end('Geometry 正在恢复，请稍后重试。')}
});
server.on('connection',socket=>{sockets.add(socket);socket.on('error',()=>{});socket.once('close',()=>sockets.delete(socket))});
server.on('upgrade',(request,socket,head)=>{
 const upstream=http.request({hostname:host,port:frontend.port,path:request.url,method:request.method,headers:request.headers});
 upstream.setTimeout(10000,()=>upstream.destroy(new Error('HMR 连接超时')));
 upstream.on('error',()=>socket.destroy());
 socket.on('error',()=>upstream.destroy());
 socket.once('close',()=>upstream.destroy());
 upstream.on('response',response=>{response.resume();socket.end('HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\n\r\n')});
 upstream.on('upgrade',(response,upstreamSocket,upstreamHead)=>{
  upstream.setTimeout(0);socket.setTimeout(0);upstreamSocket.setTimeout(0);
  let handshake=`HTTP/1.1 ${response.statusCode} ${response.statusMessage}\r\n`;
  for(let index=0;index<response.rawHeaders.length;index+=2)handshake+=`${response.rawHeaders[index]}: ${response.rawHeaders[index+1]}\r\n`;
  socket.write(handshake+'\r\n');
  upstreamSocket.on('error',()=>socket.destroy());
  upstreamSocket.once('close',()=>socket.destroy());
  socket.once('close',()=>upstreamSocket.destroy());
  if(head.length)upstreamSocket.write(head);if(upstreamHead.length)socket.write(upstreamHead);
  socket.pipe(upstreamSocket);upstreamSocket.pipe(socket);
 });
 upstream.end();
});

async function stopChild(child){
 if(!child.pid||child.exitCode!==null||child.signalCode!==null)return;
 if(process.platform==='win32'){
  await new Promise(resolve=>{const killer=spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});killer.once('error',()=>{child.kill();resolve()});killer.once('exit',resolve)});
 }else{
  try{process.kill(-child.pid,'SIGTERM')}catch{child.kill()}
  await new Promise(resolve=>{const timer=setTimeout(()=>{try{process.kill(-child.pid,'SIGKILL')}catch{}resolve()},2000);child.once('exit',()=>{clearTimeout(timer);resolve()})});
 }
}
async function shutdown(signal){
 if(stopping)return;stopping=true;log(`Gateway stopping (${signal}).`);
 clearInterval(pollTimer);for(const service of services){clearTimeout(service.restartTimer);service.state='stopped';service.ready=false}
 server.close();for(const socket of sockets)socket.destroy();
 await Promise.allSettled([...owned].map(stopChild));
 gatewayLog.end(()=>process.exit(0));
}
process.on('SIGINT',()=>void shutdown('SIGINT'));
process.on('SIGTERM',()=>void shutdown('SIGTERM'));
server.on('error',error=>{log(`Gateway cannot listen: ${error.message}`);if(!server.listening){gatewayLog.end(()=>process.exit(1))}});
server.listen(3000,host,()=>{
 log(`Geometry preview: http://${host}:3000/ (gateway is listening).`);
 for(const service of services)start(service);
 void Promise.all(services.map(probe));
 pollTimer=setInterval(()=>void Promise.all(services.map(probe)),2000);
});
