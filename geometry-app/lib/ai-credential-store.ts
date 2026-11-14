import type {AiProvider} from './ai-providers';

export const CREDENTIAL_SESSION_KEY='geometry.ai.session.v1';
const PROTOCOLS=['chat','responses','anthropic','gemini'];
const EFFORTS=['low','medium','high','max'];

export function readCredentialSession(storage:Storage):{key:string;config:AiProvider}|undefined{
 try{
  const raw=storage.getItem(CREDENTIAL_SESSION_KEY);
  if(!raw)return;
  const value=JSON.parse(raw) as {key?:unknown;config?:unknown};
  if(typeof value?.key!=='string'||!value.key.trim())return;
  const config=value.config as Partial<AiProvider>|undefined;
  if(!config||typeof config.provider!=='string'||typeof config.baseUrl!=='string'||typeof config.model!=='string'||!PROTOCOLS.includes(String(config.protocol)))return;
  const effort=EFFORTS.includes(String(config.reasoningEffort))?config.reasoningEffort:undefined;
  return {key:value.key,config:{provider:config.provider,baseUrl:config.baseUrl,protocol:config.protocol as AiProvider['protocol'],model:config.model,...(effort?{reasoningEffort:effort}:{})}};
 }catch{return}
}

export function saveCredentialSession(storage:Storage,key:string,config:AiProvider){
 try{storage.setItem(CREDENTIAL_SESSION_KEY,JSON.stringify({key,config}))}catch{}
}

export function clearCredentialSession(storage:Storage){
 try{storage.removeItem(CREDENTIAL_SESSION_KEY)}catch{}
}
