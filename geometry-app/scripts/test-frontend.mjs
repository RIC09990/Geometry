import {readdirSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const root=fileURLToPath(new URL('../',import.meta.url));
const files=readdirSync(new URL('../tests/',import.meta.url)).filter(file=>/\.test\.(?:ts|tsx|mjs)$/.test(file)).sort().map(file=>'tests/'+file);
const result=spawnSync(process.execPath,['--import','./scripts/frontend-test-loader.mjs','--test',...files],{cwd:root,stdio:'inherit'});
if(result.error)throw result.error;
process.exitCode=result.status??1;
