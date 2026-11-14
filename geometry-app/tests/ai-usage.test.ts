import test from 'node:test';
import assert from 'node:assert/strict';
import {cacheHitRate,formatCacheHit,formatElapsed,formatPerSecond,formatTokens} from '../lib/ai-usage';

test('Diagnostics format cache hit, tokens, speed and elapsed time',()=>{
 assert.equal(formatTokens(1234),'1,234');
 assert.equal(formatTokens(undefined),'—');
 assert.equal(cacheHitRate({promptTokens:1000,cachedTokens:250}),0.25);
 assert.equal(formatCacheHit({promptTokens:1000,cachedTokens:250}),'25%');
 assert.equal(formatCacheHit({promptTokens:0,cachedTokens:0}),'—');
 assert.equal(formatCacheHit({promptTokens:1000,cachedTokens:1500}),'100%');
 assert.equal(formatCacheHit({}),'—');
 assert.equal(formatPerSecond({tokensPerSecond:12.34}),'12.3 tok/s');
 assert.equal(formatPerSecond({}),'—');
 assert.equal(formatElapsed(12345),'12.3 秒');
 assert.equal(formatElapsed(undefined),'—');
});
