'use client';
import {Network} from 'lucide-react';
import {useT} from '@/lib/i18n';
import {text,type Problem,type Proof} from '@/lib/geometry';
import {AiResponse} from './ai-response';
import {MathText} from './math-text';

export function ProofView({proof,problem,conditionNames}:{proof:Proof;problem:Problem;conditionNames:Map<string,string>}){
 const t=useT();
 return <div className="proof-view">{proof.id.startsWith("ai-")&&<p className={"ai-proof-label "+proof.status}>{t(proof.status==="verified"?"AI 路线：列出的关系逐步核验通过，文字说明仍需阅读核对。":"AI 候选路线：有些步骤尚未核验或未通过，请检查依据。")}</p>}<ol className="proof-steps">{t(proof.steps.map((s,i)=><li key={s.id}><span className="step-number">{t(i+1)}</span><div><div className="math step-statement">{proof.id.startsWith("ai-")?<AiResponse content={s.statement}/>:<MathText text={t(s.statement)}/>}</div>{proof.id.startsWith("ai-")?<div className="step-rule"><AiResponse content={t(s.rule||'')} showCopy={false} style={{fontSize:10,color:'#a28c6b'}}/></div>:<small><MathText text={t(s.rule||'')}/></small>}{s.checkStatus&&<small className={"step-check "+s.checkStatus}>{s.checkedRelation&&<span className="math"><MathText text={t(text(s.checkedRelation))}/> · </span>}{t(s.checkStatus==="verified"?"本步关系已核验":s.checkStatus==="counterexample"?"所列依据不能推出本步":s.checkStatus==="inconsistent"?"所列依据互相矛盾":"本步尚未完成形式化核验")}</small>}<details className="dependencies"><summary><Network size={13}/>{t("查看依赖")}</summary><div className="joint-premises">{t(s.premises.length?s.premises.map(id=>{const r=problem.conditions.find(r=>r.id===id);const n=[...proof.steps,...proof.assumptionNodes].find(n=>n.id===id);return <span key={id} className={(r?!r.enabled:conditionNames.has(id))?'missing-premise':''}><MathText text={t(r?text(r):n?.statement||conditionNames.get(id)||(id==='domain'?t('非退化与点互异要求'):id))}/></span>}):<span>{t("公共关系／自反性")}</span>)}</div><small>{t("以上前提共同支持这一步。")}</small></details></div></li>))}</ol></div>;
}
