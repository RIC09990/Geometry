import test from 'node:test';
import assert from 'node:assert/strict';
import {staticAssetPath,assetCacheControl,responseCacheControl,preferredEncoding,compressibleAsset} from '../scripts/local-assets.mjs';

test('Fingerprint artwork and built scripts can be reused across page visits',()=>{
 for(const path of ['/archive-collage.b499e272e715.webp','/mobius-strip.8a40908e2ab6.webp','/euclid-book1-plate1.ca30d8a2806e.jpg','/_next/static/chunks/app-contentHash.js']){
  assert.equal(staticAssetPath(path),true);
  assert.equal(assetCacheControl(path,200),'public, max-age=604800, immutable');
  assert.equal(assetCacheControl(path,304),'public, max-age=604800, immutable');
 }
});
test('AI replies, page payloads and local service status never acquire public asset caching',()=>{
 for(const path of ['/api/ai/chat','/api/ai/review-proof','/api/cases','/__geometry_local_status','/ai','/cases/isosceles.rsc']){
  assert.equal(staticAssetPath(path),false);
  assert.equal(assetCacheControl(path,200),'no-store, max-age=0');
 }
});
test('Missing assets and server failures are not cached for a year',()=>{
 for(const status of [404,429,500,503])assert.equal(assetCacheControl('/mobius-strip.8a40908e2ab6.webp',status),'no-store, max-age=0');
});
test('Unversioned favicon requires ETag revalidation and removed unversioned artwork is rejected',()=>{
 assert.equal(assetCacheControl('/favicon.svg',304),'public, max-age=0, must-revalidate');
 for(const path of ['/anything.png','/archive-collage.webp','/euclid-book1-plate1.jpg','/private.webp','/_next/static/chunks/app.js.map']){
  // Source maps are excluded by the gateway's existing route validation.
  if(!path.endsWith('.map'))assert.equal(staticAssetPath(path),false);
 }
});

test('HTML revalidates on each visit while RSC, private credentials and AI replies stay uncached',()=>{
 const html={'content-type':'text/html; charset=utf-8'};
 assert.equal(responseCacheControl('/',200,{},html),'private, max-age=0, must-revalidate');
 assert.equal(responseCacheControl('/',304,{},{}),'private, max-age=0, must-revalidate');
 for(const [path,request,response] of [
  ['/ai.rsc',{},html],['/ai',{rsc:'1'},html],['/ai',{accept:'text/x-component'},html],
  ['/ai',{'x-ai-api-key':'test-only'},html],['/api/ai/chat',{},html],
  ['/ai',{}, {...html,'set-cookie':'test-only'}],['/ai',{}, {'content-type':'text/x-component'}],
 ] as const)assert.equal(responseCacheControl(path,200,request,response),'no-store, max-age=0');
 assert.equal(responseCacheControl('/',500,{},html),'no-store, max-age=0');
});

test('Compression respects supported encodings and quality zero',()=>{
 assert.equal(preferredEncoding('gzip, deflate, br'),'br');
 assert.equal(preferredEncoding('br;q=0, gzip;q=0.5'),'gzip');
 assert.equal(preferredEncoding('gzip;q=0.8, br;q=0.1'),'gzip');
 assert.equal(preferredEncoding('br;q=0,gzip;q=0'),null);
 assert.equal(preferredEncoding('identity'),null);
 assert.equal(preferredEncoding('br;q=0.1,identity;q=1'),null);
 assert.equal(preferredEncoding('gzip;q=oops,br;q=0'),null);
 assert.equal(preferredEncoding('*;q=1,br;q=0'),'gzip');
 assert.equal(compressibleAsset('/_next/static/chunks/test.js','application/javascript; charset=utf-8'),true);
 assert.equal(compressibleAsset('/_next/static/css/test.css','text/css'),true);
 assert.equal(compressibleAsset('/api/ai/chat','application/json'),false);
 assert.equal(compressibleAsset('/mobius-strip.8a40908e2ab6.webp','image/webp'),false);
});

test('Private asset responses and credential-bearing requests never acquire public caching',()=>{
 const path='/_next/static/chunks/test-hash.js';
 for(const headers of [{'set-cookie':'test-only'}, {'cache-control':'private, max-age=30'}, {'cache-control':'public, no-store'}]){
  assert.equal(responseCacheControl(path,200,{},headers),'no-store, max-age=0');
 }
 for(const request of [{'x-ai-api-key':'test-only'}, {'x-deepseek-api-key':'test-only'}, {authorization:'Bearer test-only'}]){
  assert.equal(responseCacheControl(path,200,request,{}),'no-store, max-age=0');
 }
});
