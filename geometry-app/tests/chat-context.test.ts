import test from 'node:test';
import assert from 'node:assert/strict';
import {buildChatContext,type ChatContextMessage} from '../lib/chat-context';

const user=(content:string,images?:ChatContextMessage['images']):ChatContextMessage=>({role:'user',content,...(images?{images}:{})});
const assistant=(content:string):ChatContextMessage=>({role:'assistant',content});
const picture=(name:string)=>({name,dataUrl:'data:image/png;base64,'+name});

test('The current question remains last with only three complete preceding turns',()=>{
 const input=Array.from({length:6},(_,i)=>[user('question '+i),assistant('answer '+i)]).flat();
 input.push(user('继续刚才第二步，为什么可以同时除以 2？'));
 const context=buildChatContext(input);
 assert.deepEqual(context,input.slice(6));
 assert.equal(context.length,7);assert.equal(context[0].role,'user');
 assert.equal(context.at(-1)?.content,'继续刚才第二步，为什么可以同时除以 2？');
});

test('The text budget drops whole old turns without cutting equations or jumping over a missing turn',()=>{
 const formula=String.raw`\[2\angle BOC=\angle BAC+180^\circ\]`;
 const input=[user('An older short question'),assistant('An older short answer'),user('长'.repeat(12000)),assistant(formula),user('继续解释上式。')];
 assert.deepEqual(buildChatContext(input),[input.at(-1)]);
 const fitting=[user('x'.repeat(11900)),assistant(formula),user('继续解释上式。')];
 const context=buildChatContext(fitting);
 assert.deepEqual(context,fitting);assert.equal(context[1].content,formula);
});

test('A large current request and its attachments remain complete even beyond the text budget',()=>{
 const latest=user('完整原题与解答：\n'+'x'.repeat(14000)+String.raw`\[x+1=2\]`,[picture('current.png')]);
 const context=buildChatContext([user('old'),assistant('old reply'),latest]);
 assert.deepEqual(context,[latest]);
 assert.equal(context[0].content,latest.content);
 assert.deepEqual(context[0].images,latest.images);
});

test('Unicode character budgeting agrees with the server and preserves complete messages',()=>{
 const input=[user('😀'.repeat(6000)),assistant('答'.repeat(5999)),user('问')];
 assert.deepEqual(buildChatContext(input),input);
 assert.deepEqual(buildChatContext([...input.slice(0,2),user('再问')]),[user('再问')]);
});

test('A new attachment group replaces old images in the request without changing UI history',()=>{
 const first=picture('first.png'),second=picture('second.png'),third=picture('third.png');
 const input=[user('第一题',[first]),assistant('第一题解答'),user('第二题',[second,third])];
 const before=structuredClone(input),context=buildChatContext(input);
 assert.equal(context[0].images,undefined);
 assert.deepEqual(context[2].images,[second,third]);
 assert.deepEqual(input,before,'UI history and its displayed uploads must remain intact');
 assert.notEqual(context[2].images,input[2].images);
});

test('A text follow-up retains only the latest attachment group still in the selected context',()=>{
 const input=[user('第一张',[picture('old.png')]),assistant('答1'),user('第二张',[picture('new-1.png'),picture('new-2.png')]),assistant('答2'),user('继续刚才第二步')];
 const context=buildChatContext(input);
 assert.equal(context[0].images,undefined);
 assert.deepEqual(context[2].images,input[2].images);
 assert.equal(context.at(-1)?.images,undefined);
 assert.equal(context.at(-1)?.content,'继续刚才第二步');
});

test('Images outside the selected recent turns are not reintroduced',()=>{
 const input=[user('很久前的附件',[picture('old.png')]),assistant('old answer')];
 for(let i=0;i<4;i++)input.push(user('question '+i),assistant('answer '+i));
 input.push(user('本次问题'));
 assert.ok(buildChatContext(input).every(message=>!message.images));
});

test('Request messages strip response metadata and non-input image fields',()=>{
 const input=[
  {...user('题目'),images:[{...picture('input.png'),id:'local-attachment',text:'internal attachment field'}]},
  {...assistant('解答'),sources:[{title:'Reference',url:'https://example.com'}],grading:{score:50},reportPdf:{dataUrl:'private report'},provider:'model provider',finishReason:'stop',images:[picture('invalid-assistant-image.png')]},
  user('继续'),
 ];
 const before=structuredClone(input),context=buildChatContext(input);
 assert.deepEqual(context,[user('题目',[picture('input.png')]),assistant('解答'),user('继续')]);
 assert.deepEqual(input,before);
});

test('Incomplete user turns are preserved and leading orphan assistant messages are omitted',()=>{
 const input=[assistant('orphan'),user('补充上传'),user('刚才漏了一条条件'),assistant('已收到'),user('继续')];
 assert.deepEqual(buildChatContext(input),input.slice(1));
});

test('An oversized multi-message turn is not split to fit the hard message limit',()=>{
 const input=[user('previous'),...Array.from({length:7},(_,i)=>assistant('fragment '+i)),user('current')];
 assert.deepEqual(buildChatContext(input),[user('current')]);
});

test('Question wording never heuristically erases context and current formula whitespace is retained',()=>{
 const latest=user('  换一道题也可以继续刚才的思路：\n'+String.raw`\[2\angle BOC=\angle BAC+180^\circ\]`+'\n');
 const input=[user('先前问题'),assistant('先前答案'),latest];
 assert.deepEqual(buildChatContext(input),input);
 assert.equal(buildChatContext(input).at(-1)?.content,latest.content);
});

test('An empty conversation is harmless and a payload without a current user request is rejected',()=>{
 assert.deepEqual(buildChatContext([]),[]);
 assert.throws(()=>buildChatContext([user('question'),assistant('answer')]),/current request/);
});
