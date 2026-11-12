'use client';
import Link from 'next/link';
import {ArrowUpRight,BookOpen} from 'lucide-react';
import {browserStorage} from '@/lib/browser-storage';
import {useT} from '@/lib/i18n';
import {cases} from '@/lib/geometry';
import {GeometryBoard} from './board';
import {TopicCards} from './topic-cards';

export function CaseCatalogue(){
 const t=useT();
 return <><div className="section-heading"><div><p className="eyebrow">THE GEOMETRY NOTEBOOK</p><h1><span className="paper-title">{t("探索几何")}</span></h1><p>{t("从一道题开始，探究每个条件的作用。")}</p></div><div className="catalogue-actions"><Link href="/cases/new" className="button primary">{t("新建")}</Link><a className="button secondary" href="https://www.geogebra.org/geometry" target="_blank" rel="noopener noreferrer" aria-label={t("画图（在新标签页打开 GeoGebra）")}>{t("画图")}<ArrowUpRight size={18}/></a></div></div><div className="catalogue-caption"><span>{t("精选题目 / 01—05")}</span></div><div className="case-grid">{t(cases.map((c,i)=><article className={'case-card case-'+i} key={c.id}><span className="tape" aria-hidden="true"/><div className="case-card-top"><span className="case-number">0{t(i+1)}</span><span className="case-tag">{t(c.tag)}</span></div><h2>{t(c.title)}</h2><GeometryBoard problem={c} small readOnly/><p>{t(c.description)}</p><Link href={'/cases/'+c.id} className="case-enter" onClick={()=>browserStorage.removeItem('geometry.draft.'+c.id)}>{t("开始探索")}<ArrowUpRight size={19}/></Link></article>))}<TopicCards/></div><div className="catalogue-note"><BookOpen size={19}/><span>{t("画图是观察的开始；证明需要适用于所有满足条件的图形。")}</span></div></>;
}
