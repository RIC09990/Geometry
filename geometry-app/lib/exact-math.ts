type Term={tex:string;label:string;precedence:number};
export type ExactMathExpression={latex:string;label:string};

/** Format the numeric expression returned by the exact solver; never evaluate it. */
export function exactMathExpression(source:string,language:'zh'|'en'='zh'):ExactMathExpression|undefined{
 if(!source.trim()||source.length>2048)return;
 const tokens:string[]=[];let offset=0;
 while(offset<source.length){
  const rest=source.slice(offset),space=rest.match(/^\s+/);
  if(space){offset+=space[0].length;continue}
  const token=rest.match(/^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|^(?:sqrt|pi|\*\*|[√()+\-*/^])/);
  if(!token)return;tokens.push(token[0]);offset+=token[0].length;
 }
 let index=0,depth=0;
 const group=(term:Term,minimum:number)=>term.precedence<minimum?'\\left('+term.tex+'\\right)':term.tex;
 const bracket=(value:string)=>language==='zh'?'（'+value+'）':'('+value+')';
 const spokenGroup=(term:Term,minimum:number)=>term.precedence<minimum?bracket(term.label):term.label;
 function atom():Term{
  if(++depth>64)throw new Error('Expression is too deeply nested');
  const token=tokens[index++];let result:Term;
  if(token==='('){result=sum();if(tokens[index++]!==')')throw new Error('Unclosed group')}
  else if(token==='sqrt'||token==='√'){
   if(tokens[index++]!=='(')throw new Error('Missing root argument');
   const value=sum();if(tokens[index++]!==')')throw new Error('Unclosed root');
   result={tex:'\\sqrt{'+value.tex+'}',label:(language==='zh'?'根号':'square root of ')+bracket(value.label),precedence:4};
  }else if(token==='pi')result={tex:'\\pi',label:language==='zh'?'圆周率 π':'pi',precedence:4};
  else if(token&&/^(?:\d|\.)/.test(token)){
   const scientific=token.match(/^(.+?)[eE]([+-]?\d+)$/);
   result={tex:scientific?scientific[1]+'\\times 10^{'+scientific[2]+'}':token,label:scientific?scientific[1]+(language==='zh'?' 乘以 10 的 ':' times 10 to the power of ')+scientific[2]+(language==='zh'?' 次方':''):token,precedence:scientific?2:4};
  }else throw new Error('Unsupported expression');
  depth--;return result;
 }
 function power():Term{const base=atom();if(!['**','^'].includes(tokens[index]))return base;index++;const exponent=unary();return {tex:group(base,4)+'^{'+exponent.tex+'}',label:spokenGroup(base,4)+(language==='zh'?' 的 ':' to the power of ')+bracket(exponent.label)+(language==='zh'?' 次方':''),precedence:3}}
 function unary():Term{if(tokens[index]==='+'||tokens[index]==='-'){const sign=tokens[index++],value=unary();return {tex:sign+group(value,2),label:(language==='zh'?(sign==='-'?'负 ':'正 '):(sign==='-'?'negative ':'positive '))+spokenGroup(value,2),precedence:2}}return power()}
 function product():Term{
  let value=unary();while(tokens[index]==='*'||tokens[index]==='/'){
   const op=tokens[index++],right=unary();value=op==='/'?{tex:'\\frac{'+value.tex+'}{'+right.tex+'}',label:language==='zh'?bracket(right.label)+' 分之 '+bracket(value.label):bracket(value.label)+' divided by '+bracket(right.label),precedence:4}:{tex:group(value,2)+'\\cdot '+group(right,2),label:spokenGroup(value,2)+(language==='zh'?' 乘以 ':' times ')+spokenGroup(right,2),precedence:2};
  }return value;
 }
 function sum():Term{let value=product();while(tokens[index]==='+'||tokens[index]==='-'){const op=tokens[index++],right=product();value={tex:value.tex+op+group(right,op==='-'?2:1),label:value.label+(language==='zh'?(op==='-'?' 减去 ':' 加 '):(op==='-'?' minus ':' plus '))+spokenGroup(right,op==='-'?2:1),precedence:1}}return value}
 try{const result=sum();return index===tokens.length?{latex:result.tex,label:result.label}:undefined}catch{return}
}

export function exactMathLatex(source:string):string|undefined{return exactMathExpression(source)?.latex}
