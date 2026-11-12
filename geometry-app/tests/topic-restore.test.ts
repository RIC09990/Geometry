import test from 'node:test';
import assert from 'node:assert/strict';
import {restoreTopicAnalysis,type Topic} from '../lib/topics';
import {cases,clone,type Analysis,type RecordEntry} from '../lib/geometry';

const problem={...clone(cases[0]),id:'custom-restore'};
const result:Analysis={version:problem.version,outcome:'proven',message:'fresh',proofs:[],search:{status:'skipped'},impact:[],elapsed:0};
const aiResult:Analysis={...result,message:'saved',aiAnswer:{version:problem.version,content:'已保存的解答'},proofs:[{id:'ai-saved',title:'AI 路线',engine:'AI',status:'candidate',steps:[],assumptionIds:[],assumptionNodes:[]}]};
const record:RecordEntry={key:'recent',name:'恢复',problem,time:'2026-11-10T15:00:00Z',saved:false,result};
const topic:Topic={id:problem.id,problem,recognizedText:'',createdAt:'2026-11-10T14:00:00Z',updatedAt:'2026-11-10T15:01:00Z',result:aiResult};

test('A newer saved AI answer takes precedence over the earlier analysis cache',()=>{
 assert.equal(restoreTopicAnalysis(problem,record,topic),aiResult);
});
test('Reanalysis keeps its fresh conclusion while restoring the same saved AI answer',()=>{
 const restored=restoreTopicAnalysis(problem,{...record,time:'2026-11-10T15:02:00Z'},topic)!;
 assert.equal(restored.message,'fresh');assert.equal(restored.aiAnswer?.content,'已保存的解答');
 assert.equal(restored.proofs[0].id,'ai-saved');assert.equal(result.aiAnswer,undefined);
});
test('The latest AI answer wins without merging old AI routes',()=>{
 const fresh={...aiResult,aiAnswer:{version:problem.version,content:'新的解答'},proofs:[{...aiResult.proofs[0],id:'ai-new'}]};
 const restored=restoreTopicAnalysis(problem,{...record,time:'2026-11-10T15:02:00Z',result:fresh},topic)!;
 assert.equal(restored.aiAnswer?.content,'新的解答');assert.deepEqual(restored.proofs.map(p=>p.id),['ai-new']);
});
test('Changed conditions and stale versions cannot restore an older proof or answer',()=>{
 const changed=clone(problem);changed.conditions[0].enabled=!changed.conditions[0].enabled;
 assert.equal(restoreTopicAnalysis(changed,record,topic),undefined);
 assert.equal(restoreTopicAnalysis({...problem,version:problem.version+1},record,topic),undefined);
});
test('A stale saved AI answer is not merged into a current analysis',()=>{
 const restored=restoreTopicAnalysis(problem,record,{...topic,result:{...aiResult,aiAnswer:{version:problem.version-1,content:'旧题目'}}})!;
 assert.equal(restored.aiAnswer,undefined);assert.deepEqual(restored.proofs,[]);
});
