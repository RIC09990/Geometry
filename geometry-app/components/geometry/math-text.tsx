'use client';
import {Fragment} from 'react';
import {mathTextParts} from '@/lib/math-text';
import {MathValue} from './math-value';

/** Inline formulas in proof prose, condition labels and dependency chips. */
export function MathText({text}:{text:string}){
 return <>{mathTextParts(text).map((part,i)=>part.math||part.latex!==undefined?<MathValue key={i} value={part.text} latex={part.latex}/>:<Fragment key={i}>{part.text}</Fragment>)}</>;
}
