'use client';
import {browserStorage} from '@/lib/browser-storage';
import {useT} from '@/lib/i18n';
import Link from 'next/link';
import {useLanguage} from '@/lib/i18n';
import {lazy,Suspense,useEffect,useState} from 'react';
import {BookOpen,User,Settings,Shield,Database,FileText,Mail,ArrowUpRight,ArrowLeft,Copy,Clock,Network,ScanLine,Triangle,ChevronRight,Check} from 'lucide-react';
import {type RecordEntry,readRecords,outcomeText} from '@/lib/geometry';
import {Modal} from './common';
import {SideNavigation} from './navigation';
import {AiBrandMark,AiGlassMaterial} from './ai-material';

// Keep the shared shell and homepage independent of the editor, geometry engine and math renderer.
const CaseCatalogue=lazy(()=>import('./case-catalogue').then(module=>({default:module.CaseCatalogue})));
const Workspace=lazy(()=>import('./workspace').then(module=>({default:module.Workspace})));
const AiChat=lazy(()=>import('./ai-chat').then(module=>({default:module.AiChat})));
const NewTopic=lazy(()=>import('./new-topic').then(module=>({default:module.NewTopic})));

function PageLoading(){
 const {language}=useLanguage();
 return <p className="muted" role="status" style={{padding:'24px 0'}}>{language==='en'?'Loading…':'正在加载…'}</p>;
}

type Page='home'|'cases'|'workspace'|'about'|'about-detail'|'ai'|'new';
export type Preferences={labels:boolean;reduceMotion:boolean};
export function GeometryApp({page,caseId,aboutId}:{page:Page;caseId?:string;aboutId?:string}){
 const t=useT();
 const {language,setLanguage}=useLanguage();
 const [panel,setPanel]=useState<'user'|'settings'|null>(null);const [records,setRecords]=useState<RecordEntry[]>([]);const [prefs,setPrefs]=useState<Preferences>({labels:true,reduceMotion:false});const [notice,setNotice]=useState('');
 useEffect(()=>{const update=()=>setRecords(readRecords());update();window.addEventListener('geometry-records',update);try{const p=JSON.parse(browserStorage.getItem('geometry.settings.v1')||'null');if(p){const clean={labels:p.labels!==false,reduceMotion:!!p.reduceMotion};setPrefs(clean);browserStorage.setItem('geometry.settings.v1',JSON.stringify(clean))}}catch{};return()=>window.removeEventListener('geometry-records',update)},[]);
 useEffect(()=>{if(!notice)return;const t=setTimeout(()=>setNotice(''),6000);return()=>clearTimeout(t)},[notice]);
 const savePrefs=(p:Preferences)=>{setPrefs(p);try{browserStorage.setItem('geometry.settings.v1',JSON.stringify(p))}catch{setNotice(t("浏览器没有允许保存设置。"))}};
 const isAbout=page==='about'||page==='about-detail';
 const style=page==='ai'?'ai':page==='home'?'glass':isAbout?'stijl':'scrap';
 return <div className={`app theme-${style} ${prefs.reduceMotion?'reduce-motion':''}`}>
  <div className="page-background" aria-hidden="true">{t(isAbout&&<div className="stijl-composition"><span className="stijl-piece piece-blue"/><span className="stijl-piece piece-red"/><span className="stijl-piece piece-yellow"/><span className="stijl-piece piece-small-blue"/><span className="stijl-piece piece-bottom-red"/><span className="stijl-grid-lines"/></div>)}</div>
  {page==='ai'&&<AiGlassMaterial/>}
  <div className="app-frame">
   <header className="topbar"><Link href="/" className="brand" aria-label={t("Geometry 首页")}><span className="brand-symbol" aria-hidden="true">{t(page==='ai'?<AiBrandMark/>:style==='glass'?<span className="glass-orb"/>:isAbout?<span className="stijl-logo"/>:<Triangle size={28} strokeWidth={1.6}/>)}</span><span>Geometry</span></Link><div className="header-note">{t("条件 · 推理 · 发现")}</div><div className="account-actions"><button aria-label={t('用户')} onClick={()=>setPanel('user')}><User size={21}/><span>{t("用户")}</span></button><span className="header-divider"/><button aria-label={t('设置')} onClick={()=>setPanel('settings')}><Settings size={21}/><span>{t("设置")}</span></button></div></header>
   <aside className="sidebar"><SideNavigation activeIndex={page==='home'?0:page==='ai'?1:isAbout?3:2} reduceMotion={prefs.reduceMotion}/><div className="sidebar-bottom"><span>{t("每一个条件")}<br/>{t("都有它的意义。")}</span><small>GEOMETRY EXPLORER</small></div></aside>
   <main key={page+':'+(caseId||aboutId||'')} className={'main-content page-'+page}>
    <Suspense fallback={<PageLoading/>}>
    {t(page==='home'&&<HomePage records={records}/>)}
    {t(page==='cases'&&<CaseCatalogue/>)}
    {t(page==='about'&&<AboutPage/>)}
    {t(page==='about-detail'&&<AboutDetail aboutId={aboutId!} notify={setNotice}/>)}
    {t(page==='ai'&&<AiChat/>)}
    {page==='new'&&<NewTopic/>}
    {t(page==='workspace'&&<Workspace key={caseId} caseId={caseId!} notify={setNotice} prefs={prefs}/>)}
    </Suspense>
   </main>
  </div>
  {t(panel==='user'&&<Modal title={t("我的探究")} onClose={()=>setPanel(null)}><div className="visitor"><User size={28}/><div><strong>{t("本机访客")}</strong><p>{t("在当前浏览器查看你的探究记录")}</p></div></div><p className="muted">{t("账号与跨设备同步将在后续版本提供。")}</p><div className="record-list">{t(records.length?records.map(r=><Link key={r.key} href={'/cases/'+encodeURIComponent(r.problem.id)} onClick={()=>{browserStorage.setItem('geometry.draft.'+r.problem.id,JSON.stringify(r.problem));setPanel(null)}}><div><strong>{t(r.name)}</strong><small>{t(r.saved?t("已保存变式"):t("最近探究"))} · {t(new Date(r.time).toLocaleString('zh-CN'))}</small></div><ChevronRight size={18}/></Link>):<div className="empty"><BookOpen size={32}/><p>{t("还没有探究记录")}</p><small>{t("分析题目或保存变式后，会出现在这里。")}</small></div>)}</div></Modal>)}
  {t(panel==='settings'&&<Modal title={t("设置")} onClose={()=>setPanel(null)}><div className="settings-list"><label><span><strong>{t("语言")}</strong><small>{t("选择界面语言")}</small></span><select aria-label={t("语言")} value={language} onChange={e=>setLanguage(e.target.value as 'zh'|'en')}><option value="zh">{t("中文")}</option><option value="en">English</option></select></label>{t([{key:'labels',title:t("显示点的标签"),desc:t("在几何画板中显示 A、B、C 等点名")},{key:'reduceMotion',title:t("减少动态效果"),desc:t("减少界面和首页装饰的动画")}].map(s=><label key={s.key}><span><strong>{t(s.title)}</strong><small>{t(s.desc)}</small></span><input type="checkbox" checked={prefs[s.key as keyof Preferences]} onChange={e=>savePrefs({...prefs,[s.key]:e.target.checked})}/></label>))}</div><button className="button secondary" onClick={()=>{savePrefs({labels:true,reduceMotion:false});setLanguage('zh');setNotice("已恢复默认设置")}}>{t("恢复默认设置")}</button></Modal>)}
  {t(notice&&<div role="status" aria-live="polite" className="toast">{t(notice)}</div>)}
 </div>;
}

