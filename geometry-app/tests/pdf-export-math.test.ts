import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import postcss from 'postcss';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {MathValue} from '../components/geometry/math-value';
import {MathText} from '../components/geometry/math-text';
import {ProofView} from '../components/geometry/proof-view';
import {AiResponse} from '../components/geometry/ai-response';
import {HomeworkReport} from '../components/geometry/homework-report';
import {exactMathLatex,exactMathExpression} from '../lib/exact-math';
import {mathTextParts} from '../lib/math-text';
import type {Problem,Proof} from '../lib/geometry';
import catalogue from '../data/cases.json';
import {exportAnswerPdf,exportImagesForContext,feedbackPdfOptions,canExportFeedback} from '../lib/pdf-export';
import {buildChatContext,type ChatContextMessage} from '../lib/chat-context';
import {mathMarkdown} from '../lib/math-markdown';

test('Actual multiline dollar math never swallows following headings or the rest of an AI answer',()=>{
 const source=String.raw`**规范订正：**
$$\frac12+\frac13
=\frac{1\times3}{2\times3}+\frac{1\times2}{3\times2}
=\frac36+\frac26
=\frac56.$$
因此正确结果是
$$\boxed{\frac56}.$$

## 3. 判断两个角关系式是否等价

由 $$2\angle BOC=\angle BAC+180^\circ$$，两边除以 $2$ 得
$$\angle BOC=\frac{\angle BAC+180^\circ}{2}
=90^\circ+\frac12\angle BAC.$$
所以两式等价。`;
 const html=renderToStaticMarkup(React.createElement(AiResponse,{content:source,showCopy:false}));
 assert.doesNotMatch(html,/katex-error/);
 assert.match(html,/<h2>3\. 判断两个角关系式是否等价<\/h2>/);
 assert.equal((html.match(/class="katex-display"/g)||[]).length,4);
 assert.match(html,/<mfrac>/);assert.match(html,/所以两式等价。/);
 assert.equal((html.match(/<annotation /g)||[]).length,5);
});

test('Display normalization preserves inline formulas, escaped dollars and literal code',()=>{
 const source=String.raw`Keep $x+1$ and \$\$literal\$\$; `+'`$$x=1$$`\n```tex\n$$x=2$$\n```'+String.raw`\n\[x=3\]`;
 const normalized=mathMarkdown(source);
 assert.match(normalized,/Keep \$x\+1\$ and \\\$\\\$literal/);
 assert.ok(normalized.includes('`$$x=1$$`\n```tex\n$$x=2$$\n```'));
 assert.ok(normalized.includes('\n\n$$\nx=3\n$$\n\n'));
 const html=renderToStaticMarkup(React.createElement(AiResponse,{content:source,showCopy:false}));
 assert.doesNotMatch(html,/katex-error/);
});

