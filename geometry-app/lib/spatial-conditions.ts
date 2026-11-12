/** Match complete statements; any extra mathematical text stays unencoded. */
export function spatialStatement(description:string):{kind:string;args:string[]}|undefined{
 let source=description.trim();
 const notice=source.match(/^[“「"](.+?)[”」"]\s*(?:无法用当前已定义的几何关系直接精确表达，已用\s*free_text\s*条件保留|当前没有直接的内点关系，已用\s*free_text\s*保留)\s*[。.;；]?$/);
 if(notice)source=notice[1].trim();
 if(source.startsWith('\\(')&&source.endsWith('\\)'))source=source.slice(2,-2).trim();
 else if(source.startsWith('$')&&source.endsWith('$'))source=source.replace(/^\$+|\$+$/g,'').trim();
 source=source.replace(/\\triangle/g,'△');
 const point='([A-Z][0-9]?)';
 const match=source.match(new RegExp('^(?:已知\\s*)?(?:点\\s*)?'+point+'\\s*(?:在|位于)\\s*(?:△|Δ|三角形)\\s*'+point+'\\s*'+point+'\\s*'+point+'\\s*(?:的)?\\s*(?:内部|内)(?:\\s*[（(]不含边界[）)])?\\s*[。.;；]?$'));
 if(match&&new Set(match.slice(1)).size===4)return {kind:'inside_triangle',args:match.slice(1)};
}