function HomePage({records}:{records:RecordEntry[]}){
 const t=useT();
 const completed=new Set(records.filter(r=>r.result&&['proven','counterexample'].includes(r.result.outcome)).map(r=>r.problem.id)).size;
 return <><div className="home-heading"><p className="eyebrow">A DIFFERENT WAY TO SEE GEOMETRY</p><h1>{t("当条件改变，")}<br className="mobile-break"/>{t("证明会怎样？")}</h1><p>{t("探索条件、推理与结论之间的关系")}</p></div><div className="home-grid"><div className="glass-art"><img className="mobius-art" src="/mobius-strip.8a40908e2ab6.webp" width="1086" height="1448" alt={t("黑白银色莫比乌斯环艺术图")} fetchPriority="high" decoding="async"/><div className="art-caption"><span>{t("从一个图形，走向一条推理。")}</span><span>01 / ∞</span></div></div><section className="feature-glass"><h2>{t("你可以做什么")}</h2>{t([{Icon:Triangle,title:t("观察图形"),desc:t("拖动动点，观察图形中的关系如何变化。")},{Icon:Network,title:t("追踪证明"),desc:t("看见每一步依据，理解条件如何共同作用。")},{Icon:ScanLine,title:t("检验结论"),desc:t("尝试不同证明，寻找并核验反例。")}].map(({Icon,title,desc})=><div className="feature" key={title}><Icon size={30}/><div><h3>{t(title)}</h3><p>{t(desc)}</p></div></div>))}<div className="feature-footnote">{t("在左侧「探索」中开始你的探究。")}</div></section><div className="home-right"><section className="progress-glass"><h2>{t("学习进度")}</h2>{t(completed?<><div className="progress-ring"><strong>{t(completed)}</strong><small>{t("道已探究题目")}</small></div><p className="muted">{t("根据本机真实记录统计")}</p></>:<><div className="progress-ring empty-ring"><span>{t("尚未开始")}</span></div><p className="muted">{t("完成探究后，进度会记录在这里。")}</p></>)}</section><section className="recent-glass"><h2><Clock size={21}/>{t("最近探究")}</h2>{t(records.length?<div className="recent-items">{t(records.slice(0,2).map(r=><Link key={r.key} href={'/cases/'+r.problem.id} onClick={()=>browserStorage.setItem('geometry.draft.'+r.problem.id,JSON.stringify(r.problem))}><strong>{t(r.name)}</strong><small>{t(r.result?outcomeText[r.result.outcome]:t("已保存"))}<ArrowUpRight size={15}/></small></Link>))}</div>:<div className="recent-empty"><span>{t("暂无记录")}</span><small>{t("每一次尝试，都值得留下。")}</small></div>)}</section></div></div><p className="home-bottom">{t("没有找到证明，不等于结论错误。原证明失效，也不等于结论错误。")}</p></>;
}

