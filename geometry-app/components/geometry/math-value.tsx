'use client';
import 'katex/dist/katex.min.css';
import katex from 'katex';
import {exactMathExpression} from '@/lib/exact-math';
import {useLanguage} from '@/lib/i18n';

export function MathValue({value,latex}:{value:string;latex?:string}){
 const {language}=useLanguage(),expression=latex===undefined?exactMathExpression(value,language):undefined;
 const formula=latex??expression?.latex;
 if(!formula)return <span>{value}</span>;
 try{
  const html=katex.renderToString(formula,{throwOnError:true,trust:false,maxExpand:1000,maxSize:20});
  return <span role="math" aria-label={expression?.label}><span aria-hidden={expression?true:undefined} dangerouslySetInnerHTML={{__html:html}}/></span>;
 }catch{return <span>{value}</span>}
}
