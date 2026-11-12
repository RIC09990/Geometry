'use client';
import {useState} from 'react';
import {type Point,type Relation,text} from '@/lib/geometry';
import {useT} from '@/lib/i18n';
import {Modal} from './common';

const relations:Record<string,{label:string;fields:string[]}>= {
 fixed_point:{label:'点的固定坐标',fields:['这个点']},
 equal_length:{label:'两条线段相等',fields:['第一条线段的起点','第一条线段的终点','第二条线段的起点','第二条线段的终点']},
 midpoint:{label:'一点是线段中点',fields:['中点','线段起点','线段终点']},
 perpendicular:{label:'两条直线垂直',fields:['第一条直线经过','和点','第二条直线经过','和点']},
 parallel:{label:'两条直线平行',fields:['第一条直线经过','和点','第二条直线经过','和点']},
 collinear:{label:'三个点在同一直线上',fields:['点一','点二','点三']},
 on_segment:{label:'点在线段上（不含端点）',fields:['这个点','线段起点','线段终点']},
 inside_triangle:{label:'点在三角形内部（不含边界）',fields:['内点','三角形顶点一','三角形顶点二','三角形顶点三']},
 inside_circle:{label:'点在圆内（不含圆周）',fields:['这个点','圆心','确定半径的点']},
 outside_circle:{label:'点在圆外（不含圆周）',fields:['这个点','圆心','确定半径的点']},
 same_side:{label:'两点在直线同侧',fields:['点一','点二','直线经过','和点']},
 opposite_side:{label:'两点在直线异侧',fields:['点一','点二','直线经过','和点']},
 equal_angle:{label:'两个角相等',fields:['第一个角的一边经过','第一个角的顶点','另一边经过','第二个角的一边经过','第二个角的顶点','另一边经过']},
 on_circle:{label:'一点在圆上',fields:['圆上的点','圆心','圆经过的另一个点']},
 length_ratio:{label:'两条线段的长度比',fields:['第一条线段的起点','第一条线段的终点','第二条线段的起点','第二条线段的终点']},
 similar_triangles:{label:'两个三角形相似',fields:['第一个三角形顶点一','第一个三角形顶点二','第一个三角形顶点三','对应顶点一','对应顶点二','对应顶点三']},
 fixed_angle:{label:'角的度数',fields:['角的一边经过','角的顶点','另一边经过']},
 angle_value:{label:'求一个角的度数',fields:['角的一边经过','角的顶点','另一边经过']},
 fixed_length:{label:'线段的数值长度',fields:['线段起点','线段终点']},
 on_arc:{label:'一点在圆弧上',fields:['圆弧上的点','圆心','圆弧起点','圆弧终点']},
 minimize:{label:'线段长度和的最小值',fields:[]},
 free_text:{label:'其他条件或任意表达式',fields:[]},
};
export function ConditionEditor({points,value,onSave,onClose,title='编辑条件'}:{points:Point[];value?:Relation;onSave:(r:Relation)=>void;onClose:()=>void;title?:string}){
 const t=useT();const [kind,setKind]=useState(value?.kind||'equal_length');
 const defaults=(k:string)=>(k==='minimize'?['','','','']:relations[k].fields).map((_,i)=>points[i%points.length].id);
 const [args,setArgs]=useState(value?.args||defaults(kind));
 const [coordinates,setCoordinates]=useState(value?.coordinates||[0,0]);
 const [description,setDescription]=useState(value?.description||'');
 const [length,setLength]=useState(value?.value??1),[weights,setWeights]=useState(value?.weights?.length?value.weights:[1,1]),[orientation,setOrientation]=useState(value?.orientation||'ccw');
 const relation:Relation={id:value?.id||'condition-'+crypto.randomUUID(),kind,args,enabled:value?.enabled??true,toggleable:true,...(kind==='free_text'?{description}:{}),...(kind==='fixed_point'?{coordinates}:{}),...(['fixed_length','length_ratio','fixed_angle'].includes(kind)?{value:length}:{}),...(kind==='minimize'?{weights}:{}),...(kind==='on_arc'?{orientation}:{})};
 return <Modal title={t(title)} onClose={onClose}><form className="condition-editor" onSubmit={e=>{e.preventDefault();onSave(relation)}}><label className="field">{t('关系')}<select value={kind} onChange={e=>{setKind(e.target.value);setArgs(defaults(e.target.value));setWeights([1,1])}}>{Object.entries(relations).filter(([id])=>!["minimize","angle_value"].includes(id)||title.includes("目标")).map(([id,r])=><option key={id} value={id}>{t(r.label)}</option>)}</select></label>{kind==='free_text'&&<label className="field">{t('完整条件或求解目标')}<textarea rows={4} value={description} required onChange={e=>setDescription(e.target.value)} placeholder={t('可以输入任意条件、最值或定值表达式，AI 会结合题目分析。')}/></label>}<div className="relation-point-fields">{(kind==="minimize"?args.map((_,i)=>(i%2===0?"线段起点":"线段终点")+" "+(Math.floor(i/2)+1)):relations[kind].fields).map((name,index)=><label key={index} className="field">{t(name)}<select value={args[index]} onChange={e=>setArgs(args.map((p,i)=>i===index?e.target.value:p))}>{points.map(p=><option key={p.id} value={p.id}>{p.id}</option>)}</select></label>)}</div>{['fixed_length','length_ratio','fixed_angle'].includes(kind)&&<label className="field">{t(kind==='fixed_angle'?'角度（°）':kind==='length_ratio'?'长度比':'长度')}<input type="number" min="0" max={kind==='fixed_angle'?179.999:100000} step="any" required value={length} onChange={e=>setLength(Number(e.target.value))}/></label>}{kind==='fixed_point'&&<div className="relation-point-fields">{['x','y'].map((axis,i)=><label className="field" key={axis}>{axis}<input type="number" step="any" required value={coordinates[i]} onChange={e=>setCoordinates(coordinates.map((n,j)=>j===i?Number(e.target.value):n))}/></label>)}</div>}{kind==='on_arc'&&<label className="field">{t('圆弧方向')}<select value={orientation} onChange={e=>setOrientation(e.target.value as 'cw'|'ccw')}><option value="ccw">{t('逆时针')}</option><option value="cw">{t('顺时针')}</option></select></label>}{kind==='minimize'&&<><div className="relation-point-fields">{weights.map((weight,i)=><label className="field" key={i}>{t('线段系数')} {i+1}<input type="number" min="0.000001" step="any" required value={weight} onChange={e=>setWeights(weights.map((v,j)=>i===j?Number(e.target.value):v))}/></label>)}</div>{weights.length<6&&<button type="button" className="text-button" onClick={()=>{setArgs([...args,points[0].id,points[1].id]);setWeights([...weights,1])}}>{t('增加一条线段')}</button>}{weights.length>1&&<button type="button" className="text-button" onClick={()=>{setArgs(args.slice(0,-2));setWeights(weights.slice(0,-1))}}>{t('移除最后一条线段')}</button>}</>}<p className="relation-sentence math">{t(text(relation))}</p><button className="button primary" type="submit">{t('确定')}</button></form></Modal>;
}