const aboutEntries=[
 {id:'privacy',title:'隐私政策',Icon:Shield,color:'red',description:'内容待完善'},
 {id:'data',title:'数据使用',Icon:Database,color:'yellow',description:'内容待完善'},
 {id:'terms',title:'使用条款',Icon:FileText,color:'blue',description:'内容待完善'},
 {id:'contact',title:'联系我们',Icon:Mail,color:'white',description:'微信联系 · ric09990'},
];
function AboutPage(){
 const t=useT();
 return <><div className="stijl-header"><p className="eyebrow">ABOUT GEOMETRY</p><h1>{t("说明")}<span className="title-dot"/></h1><p>{t("关于规则、数据与这个项目。")}</p></div><div className="about-grid">{t(aboutEntries.map(({id,title,Icon,color,description},i)=><Link key={id} href={'/about/'+id} className={'about-block about-'+color}><div className="about-block-head"><span>0{t(i+1)} / GEOMETRY</span><Icon size={32}/></div><h2>{t(title)}</h2><div className="about-placeholder"><span className="tiny-rule"/>{t(description)}</div><div className="about-card-action"><span>{t(id==='contact'?t("查看联系方式"):t("查看详情"))}</span><ArrowUpRight size={22}/></div></Link>))}</div><p className="about-footer"><Check size={16}/>{t("政策与条款待完善，点击卡片可查看对应内容。")}</p></>;
}
function AboutDetail({aboutId,notify}:{aboutId:string;notify:(s:string)=>void}){
 const t=useT();
 const entry=aboutEntries.find(e=>e.id===aboutId)!;
 const [copied,setCopied]=useState(false);
 const Icon=entry.Icon;
 async function copyContact(){try{await navigator.clipboard.writeText('ric09990');setCopied(true);notify(t("微信号已复制：ric09990"))}catch{notify(t("复制未成功，请手动复制微信号 ric09990。"))}}
 return <><Link className="back-link about-back" href="/about"><ArrowLeft size={16}/>{t("返回说明")}</Link><div className="stijl-header detail-heading"><p className="eyebrow">GEOMETRY / {t(aboutId.toUpperCase())}</p><h1>{t(entry.title)}<span className="title-dot"/></h1></div><section className={'about-detail-paper about-'+entry.color}><div className="about-detail-icon"><Icon size={36}/><span>GEOMETRY · {t(entry.title)}</span></div>{t(aboutId==='contact'?<><h2>{t("通过微信联系我们")}</h2><p className="contact-label">{t("微信号")}</p><div className="contact-row"><span className="wechat-id">ric09990</span><button className="button primary contact-copy" onClick={copyContact}>{t(copied?<Check size={18}/>:<Copy size={18}/>)} {t(copied?t("已复制微信号"):t("复制微信号"))}</button></div><p className="contact-help">{t("在微信中搜索这个微信号，即可添加联系。")}</p></>:<div className="policy-pending"><span className="pending-mark">···</span><h2>{t("内容待完善")}</h2><p>{t(entry.title)}{t("的具体内容尚未确定，确认后将在此处更新。")}</p></div>)}</section></>;
}
