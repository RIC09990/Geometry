'use client';
import {useEffect,useRef,useState} from 'react';
import {useRouter} from 'next/navigation';
import Link from 'next/link';
import {ArrowLeft,Plus,PenLine,Trash2,ScanLine} from 'lucide-react';
import {api,clone,normalizeDrawingProblem,type Problem,type Relation,type Point,text} from '@/lib/geometry';
import {validateDrawing} from '@/lib/display-constraints';
import {saveTopic,openTopic,readTopicDocument} from '@/lib/topics';
import {topicConfirmationSnapshot,verifyTopicPlacement,type TopicPreview} from '@/lib/topic-layout';
import {attachmentImages,attachmentText,type AiAttachment} from '@/lib/ai-files';
import {useT,useLanguage} from '@/lib/i18n';
import {AiAttachments} from './ai-attachments';
import {AiResponse} from './ai-response';
import {ConditionEditor} from './condition-editor';
import {GeometryBoard} from './board';
import {BoardFrame} from './board-frame';
import {TopicKeyButton,useTopicCredentials} from './topic-key';

type Recognized={problem:Problem|null;recognizedText:string;uncertainties:string[];unsupported:string[];encodingIssues:string[];draft:Record<string,unknown>|null};
export function NewTopic(){
 const t=useT(),router=useRouter(),{language}=useLanguage(),credentials=useTopicCredentials();
 const [files,setFiles]=useState<AiAttachment[]>([]),[description,setDescription]=useState(''),[recognized,setRecognized]=useState<Recognized>(),[problem,setProblem]=useState<Problem>(),[checked,setChecked]=useState(false);
 const [refinement,setRefinement]=useState(''),[dialogue,setDialogue]=useState<{role:string;content:string}[]>([]);
 const [busy,setBusy]=useState(''),[error,setError]=useState(''),[editor,setEditor]=useState<{value?:Relation;goal?:boolean}>();
 const [readingFiles,setReadingFiles]=useState(false);
 const [restoringFile,setRestoringFile]=useState(false),[placementValid,setPlacementValid]=useState(false);
 const [layoutMessage,setLayoutMessage]=useState('');
 const request=useRef<AbortController|undefined>(undefined),sequence=useRef(0),fit=useRef(()=>{});
 const placement=useRef<AbortController|undefined>(undefined),current=useRef<Problem|undefined>(undefined),displayed=useRef<TopicPreview|undefined>(undefined);
 const assign=(value:Problem|undefined)=>{const next=value?normalizeDrawingProblem(value):undefined;current.current=next;setProblem(next)};
 // Imported coordinates are only a sketch. Repair it independently of the
 // confirmation button; an invalid preview must not block access to layout.
 useEffect(()=>{
  if(!problem||validateDrawing(problem,problem.points).valid)return;
  const snapshot=current.current;if(!snapshot||snapshot!==problem)return;
  placement.current?.abort();const abort=new AbortController();placement.current=abort;
  setLayoutMessage(t('正在按全部保留条件生成图形…'));
  void api<{status:string;points?:Point[];message?:string;version:number}>('validate',{problem:snapshot},abort.signal).then(reply=>{
   if(abort.signal.aborted||current.current!==snapshot||placement.current!==abort)return;
   const preview=displayed.current;
   if(preview?.problem===snapshot&&validateDrawing(snapshot,preview.points).valid){assign({...snapshot,points:preview.points});setLayoutMessage('');return}
   if(reply.status==='sat'&&reply.version===snapshot.version&&reply.points&&validateDrawing(snapshot,reply.points).valid){assign({...snapshot,points:reply.points});setLayoutMessage('')}
   else setLayoutMessage(reply.message||t('当前图形尚未通过全部保留条件核验，请继续核对题目。'));
  }).catch(error=>{if(!abort.signal.aborted&&current.current===snapshot)setLayoutMessage((error as Error).message)});
  return()=>abort.abort();
 },[problem]);
 useEffect(()=>()=>{request.current?.abort();placement.current?.abort();sequence.current++},[]);
 useEffect(()=>{request.current?.abort();placement.current?.abort();sequence.current++;setBusy('')},[credentials.key,credentials.mode,credentials.config]);
 const invalidate=()=>{request.current?.abort();placement.current?.abort();sequence.current++;setBusy('');setError('');setPlacementValid(false)};
 const resetRecognition=()=>{invalidate();assign(undefined);displayed.current=undefined;setRecognized(undefined);setChecked(false);setDialogue([]);setRestoringFile(false)};
 function chooseFiles(value:AiAttachment[]){
  resetRecognition();setFiles(value);
  const saved=value.length===1&&value[0].text?readTopicDocument(value[0].text):undefined;
  if(saved){assign(saved);setRestoringFile(true);setRecognized({problem:saved,recognizedText:'已读取保存的题目。请核对条件后继续。',uncertainties:[],unsupported:[],encodingIssues:[],draft:null})}
 }
 const update=(p:Problem)=>{invalidate();assign({...p,version:p.version+1});setChecked(false)};
 async function recognize(refining=false){
  if(readingFiles||(!attachmentImages(files).length&&!description.trim()&&!attachmentText(files))||!credentials.configured)return;
  invalidate();const token=++sequence.current,abort=new AbortController();request.current=abort;setBusy(t(refining?'正在更新题目条件…':'AI 正在识别题目…'));
  try{const reply=await api<Recognized>('ai/import-topic',{images:attachmentImages(files),description:description+attachmentText(files)+(refining?"\n学生本次补充："+refinement:""),currentProblem:refining?problem:undefined,previousText:refining?recognized?.recognizedText:undefined,previousDraft:refining?recognized?.draft:undefined,conversation:refining?dialogue.slice(-16):[],language,keyMode:credentials.mode,...credentials.options},abort.signal,credentials.headers);if(token!==sequence.current||abort.signal.aborted)return;setRecognized(reply);assign(reply.problem||undefined);setChecked(false);setDialogue(old=>[...old,{role:"user",content:refining?refinement:t("请识别这张题目图片。")},{role:"assistant",content:[reply.recognizedText,...reply.uncertainties,...reply.unsupported,...reply.encodingIssues].filter(Boolean).join("\n\n")}]);setRefinement("")}catch(e){if(!abort.signal.aborted)setError((e as Error).message)}finally{if(token===sequence.current)setBusy('')}
 }
 function move(_point:Point,points:Point[]){
  const snapshot=current.current;if(!snapshot||busy)return;
  placement.current?.abort();
  assign({...snapshot,points});
 }
 async function create(){
  if(readingFiles||!problem||!checked||!placementValid)return;
  invalidate();const token=++sequence.current,abort=new AbortController();request.current=abort;setBusy(t('正在核对条件并构造图形…'));
  try{
   const snapshot=topicConfirmationSnapshot(problem,displayed.current);
   const points=await verifyTopicPlacement(snapshot,abort.signal);
   if(token!==sequence.current||abort.signal.aborted)return;
   const id=restoringFile?problem.id:'custom-'+crypto.randomUUID(),value={...clone(snapshot),id,points},time=new Date().toISOString();
   const topic={id,problem:value,recognizedText:recognized?.recognizedText||'',createdAt:time,updatedAt:time};
   openTopic(topic);saveTopic(topic);router.push('/cases/'+id);
  }catch(e){if(!abort.signal.aborted)setError((e as Error).message)}finally{if(token===sequence.current)setBusy('')}
 }
 function renamePoint(old:string,next:string){
  if(!problem||old===next)return;
  if(!/^[A-Z][0-9]?$/.test(next)||problem.points.some(p=>p.id===next)){setError(t('点名请使用 A—Z 或带一位数字的点名，且不能重复。'));return}
  const replace=(ids:string[])=>ids.map(id=>id===old?next:id);
  update({...problem,points:problem.points.map(p=>p.id===old?{...p,id:next}:p),segments:problem.segments.map(s=>({...s,points:replace(s.points)})),circles:problem.circles.map(c=>({...c,center:c.center===old?next:c.center,through:c.through===old?next:c.through,end:c.end===old?next:c.end})),conditions:problem.conditions.map(r=>({...r,args:replace(r.args)})),goal:{...problem.goal,args:replace(problem.goal.args)},nondegenerate:{...problem.nondegenerate,triangles:problem.nondegenerate.triangles.map(replace)}});
 }
 return <><Link className="back-link" href="/cases"><ArrowLeft size={16}/>{t('返回探索')}</Link><div className="section-heading"><div><p className="eyebrow">YOUR GEOMETRY NOTEBOOK</p><h1>{t('新建例题')}</h1><p>{t('上传题目图片或输入题目文字，核对后进入几何拆解。')}</p></div><TopicKeyButton/></div><section className="paper-panel topic-upload"><div className="panel-heading"><h2>{t('1. 上传并识别')}</h2></div><AiAttachments files={files} disabled={!!busy} onChange={chooseFiles} onReadingChange={setReadingFiles}/><label className="field">{t('题目文字或补充说明')}<textarea rows={2} value={description} onChange={e=>{resetRecognition();setDescription(e.target.value)}} placeholder={t('图片不清楚的点名、条件或求证目标，可以在这里补充。')} maxLength={10000}/></label><div className="topic-confirm-actions"><button className="button primary" disabled={readingFiles||!!busy||(!attachmentImages(files).length&&!description.trim()&&!attachmentText(files))||!credentials.configured} onClick={()=>void recognize()}><ScanLine size={17}/>{t(recognized?'重新识别':'AI 识别题目')}</button>{busy&&<span role="status"><span className="spinner"/>{busy}</span>}{!credentials.configured&&!restoringFile&&<small>{t('请先填写 API Key，与 AI 页共用。')}</small>}</div></section>
 {recognized&&<section className="paper-panel topic-recognition"><details open={!recognized.problem}><summary>{t('查看识别出的原题文字')}</summary><p>{recognized.recognizedText}</p></details>{!!recognized.uncertainties.length&&<div className="topic-notices"><strong>{t('请重点核对')}</strong><ul>{recognized.uncertainties.map((s,i)=><li key={i}>{s}</li>)}</ul></div>}{!!recognized.unsupported.length&&<div className="topic-notices warning"><strong>{t('已保留为文字条件，可继续让 AI 解答')}</strong><ul>{recognized.unsupported.map((s,i)=><li key={i}>{s}</li>)}</ul></div>}{!!recognized.encodingIssues.length&&<div className="topic-notices"><strong>{t("还有这些内容需要补齐")}</strong><ul>{recognized.encodingIssues.map((s,i)=><li key={i}>{s}</li>)}</ul></div>}</section>}
 {(!!attachmentImages(files).length||!!description.trim()||!!recognized)&&<section className="paper-panel topic-dialogue"><h2>{t('和 AI 核对题目')}</h2><div className="topic-dialogue-log" role="log">{dialogue.map((item,i)=><div key={i} className={'topic-dialogue-'+item.role}><small>{item.role==='user'?t('你'):t('Geometry小助手')}</small><AiResponse content={item.content}/></div>)}</div><label className="field">{t('告诉 AI 要补充或修改什么')}<textarea value={refinement} onChange={e=>setRefinement(e.target.value)} rows={3} maxLength={10000} placeholder={t('例如：图里没读清楚，D 是 BC 的中点，请加上这个条件。')}/></label><button className="button secondary" disabled={readingFiles||!refinement.trim()||!!busy||!credentials.configured} onClick={()=>void recognize(true)}>{t('发送给 AI 并更新条件')}</button></section>}
 {problem&&<><div className="work-grid topic-preview"><BoardFrame onFit={()=>fit.current()} title="识别后的图形"><GeometryBoard problem={problem} placementMessage={layoutMessage} measurements onConstraintState={valid=>{setPlacementValid(valid);if(!valid)displayed.current=undefined}} onDragStart={()=>{placement.current?.abort()}} readOnly={!!busy} onPreview={points=>{displayed.current={problem,points}}} onMove={move} onReady={f=>fit.current=f}/></BoardFrame><div className="work-details"><section className="paper-panel"><h2>{t('2. 核对条件')}</h2><label className="field">{t('题目名称')}<input value={problem.title} maxLength={80} onChange={e=>update({...problem,title:e.target.value})}/></label><div className="conditions-list">{problem.conditions.map(r=><div className="editable-condition" key={r.id}><span className="math">{t(text(r))}</span><button className="icon-button" aria-label={t('编辑条件')+' '+text(r)} onClick={()=>setEditor({value:r})}><PenLine size={15}/></button><button className="icon-button" aria-label={t('删除条件')+' '+text(r)} onClick={()=>update({...problem,conditions:problem.conditions.filter(c=>c.id!==r.id)})}><Trash2 size={15}/></button></div>)}</div><button className="text-button" onClick={()=>setEditor({})}><Plus size={15}/>{t('添加条件')}</button><details className="topic-domain"><summary>{t('点名与非退化要求')}</summary><div className="topic-point-names">{problem.points.map(p=><label className="field" key={p.id}>{p.id}<input aria-label={t('点名')+' '+p.id} defaultValue={p.id} maxLength={2} onBlur={e=>{const next=e.target.value.trim().toUpperCase();if(!/^[A-Z][0-9]?$/.test(next)||problem.points.some(q=>q.id===next&&q.id!==p.id))e.target.value=p.id;renamePoint(p.id,next)}}/></label>)}</div><label><input type="checkbox" checked={problem.nondegenerate.distinct} onChange={e=>update({...problem,nondegenerate:{...problem.nondegenerate,distinct:e.target.checked}})}/>{t('各点互不重合')}</label>{problem.nondegenerate.triangles.map((triangle,i)=><div className="topic-triangle" key={i}>△{triangle.map((id,j)=><select key={j} aria-label={t('非退化三角形顶点')+' '+i+' '+j} value={id} onChange={e=>update({...problem,nondegenerate:{...problem.nondegenerate,triangles:problem.nondegenerate.triangles.map((row,k)=>k===i?row.map((a,b)=>b===j?e.target.value:a):row)}})}>{problem.points.map(p=><option key={p.id}>{p.id}</option>)}</select>)}{t('非退化')}<button className="icon-button" aria-label={t('删除非退化要求')} onClick={()=>update({...problem,nondegenerate:{...problem.nondegenerate,triangles:problem.nondegenerate.triangles.filter((_,j)=>i!==j)}})}><Trash2 size={14}/></button></div>)}<button className="text-button" onClick={()=>update({...problem,nondegenerate:{...problem.nondegenerate,triangles:[...problem.nondegenerate.triangles,problem.points.slice(0,3).map(p=>p.id)]}})}>{t('添加非退化三角形')}</button></details></section><section className="paper-panel"><div className="panel-heading"><h2>{t('3. 核对求证目标')}</h2><button className="text-button" onClick={()=>setEditor({value:problem.goal,goal:true})}><PenLine size={15}/>{t('编辑目标')}</button></div><strong className="math">{t(text(problem.goal))}</strong></section></div></div><div className="paper-panel topic-create"><label><input type="checkbox" checked={checked} onChange={e=>setChecked(e.target.checked)} disabled={!!busy}/>{t('我已核对点名、全部条件和求证目标。')}</label><button className="button primary" onClick={()=>void create()} disabled={readingFiles||!checked||!placementValid||!!busy||!problem.title.trim()}>{t('确认并进入几何拆解')}</button></div></>}
 {error&&<p className="topic-error" role="alert">{error}</p>}{editor&&problem&&<ConditionEditor points={problem.points} value={editor.value} title={editor.goal?'编辑求证目标':'编辑条件'} onClose={()=>setEditor(undefined)} onSave={r=>{update(editor.goal?{...problem,goal:{...r,id:problem.goal.id}}:{...problem,conditions:editor.value?problem.conditions.map(c=>c.id===r.id?r:c):[...problem.conditions,r]});setEditor(undefined)}}/>}</>;
}
