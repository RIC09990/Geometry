import test from 'node:test';
import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
import React from 'react';
import {renderToReadableStream} from 'react-dom/server';

const loaded=new Set();
registerHooks({
 resolve(specifier,context,next){
  // Match the production framework aliases without starting a second web server.
  if(specifier==='next/link'||specifier==='next/navigation')return {url:pathToFileURL(path.resolve('node_modules/vinext/dist/shims/'+specifier.slice(5)+'.js')).href,shortCircuit:true};
  return next(specifier,context);
 },
 load(url,context,next){loaded.add(url);return next(url,context)},
});
const {GeometryApp}=await import('../components/geometry/app.tsx');
const {AppRouterContext}=await import(pathToFileURL(path.resolve('node_modules/vinext/dist/shims/internal/app-router-context.js')).href);
const router={push(){},replace(){},refresh(){},back(){},forward(){},prefetch(){}};
async function renderPage(page,props={}){
 const errors=[];
 const tree=React.createElement(AppRouterContext.Provider,{value:router},React.createElement(GeometryApp,{page,...props}));
 const stream=await renderToReadableStream(tree,{onError:error=>{errors.push(error)}});
 await stream.allReady;
 const html=await new Response(stream).text();
 assert.deepEqual(errors,[],`${page} must resolve without a lazy import or server render error`);
 for(const href of ['/','/ai','/cases','/about'])assert.ok(html.includes('href="'+href+'"'),`${page} must retain navigation to ${href}`);
 return html;
}

test('Homepage renders without loading the editor, proof checker, math renderer or geometry board',async()=>{
 const html=await renderPage('home');
 assert.match(html,/当条件改变/);
 assert.match(html,/mobius-strip\.[a-f0-9]+\.webp/);
 assert.match(html,/theme-glass/);
 for(const file of ['ai-chat','workspace','new-topic','case-catalogue','board','ai-response'])assert.equal([...loaded].some(url=>url.endsWith('/components/geometry/'+file+'.tsx')),false,`${file} must remain outside the homepage import path`);
});
test('Deferred pages resolve in SSR and retain their original route content',async()=>{
 for(const [page,props,expected,theme] of [
  ['cases',{},'探索几何','scrap'],
  ['ai',{},'今天研究什么','ai'],
  ['new',{},'新建例题','scrap'],
  ['workspace',{caseId:'isosceles'},'正在打开探究','scrap'],
  ['about',{},'隐私政策','stijl'],
  ['about-detail',{aboutId:'contact'},'ric09990','stijl'],
 ]){
  const html=await renderPage(page,props);
  assert.ok(html.includes(expected),`${page} must retain ${expected}`);
  assert.ok(html.includes('theme-'+theme),`${page} must retain its original theme`);
 }
});
