import test from 'node:test';
import assert from 'node:assert/strict';
import {topicAnswerText} from '../lib/topic-answer';

test('Saved duplicate protocol replies show one mathematical answer',()=>{
 const answer=String.raw`最小值为 \(\sqrt{10}\)。`;
 const source=JSON.stringify({routes:[],answer});
 assert.equal(topicAnswerText(source+'\n'+source),answer);
 assert.equal(topicAnswerText('```json\n'+source+'\n```'),answer);
});
test('Older route-only answers retain readable proof statements and math',()=>{
 const source=JSON.stringify({routes:[{title:'三角不等式',steps:[{statement:'取 E = (-2, 0)。'},{statement:'2MA = ME，因此最小值为 √(10)。'}]}]});
 const result=topicAnswerText(source);
 assert.match(result,/### 三角不等式/);assert.match(result,/最小值为 √\(10\)/);
 assert.doesNotMatch(result,/"routes"|"steps"|"statement"/);
});
test('JSON braces and quoted strings within an answer cannot split the protocol',()=>{
 const answer='函数集合 {x | x > 0}；示例 "content"。';
 const source=JSON.stringify({mode:'solution',content:answer});
 assert.equal(topicAnswerText(source+' '+source),answer);
});
test('Conflicting, truncated or invalid saved data is never shown as a solution',()=>{
 const source=JSON.stringify({routes:[],answer:'a'});
 for(const value of [source+JSON.stringify({routes:[],answer:'b'}),source.slice(0,-1),source+' garbage',JSON.stringify({routes:[{steps:[]}]}),source.repeat(9)]){
  assert.equal(topicAnswerText(value),'先前保存的 AI 回复格式不完整，请重新生成解答。');
 }
});
test('Readable stored prose remains unchanged',()=>{
 const source=String.raw`设 \(M=(x,y)\)，则 \(x^2+y^2=1\)。`;
 assert.equal(topicAnswerText(source),source);
});
