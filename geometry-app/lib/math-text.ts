import {exactMathLatex} from './exact-math';

export type MathTextPart={text:string;math?:true;latex?:string};

/** Recognize delimited TeX and exact numbers in proof prose. */
export function mathTextParts(source:string):MathTextPart[]{
 const parts:MathTextPart[]=[];
 const protectedParts=source.split(/(```[\s\S]*?```|`[^`\n]*`|https?:\/\/[^\s]+|[A-Za-z]:[\\/][^\s]+|(?<!\\)\\\([\s\S]*?(?<!\\)\\\)|(?<!\\)\\\[[\s\S]*?(?<!\\)\\\]|(?<!\\)\$\$[\s\S]+?(?<!\\)\$\$|(?<![\\$])\$(?!\$)(?:\\.|[^$\\\r\n])+?\$(?!\$))/g);
 for(let i=0;i<protectedParts.length;i++){
  const text=protectedParts[i];
  if(i%2){
   const delimiter=text.startsWith('$$')||text.startsWith('\\(')||text.startsWith('\\[')?2:text.startsWith('$')?1:0;
   parts.push(delimiter?{text,latex:text.slice(delimiter,-delimiter).trim()}:{text});
   continue;
  }
  let cursor=0;
  const candidates=/(?:sqrt|pi|√|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[()+\-*/^ \t])+/g;
  for(const match of text.matchAll(candidates)){
   const raw=match[0],leading=raw.match(/^[\s*/^]*/)?.[0].length||0;
   const expression=raw.slice(leading).replace(/[\s+\-*/^]+$/,'');
   const start=match.index+leading,end=start+expression.length;
   if(!expression||!/(?:sqrt|√|\/|\*|\^|pi)/.test(expression))continue;
   // Do not reinterpret identifiers, file names, dates or a piece of malformed syntax.
   if(/[A-Za-z0-9_\\.]/.test(text[start-1]||''))continue;
   if(/[A-Za-z0-9_.]/.test(text[end]||'')&&!/^[A-Z][A-Z0-9]+(?:\b|[\u3400-\u9fff])/.test(text.slice(end)))continue;
   if(/^\d{4}\/\d{1,2}\/\d{1,2}$/.test(expression)||exactMathLatex(expression)===undefined)continue;
   if(start>cursor)parts.push({text:text.slice(cursor,start)});
   parts.push({text:expression,math:true});cursor=end;
  }
  if(cursor<text.length)parts.push({text:text.slice(cursor)});
 }
 return parts;
}
