/** Display older saved protocol replies without modifying the student's records. */
export function topicAnswerText(source:string):string{
 const text=source.trim().replace(/^```(?:json)?\s*\n?/,'').replace(/\s*```$/,'');
 if(!/^\{\s*"(?:routes|answer|message|mode|content)"\s*:/.test(text))return source;
 try{
  const objects:Record<string,unknown>[]=[];
  let start=0,depth=0,string=false,escaped=false;
  for(let i=0;i<text.length;i++){
   const char=text[i];
   if(!depth&&/\s/.test(char)){start=i+1;continue;}
   if(string){if(escaped)escaped=false;else if(char==='\\')escaped=true;else if(char==='"')string=false;continue;}
   if(char==='"')string=true;
   else if(char==='{')depth++;
   else if(char==='}'&&--depth===0){objects.push(JSON.parse(text.slice(start,i+1)));start=i+1;if(objects.length>8)throw Error('Too many objects');}
   else if(!depth)throw Error('Unexpected protocol text');
  }
  if(depth||string||!objects.length)throw Error('Incomplete reply');
  const value=objects[0];
  if(objects.some(object=>JSON.stringify(object)!==JSON.stringify(value)))throw Error('Conflicting replies');
  if(typeof value.answer==='string'&&value.answer.trim())return value.answer;
  if(typeof value.content==='string'&&value.content.trim())return value.content;
  if(Array.isArray(value.routes)){
   const routes=value.routes.map(route=>{
    if(!route||typeof route.title!=='string'||!Array.isArray(route.steps))throw Error('Invalid route');
    return '### '+route.title+'\n\n'+route.steps.map((step:{statement?:unknown})=>{if(typeof step.statement!=='string')throw Error('Invalid step');return step.statement}).join('\n\n');
   });
   if(routes.length)return routes.join('\n\n');
  }
 }catch{/* Leave the original saved record intact; offer regeneration. */}
 return '先前保存的 AI 回复格式不完整，请重新生成解答。';
}
