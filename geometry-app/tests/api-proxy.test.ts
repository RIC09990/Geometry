import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {once} from 'node:events';
import {GET} from '../app/api/[...path]/route';

test('Topic search reaches the upstream with its query parameters intact',async()=>{
 let received:URL|undefined;
 const server=http.createServer((request,response)=>{
  received=new URL(request.url!,'http://localhost');
  response.setHeader('Content-Type','application/json');
  response.end(JSON.stringify(received.searchParams.get('q')==='等腰 & triangle'?[{id:'custom-match'}]:[]));
 });
 const previous=process.env.GEOMETRY_API_ORIGIN;
 try{
  server.listen(0,'127.0.0.1');await once(server,'listening');
  const address=server.address() as {port:number};
  process.env.GEOMETRY_API_ORIGIN=`http://127.0.0.1:${address.port}`;
  const response=await GET(new Request('http://localhost/api/topics?q='+encodeURIComponent('等腰 & triangle')),
   {params:Promise.resolve({path:['topics']})});
  assert.equal(response.status,200);
  assert.deepEqual(await response.json(),[{id:'custom-match'}]);
  assert.equal(received?.pathname,'/api/topics');
  assert.equal(received?.searchParams.get('q'),'等腰 & triangle');
 }finally{
  if(previous===undefined)delete process.env.GEOMETRY_API_ORIGIN;
  else process.env.GEOMETRY_API_ORIGIN=previous;
  server.closeAllConnections();await new Promise<void>(resolve=>server.close(()=>resolve()));
 }
});
