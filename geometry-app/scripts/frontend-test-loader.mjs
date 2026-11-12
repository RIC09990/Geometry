import {registerHooks} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import ts from 'typescript';
const root=path.resolve('.');
registerHooks({
 resolve(specifier,context,next){let file;if(specifier.startsWith('@/'))file=path.join(root,specifier.slice(2));else if(specifier.startsWith('.')&&context.parentURL?.startsWith('file:'))file=fileURLToPath(new URL(specifier,context.parentURL));if(file){for(const suffix of ['', '.ts','.tsx','.json'])if(fs.existsSync(file+suffix)&&fs.statSync(file+suffix).isFile())return {url:pathToFileURL(file+suffix).href,shortCircuit:true};}return next(specifier,context)},
 load(url,context,next){if(url.startsWith('file:')&&url.endsWith('.css'))return {format:'module',source:'',shortCircuit:true};if(url.startsWith('file:')&&/\.(tsx?|json)$/.test(url)&&!url.includes('/node_modules/')){const file=fileURLToPath(url),text=fs.readFileSync(file,'utf8');return {format:'module',source:file.endsWith('.json')?'export default '+text:ts.transpileModule(text,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,shortCircuit:true}}return next(url,context)}
});
