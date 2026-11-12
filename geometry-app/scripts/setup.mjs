import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {existsSync} from 'node:fs';
const root=process.cwd();
async function run(cmd,args,env={}){await new Promise((resolve,reject)=>{const child=spawn(cmd,args,{stdio:'inherit',cwd:root,env:{...process.env,...env}});child.on('error',reject);child.on('exit',code=>code===0?resolve():reject(new Error(`安装步骤退出：${code}`)))})}
const npmCli=process.env.npm_execpath||path.join(path.dirname(process.execPath),'node_modules/npm/bin/npm-cli.js');
await run(process.execPath,[npmCli,'ci']);
if(process.platform==='win32'){
 await fs.mkdir('.tools',{recursive:true});
 const meta=await(await fetch('https://pypi.org/pypi/uv/0.13.7/json')).json();
 const artifact=meta.urls.find(a=>a.filename.endsWith('win_amd64.whl'));
 const bytes=new Uint8Array(await(await fetch(artifact.url)).arrayBuffer());
 if(createHash('sha256').update(bytes).digest('hex')!==artifact.digests.sha256)throw new Error('下载校验失败');
 await fs.writeFile('.tools/uv.zip',bytes);
 await run('powershell.exe',['-NoProfile','-Command',"Expand-Archive -LiteralPath '.tools/uv.zip' -DestinationPath '.tools/uv' -Force"]);
 const entries=await fs.readdir('.tools/uv',{recursive:true,withFileTypes:true});
 const exe=entries.find(e=>e.isFile()&&e.name==='uv.exe');if(!exe)throw new Error('未找到 Python 安装工具');
 const uv=path.join(exe.parentPath,exe.name);
 const env={UV_CACHE_DIR:path.join(root,'.uv-cache'),UV_PYTHON_INSTALL_DIR:path.join(root,'.python')};
 await run(uv,['python','install','3.12','--no-bin','--no-registry'],env);
 if(!existsSync(path.join(root,'.venv/Scripts/python.exe')))await run(uv,['venv','--python','3.12','.venv'],env);
 await run(uv,['pip','install','--python','.venv/Scripts/python.exe','-r','requirements.lock.txt'],env);
}else{
 if(!existsSync(path.join(root,'.venv/bin/python')))await run('python3.12',['-m','venv','.venv']);
 await run(path.join(root,'.venv/bin/python'),['-m','pip','install','-r','requirements.lock.txt']);
}
console.log('安装完成。运行 npm run dev:all，然后打开 http://127.0.0.1:3000/');