test('Rendered math layout classes have the positioning rules in the CSS actually imported by both components',()=>{
 const require=createRequire(import.meta.url);
 const css=postcss.parse(readFileSync(require.resolve('katex/dist/katex.min.css'),'utf8'));
 const outputs=[
  {name:'AI answer',html:renderToStaticMarkup(React.createElement(AiResponse,{content:String.raw`\[\frac56\ne\frac25+\sqrt{10}\]`,showCopy:false})),required:['base','strut','vbox','thinbox','inner','fix']},
  {name:'Exact solver value',html:renderToStaticMarkup(React.createElement(MathValue,{value:'sqrt(10)/2'})),required:['base','strut','sizing']},
 ];
 for(const {name,html,required} of outputs){
  assert.doesNotMatch(html,/katex-error/);
  const names=[...new Set([...html.matchAll(/class="([^"]+)"/g)].flatMap(match=>match[1].split(/\s+/)))];
  for(const layout of required){
   const className=names.find(value=>value===layout||value==='katex-'+layout);
   assert.ok(className,`${name} must exercise ${layout} layout`);
   const selector=new RegExp('\\.'+className+'(?![\\w-])');
   let matched=false,positioned=layout!=='inner';
   css.walkRules(rule=>{if(selector.test(rule.selector)){matched=true;if(layout==='inner')rule.walkDecls('position',declaration=>{if(declaration.value==='absolute')positioned=true})}});
   assert.ok(matched,`${name}: rendered .${className} has no matching imported KaTeX CSS rule`);
   assert.ok(positioned,`${name}: the not-equal slash must be positioned over the equals sign`);
  }
 }
});

test('Exact numeric results render proper radicals, fractions and powers without decimal approximation',()=>{
 assert.equal(exactMathLatex('sqrt(10)'),String.raw`\sqrt{10}`);
 assert.equal(exactMathLatex('sqrt(2 + sqrt(3))/2'),String.raw`\frac{\sqrt{2+\sqrt{3}}}{2}`);
 assert.equal(exactMathLatex('-1/3'),String.raw`\frac{-1}{3}`);
 assert.equal(exactMathLatex('(1 + sqrt(5))**2'),String.raw`\left(1+\sqrt{5}\right)^{2}`);
 assert.equal(exactMathLatex('-2**2'),String.raw`-2^{2}`);
 assert.equal(exactMathLatex('(-2)**2'),String.raw`\left(-2\right)^{2}`);
 assert.equal(exactMathLatex('2**(1/3)'),String.raw`2^{\frac{1}{3}}`);
 const root=renderToStaticMarkup(React.createElement(MathValue,{value:'sqrt(10)'}));
 assert.match(root,/class="katex"/);assert.match(root,/<msqrt>/);assert.doesNotMatch(root,/√\(10\)|katex-error/);
 assert.match(root,/role="math" aria-label="根号（10）"/);
 assert.equal(exactMathExpression('sqrt(10)','en')?.label,'square root of (10)');
 const fraction=renderToStaticMarkup(React.createElement(MathValue,{value:'2*sqrt(10)/3'}));
 assert.match(fraction,/<mfrac>/);assert.match(fraction,/<msqrt>/);assert.doesNotMatch(fraction,/katex-error/);
});

test('Proof prose renders old roots, exact fractions and powers while retaining all surrounding text',()=>{
 for(const [source,values] of [
  ['1BE = √(10)。',['√(10)']],
  ['最小值为 3*sqrt(37)/2。',['3*sqrt(37)/2']],
  ['取 OA = 1/4AD，系数为 (1+sqrt(5))/2，幂为 2**(1/3)。',['1/4','(1+sqrt(5))/2','2**(1/3)']],
 ] as const){
  const parts=mathTextParts(source);assert.equal(parts.map(part=>part.text).join(''),source);
  assert.deepEqual(parts.filter(part=>part.math).map(part=>part.text),[...values]);
  const html=renderToStaticMarkup(React.createElement(MathText,{text:source}));
  assert.doesNotMatch(html,/katex-error|√\(/);assert.match(html,/role="math"/);
 }
});

test('Prose formatting leaves code, links, dates, identifiers and malformed roots unchanged',()=>{
 const source='记录 2026/11/10；代码 `sqrt(10)`；https://example.com/1/2；C:/1/2；mysqrt(10)；sqrt(10file；√(10';
 const parts=mathTextParts(source);assert.equal(parts.map(part=>part.text).join(''),source);assert.ok(parts.every(part=>!part.math));
 const html=renderToStaticMarkup(React.createElement(MathText,{text:'<script>alert(1)</script>，最小值为 √(7)'}));
 assert.doesNotMatch(html,/<script>/);assert.match(html,/&lt;script&gt;/);assert.match(html,/<msqrt>/);
});

test('Saved optimization proof statements, rules and dependency text all render standard exact mathematics',()=>{
 const proof:Proof={id:'opt-saved',title:'优化证明',engine:'SymPy + Z3',status:'verified',assumptionIds:[],assumptionNodes:[],steps:[
  {id:'distance',statement:'1BE = √(10)。',rule:'计算 √(2+sqrt(3))/2。',premises:[]},
  {id:'conclusion',statement:'最小值为 √(10)。',rule:'下界成立且能够取到',premises:['distance']},
 ]};
 const html=renderToStaticMarkup(React.createElement(ProofView,{proof,problem:catalogue[0] as Problem,conditionNames:new Map()}));
 assert.match(html,/最小值为/);assert.match(html,/<mfrac>/);assert.match(html,/aria-label="根号（10）"/);
 assert.equal((html.match(/role="math"/g)||[]).length,4);
 assert.doesNotMatch(html,/√\(|katex-error|导出 PDF|ai-copy/);
});

test('Saved AI dependencies typeset the same delimited formulas as proof prose',()=>{
 const statement='因 $D$ 在线段 $BC$ 上，$\\angle ACD=\\angle ACB=40^\\circ$。在 \\( \\triangle ACD \\) 中，\\[\\angle ADC=180^\\circ-60^\\circ-40^\\circ=80^\\circ\\]。';
 const proof:Proof={id:'ai-saved-dependencies',title:'角度推导',engine:'AI',status:'candidate',assumptionIds:[],
  assumptionNodes:[{id:'construction',statement:'辅助式 $$\\sqrt{10}\\ne 2$$',premises:[]}],
  steps:[
   {id:'angle',statement,premises:[]},
   {id:'conclusion',statement:'得 $ \\angle ADC=80^\\circ $。',premises:['angle','construction','removed','domain']},
  ]};
 const html=renderToStaticMarkup(React.createElement(ProofView,{proof,problem:catalogue[0] as Problem,
  conditionNames:new Map([['removed','原条件 $AB=\\frac{1}{2}AC$']])}));
 const dependencies=[...html.matchAll(/<div class="joint-premises">([\s\S]*?)<\/div>/g)].at(-1)![1];
 const visible=dependencies.replace(/<annotation\b[^>]*>[\s\S]*?<\/annotation>/g,'');
 assert.equal((dependencies.match(/class="katex"/g)||[]).length,7);
 assert.match(visible,/因 /);assert.match(visible,/在线段 /);assert.match(visible,/非退化与点互异要求/);
 assert.match(visible,/class="missing-premise"/);assert.match(visible,/<mfrac>/);assert.match(visible,/<msqrt>/);
 assert.doesNotMatch(visible,/\$|\\angle|\\circ|katex-error/);
});

test('Inline formula recognition leaves code and literal delimiters alone',()=>{
 const source='代码 `$x$`，转义 \\$10，公式 \\(\\frac{1}{2}\\) 与 $$\\sqrt{3}\n+1$$。';
 const parts=mathTextParts(source);
 assert.equal(parts.map(part=>part.text).join(''),source);
 assert.deepEqual(parts.flatMap(part=>part.latex===undefined?[]:[part.latex]),['\\frac{1}{2}','\\sqrt{3}\n+1']);
 const html=renderToStaticMarkup(React.createElement(MathText,{text:'安全测试 $\\href{javascript:alert(1)}{x}$，以及 <script>。'}));
 assert.doesNotMatch(html,/<(?:script|a)\b|href=/);
 assert.match(html,/&lt;script&gt;/);
});

test('Unknown or malformed solver values remain escaped readable text instead of guessed formulas',()=>{
 for(const value of ['sqrt(10','1/','sqrt(2);alert(1)','\\htmlStyle{color:red}{x}','arbitrary text'])assert.equal(exactMathLatex(value),undefined);
 const html=renderToStaticMarkup(React.createElement(MathValue,{value:'<script>alert(1)</script>'}));
 assert.doesNotMatch(html,/<script>|class="katex"/);assert.match(html,/&lt;script&gt;/);
});

test('Only this turn’s checked grading exposes a PDF download or retry',()=>{
 const reportPdf={name:'answer.pdf',dataUrl:'data:application/pdf;base64,JVBERi0x'};
 const html=renderToStaticMarkup(React.createElement(HomeworkReport,{reply:{grading:null,reportPdf}}));
 assert.doesNotMatch(html,/download=|PDF|homework-marks/);
 const grading={score:null,maximum:100,basis:'',items:[{label:'本题',verdict:'incorrect' as const,feedback:'需要改正'}]};
 const reply={mode:'homework' as const,pdfEligible:true,grading};
 const report=renderToStaticMarkup(React.createElement(HomeworkReport,{reply:{...reply,reportPdf}}));
 assert.match(report,/download="answer.pdf"/);assert.match(report,/下载批改 PDF/);assert.doesNotMatch(report,/暂无法评分/);
 const error=renderToStaticMarkup(React.createElement(HomeworkReport,{reply:{...reply,reportError:'Please retry the export'}}));
 assert.match(error,/Please retry the export/);assert.match(error,/role="status"/);
 assert.equal(canExportFeedback({...reply,mode:'solution'}),false);
 assert.equal(feedbackPdfOptions({...reply,pdfEligible:false}),undefined);
 assert.deepEqual(feedbackPdfOptions(reply),{images:undefined,grading});
});

test('Ordinary solutions do not expose PDF controls even after a previous grading',()=>{
 const html=renderToStaticMarkup(React.createElement(AiResponse,{content:'The answer is \\(\\sqrt{10}\\).',exportPdf:feedbackPdfOptions({mode:'solution',pdfEligible:false})}));
 assert.doesNotMatch(html,/导出 PDF|下载 PDF|API Key|正在生成 PDF/);
 const statement=renderToStaticMarkup(React.createElement(AiResponse,{content:'A single proof statement.',showCopy:false}));
 assert.doesNotMatch(statement,/导出 PDF|ai-copy/);
});

test('Export calls only the local PDF endpoint and preserves the selected text, math and images',async()=>{
 const prior=globalThis.fetch,calls:unknown[]=[];
 const payload={content:'Correct: \\(\\frac12+\\frac13=\\frac56\\)',language:'zh' as const,images:[{name:'work.png',dataUrl:'data:image/png;base64,original'}],grading:null};
 globalThis.fetch=async(url,init)=>{
  calls.push(url);assert.equal(url,'/api/ai/export-pdf');assert.equal(init?.method,'POST');
  assert.deepEqual(init?.headers,{'Content-Type':'application/json'});
  assert.deepEqual(JSON.parse(String(init?.body)),payload);
  return Response.json({reportPdf:{name:'answer.pdf',dataUrl:'data:application/pdf;base64,JVBERi0x'}});
 };
 try{const result=await exportAnswerPdf(payload);assert.equal(result.name,'answer.pdf');assert.equal(calls.length,1)}finally{globalThis.fetch=prior}
});

test('Export never offers a malformed or remote response as a downloadable generated PDF',async()=>{
 const prior=globalThis.fetch;
 globalThis.fetch=async()=>Response.json({reportPdf:{name:'answer.pdf',dataUrl:'https://example.com/pretend.pdf'}});
 try{await assert.rejects(exportAnswerPdf({content:'Answer',language:'zh'}),/PDF 文件生成失败/)}finally{globalThis.fetch=prior}
});

test('Every report keeps only this submission’s upload group and never revives an earlier worksheet',()=>{
 const photo=(name:string)=>({name,dataUrl:'data:image/png;base64,'+name});
 const messages:ChatContextMessage[]=[{role:'user',content:'First problem',images:[photo('first.png')]},{role:'assistant',content:'First answer'},{role:'user',content:'Explain this step'}];
 const first=exportImagesForContext(buildChatContext(messages));
 messages.push({role:'assistant',content:'Explanation'},{role:'user',content:'New problem',images:[photo('second.png'),photo('second-page.png')]});
 const second=exportImagesForContext(buildChatContext(messages));
 assert.deepEqual(first,[]);assert.deepEqual(second,[photo('second.png'),photo('second-page.png')]);
 for(let n=0;n<4;n++)messages.push({role:'assistant',content:'Answer'},{role:'user',content:'Text-only follow-up'});
 assert.deepEqual(exportImagesForContext(buildChatContext(messages)),[],'Images outside the model context must not be revived for export');
 assert.deepEqual(first,[]);
});
