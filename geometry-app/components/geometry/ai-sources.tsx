import {useT} from '@/lib/i18n';
export type SearchReply={sources?:{title:string;url:string}[];searchStatus?:string|null};
export function AiSources({sources,searchStatus}:SearchReply){
 const t=useT();if(!searchStatus)return null;
 return <div className="ai-sources">{searchStatus==='unavailable'?<small>{t('联网搜索暂时不可用，本次回复未使用网页资料。')}</small>:searchStatus==='empty'?<small>{t('本次未搜到相关网页。')}</small>:<><small>{t('参考网页')}</small>{sources?.map((s,i)=><a key={s.url+i} href={s.url} target="_blank" rel="noopener noreferrer">{i+1}. {s.title||s.url}</a>)}</>}</div>;
}
