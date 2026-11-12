/** Accept AI TeX delimiters without changing fenced or inline code. */
export function mathMarkdown(source:string){
 return source.split(/(```[\s\S]*?```|`[^`\n]*`)/g).map((part,index)=>index%2?part:part
  // remark-math treats text after a block's opening $$ as metadata and only
  // recognizes a closing fence on its own line. AI replies use both compact
  // and multiline forms, so put every complete display formula on its own lines.
  .replace(/(?<!\\)\$\$([\s\S]*?)(?<!\\)\$\$/g,(_,math)=>'\n\n$$\n'+math.trim()+'\n$$\n\n')
  .replace(/\\\[\s*([\s\S]*?)\s*\\\]/g,(_,math)=>'\n\n$$\n'+math+'\n$$\n\n')
  .replace(/\\\(([\s\S]*?)\\\)/g,(_,math)=>'$'+math.trim()+'$')
  .replace(/\*\*([^\n]*?)\*\*/g,(_,text)=>'**'+text.trim()+'**')).join('');
}
