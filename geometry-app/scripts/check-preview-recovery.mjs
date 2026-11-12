import {writeFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
const rows=[];
const before=await(await fetch('http://127.0.0.1:3000/__geometry_ready')).json();
if(!before.ready||before.api.port!==8001||!Number.isInteger(before.api.pid))throw new Error('Geometry 尚未就绪，未重启任何进程');
for(let i=0;i<20;i++){
 if(i===2&&process.argv.includes('--restart-api'))execFileSync('taskkill.exe',['/PID',String(before.api.pid),'/T','/F'],{stdio:'pipe',windowsHide:true});
 const [page,api]=await Promise.all([
  fetch('http://127.0.0.1:3000/',{signal:AbortSignal.timeout(3000)}).then(r=>r.status).catch(()=>0),
  fetch('http://127.0.0.1:3000/api/health',{signal:AbortSignal.timeout(1000)}).then(r=>r.status).catch(()=>0)
 ]);
 rows.push({time:new Date().toISOString(),page,api});
 await new Promise(r=>setTimeout(r,400));
}
const after=await(await fetch('http://127.0.0.1:3000/__geometry_ready')).json();
writeFileSync('docs/preview-recovery.json',JSON.stringify({before,rows,after},null,2));
console.log(JSON.stringify({pageStatuses:[...new Set(rows.map(r=>r.page))],apiStatuses:[...new Set(rows.map(r=>r.api))],recovered:after.ready,apiRestarts:after.api.restarts}));
if(rows.some(r=>r.page!==200)||!after.ready)process.exitCode=1;
