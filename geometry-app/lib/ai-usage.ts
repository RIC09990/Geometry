export type AiUsage={
 promptTokens?:number;cachedTokens?:number;completionTokens?:number;reasoningTokens?:number;
 firstTokenMs?:number|null;elapsedMs?:number;generationMs?:number;tokensPerSecond?:number;
};

export function formatTokens(value?:number|null):string{
 return typeof value==='number'&&Number.isFinite(value)?value.toLocaleString('en-US'):'—';
}

/** Share of the prompt served from cache, or null when the provider did not report it. */
export function cacheHitRate(usage?:AiUsage):number|null{
 const prompt=usage?.promptTokens,cached=usage?.cachedTokens;
 if(typeof prompt!=='number'||typeof cached!=='number'||prompt<=0)return null;
 return Math.min(1,Math.max(0,cached/prompt));
}

export function formatCacheHit(usage?:AiUsage):string{
 const rate=cacheHitRate(usage);
 return rate===null?'—':Math.round(rate*100)+'%';
}

export function formatPerSecond(usage?:AiUsage):string{
 return typeof usage?.tokensPerSecond==='number'?usage.tokensPerSecond.toFixed(1)+' tok/s':'—';
}

export function formatElapsed(milliseconds?:number):string{
 return typeof milliseconds==='number'&&Number.isFinite(milliseconds)?(milliseconds/1000).toFixed(1)+' 秒':'—';
}
