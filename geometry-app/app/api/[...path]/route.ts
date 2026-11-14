const allowed = new Set(['health','cases','validate','analyze','check-step','ai/status','ai/models','ai/chat','ai/chat/stream','ai/compact','ai/review-proof','ai/export-pdf','ai/import-topic','ai/proof-ideas']);
const conversation = /^ai\/conversations(?:\/[0-9a-f-]{36})?$/;
async function proxy(request:Request,context:{params:Promise<{path:string[]}>}){
 const {path}=await context.params;const endpoint=path.join('/');
 if(!allowed.has(endpoint)&&!conversation.test(endpoint))return Response.json({detail:'未找到接口'},{status:404});
 const origin=process.env.GEOMETRY_API_ORIGIN||(process.env.NODE_ENV==='development'?'http://127.0.0.1:8001':'');
 if(!origin)return Response.json({detail:'尚未配置计算服务地址'},{status:503});
 const headers:Record<string,string>={'Content-Type':'application/json'};
 const personalKey=request.headers.get('X-AI-Api-Key')||request.headers.get('X-DeepSeek-Api-Key');
 if(['ai/models','ai/chat','ai/chat/stream','ai/compact','ai/review-proof','ai/import-topic','ai/proof-ideas'].includes(endpoint)&&personalKey)headers['X-AI-Api-Key']=personalKey;
 if(process.env.GEOMETRY_SERVICE_KEY)headers['X-Geometry-Service-Key']=process.env.GEOMETRY_SERVICE_KEY;
 const options:RequestInit&{duplex:'half'}={method:request.method,headers,body:request.method==='GET'?undefined:request.body,duplex:'half',signal:AbortSignal.any([request.signal,AbortSignal.timeout(endpoint.startsWith('ai/')?310000:60000)])};
 try{const response=await fetch(new URL('/api/'+endpoint,origin),options);return new Response(response.body,{status:response.status,headers:{'Content-Type':response.headers.get('content-type')||'application/json','Cache-Control':'no-store'}})}catch{return Response.json({detail:'计算服务暂时不可用或请求超时，请稍后重试。'},{status:503})}
}
export const GET=proxy;
export const POST=proxy;
export const PATCH=proxy;
export const DELETE=proxy;
