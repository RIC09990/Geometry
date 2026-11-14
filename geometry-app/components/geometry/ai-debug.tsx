'use client';
import {useEffect,useRef} from 'react';
import {useT} from '@/lib/i18n';
import {formatCacheHit,formatElapsed,formatPerSecond,formatTokens,type AiUsage} from '@/lib/ai-usage';

/** Collapsible model reasoning. It opens when the model starts thinking and stays open. */
export function AiThinking({reasoning,streaming}:{reasoning:string;streaming?:boolean}){
 const t=useT(),ref=useRef<HTMLDetailsElement>(null);
 useEffect(()=>{if(streaming&&ref.current)ref.current.open=true},[streaming]);
 return <details className="ai-think" ref={ref}>
  <summary>{t('思考过程')} · {reasoning.length} {t('字')}{streaming?' · '+t('正在思考…'):''}</summary>
  <pre>{reasoning}</pre>
 </details>;
}

export function AiElapsed({milliseconds}:{milliseconds:number}){
 const t=useT();
 return <small className="ai-elapsed">{t('用时')} {formatElapsed(milliseconds)}</small>;
}

export function AiDebugBar({usage,status}:{usage?:AiUsage;status?:string}){
 const t=useT();
 const label=status==='searching'?t('正在检索资料…'):status==='verifying'?t('正在复核…'):status==='retrying'?t('正在重新生成…'):'';
 const uncached=typeof usage?.promptTokens==='number'&&typeof usage?.cachedTokens==='number'?usage.promptTokens-usage.cachedTokens:usage?.promptTokens;
 return <div className="ai-debug" aria-live="off">
  {label&&<span className="ai-debug-status">{label}</span>}
  {usage?<>
   <span>{t('缓存命中')} {formatCacheHit(usage)}</span>
   <span>{formatPerSecond(usage)}</span>
   <span>{t('输入')} {formatTokens(uncached)} tok</span>
   <span>{t('输出')} {formatTokens(usage.completionTokens)} tok</span>
   <span>{t('上下文')} {formatTokens(usage.promptTokens)} tok</span>
  </>:<span>{t('本轮无统计')}</span>}
 </div>;
}
