import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
if(process.platform==='win32'){
 const args=['-u',fileURLToPath(new URL('./local.py',import.meta.url))];
 if(process.env.GEOMETRY_NO_OPEN==='1')args.push('--no-browser');
 const child=spawn(fileURLToPath(new URL('../.venv/Scripts/python.exe',import.meta.url)),args,{cwd:root,stdio:'inherit'});
 child.on('exit',code=>{process.exitCode=code||0});
 child.on('error',error=>{console.error(error.message);process.exitCode=1});
}else{
 const child=spawn(process.execPath,['scripts/preview.mjs'],{cwd:root,stdio:'inherit'});
 child.on('exit',code=>process.exitCode=code||0);
}
