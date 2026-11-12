import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import path from 'node:path';
const python=process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python';
if(!existsSync(python)){console.error('请先按 README 安装 Python 依赖。');process.exit(1)}
try{const existing=await fetch('http://127.0.0.1:3000/api/health',{signal:AbortSignal.timeout(1000)});if(existing.ok){const info=await existing.json();if(info.engines?.newclid&&info.nicegeo){console.log('Geometry 已经运行：http://127.0.0.1:3000/');process.exit(0)}}}catch{}
const server=spawn(path.resolve(python),['-m','uvicorn','server.main:app','--host','127.0.0.1','--port','8001'],{stdio:'inherit',env:{...process.env,PYTHONIOENCODING:'utf-8'}});
const front=spawn(process.execPath,['scripts/run-framework.mjs','dev','--host','127.0.0.1','--port','3000'],{stdio:'inherit'});
const stop=()=>{server.kill();front.kill()};process.on('SIGINT',stop);process.on('SIGTERM',stop);process.on('exit',stop);
server.on('exit',code=>{if(code)stop()});front.on('exit',code=>{if(code)stop()});
