import test from 'node:test';
import assert from 'node:assert/strict';
import {migrateLocalTopics} from '../lib/topics';
import {browserStorage} from '../lib/browser-storage';

test('Failed topic migration keeps unsaved topics and concurrent callers share one retry',async()=>{
 const priorFetch=globalThis.fetch,priorGet=browserStorage.getItem,priorSet=browserStorage.setItem,priorRemove=browserStorage.removeItem;
 const topics=[{id:'custom-one',problem:{title:'一'}},{id:'custom-two',problem:{title:'二'}}];
 let raw:string|null=JSON.stringify(topics),fail=true;
 const saved:string[]=[];
 browserStorage.getItem=()=>raw;
 browserStorage.setItem=(_key,value)=>{raw=value};
 browserStorage.removeItem=()=>{raw=null};
 globalThis.fetch=async(_url,init)=>{
  const topic=JSON.parse(String(init?.body));
  if(fail&&topic.id==='custom-two')return Response.json({detail:'不可用'},{status:503});
  saved.push(topic.id);return Response.json(topic);
 };
 try{
  const first=migrateLocalTopics(),concurrent=migrateLocalTopics();
  assert.equal(first,concurrent);
  assert.equal(await first,1);
  assert.deepEqual(JSON.parse(raw!),[topics[1]]);
  fail=false;assert.equal(await migrateLocalTopics(),1);
  assert.equal(raw,null);
  assert.deepEqual(saved,['custom-one','custom-two']);
 }finally{
  globalThis.fetch=priorFetch;browserStorage.getItem=priorGet;browserStorage.setItem=priorSet;browserStorage.removeItem=priorRemove;
 }
});
