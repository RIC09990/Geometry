import test from 'node:test';
import assert from 'node:assert/strict';
import {buildChatContext,recentTurnStart,type ChatContextMessage} from '../lib/chat-context';

const user=(content:string,images?:ChatContextMessage['images']):ChatContextMessage=>({role:'user',content,...(images?{images}:{})});
const assistant=(content:string):ChatContextMessage=>({role:'assistant',content});
const picture=(name:string)=>({name,dataUrl:'data:image/png;base64,'+name});
const pairs=(count:number,offset=0)=>Array.from({length:count},(_,i)=>[user('question '+(i+offset)),assistant('answer '+(i+offset))]).flat();

test('A conversation inside the high-water budget is sent whole',()=>{
 const input=[...pairs(6),user('继续刚才第二步，为什么可以同时除以 2？')];
 assert.deepEqual(buildChatContext(input),input);
});

test('Exceeding the budget drops whole old turns back to the trim target',()=>{
 const input=[...pairs(14),user('继续')];
 const context=buildChatContext(input);
 assert.deepEqual(context,input.slice(-11));
 assert.equal(context.length,11);
 assert.equal(context.at(-1)?.content,'继续');
});

test('A current turn beyond the budget is preserved alone',()=>{
 const latest=user('完整原题与解答：\n'+'x'.repeat(25000)+String.raw`\[x+1=2\]`,[picture('current.png')]);
 const context=buildChatContext([user('old'),assistant('old reply'),latest]);
 assert.deepEqual(context,[latest]);
 assert.equal(context[0].content,latest.content);
 assert.deepEqual(context[0].images,latest.images);
});

test('Unicode character budgeting agrees with the server and preserves complete messages',()=>{
 const input=[user('😀'.repeat(6000)),assistant('答'.repeat(5999)),user('问')];
 assert.deepEqual(buildChatContext(input),input);
 const oversized=[user('😀'.repeat(12000)),assistant('答'.repeat(12000)),user('再问')];
 assert.deepEqual(buildChatContext(oversized),[user('再问')]);
});

test('Uploads of every retained turn travel with the request',()=>{
 const first=picture('first.png'),second=picture('second.png'),third=picture('third.png');
 const input=[user('第一题',[first]),assistant('第一题解答'),user('第二题',[second]),assistant('第二题解答'),user('第三题',[third])];
 const before=structuredClone(input),context=buildChatContext(input);
 assert.deepEqual(context[0].images,[first]);
 assert.deepEqual(context[2].images,[second]);
 assert.deepEqual(context[4].images,[third]);
 assert.deepEqual(input,before,'UI history and its displayed uploads must remain intact');
 assert.notEqual(context[4].images,input[4].images);
});

test('A text follow-up retains the newest two attachment groups still in context',()=>{
 const input=[user('第一张',[picture('old.png')]),assistant('答1'),user('第二张',[picture('new-1.png'),picture('new-2.png')]),assistant('答2'),user('继续刚才第二步')];
 const context=buildChatContext(input);
 assert.deepEqual(context[0].images,input[0].images);
 assert.deepEqual(context[2].images,input[2].images);
 assert.equal(context.at(-1)?.images,undefined);
 assert.equal(context.at(-1)?.content,'继续刚才第二步');
});

test('Images outside the selected turns are not reintroduced after trimming',()=>{
 const input=[user('很久前的附件',[picture('old.png')]),assistant('old answer'),...pairs(13),user('本次问题')];
 const context=buildChatContext(input);
 assert.ok(context.every(message=>!message.images));
 assert.equal(context[0].role,'user');
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

test('Whole assistant groups are never split at the message limit',()=>{
 const group=(i:number)=>[user('question '+i),...Array.from({length:6},(_,j)=>assistant('fragment '+i+'-'+j))];
 const input=[...group(0),...group(1),...group(2),...group(3),user('current')];
 const context=buildChatContext(input);
 assert.deepEqual(context,[...group(3),user('current')]);
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

test('A stored summary replaces compacted turns and keeps the recent ones',()=>{
 const input=[...pairs(6),user('继续')];
 const context=buildChatContext(input,{text:'早期提要',through:8});
 assert.equal(context[0].role,'assistant');
 assert.match(context[0].content,/早期对话摘要：\n早期提要/);
 assert.deepEqual(context.slice(1),input.slice(8));
});

test('The recent window starts at the newest complete turns',()=>{
 const input=[...pairs(6),user('继续')];
 assert.equal(recentTurnStart(input,4),6);
 assert.equal(recentTurnStart(input,10),0);
});
