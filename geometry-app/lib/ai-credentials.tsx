'use client';
import {browserStorage,browserSessionStorage} from '@/lib/browser-storage';
import {clearCredentialSession,readCredentialSession,saveCredentialSession} from './ai-credential-store';
import {createContext,useContext,useEffect,useState,type ReactNode} from 'react';
import {aiProviders,type AiProvider} from './ai-providers';

type Mode='disabled'|'personal'|'server';
type Credentials={mode:Mode;key:string;ready:boolean;config:AiProvider;options:{provider?:AiProvider};headers?:Record<string,string>;useKey:(key:string,config?:AiProvider)=>void;useServer:()=>void;clear:()=>void};
const Context=createContext<Credentials>({mode:'disabled',key:'',config:aiProviders.deepseek.config,options:{},ready:false,useKey:()=>{},useServer:()=>{},clear:()=>{}});
const MODE='geometry.ai.mode.v1';
export function AiCredentialsProvider({children}:{children:ReactNode}){
 const [mode,setMode]=useState<Mode>('disabled');const [key,setKey]=useState('');const [ready,setReady]=useState(false);
 const [config,setConfig]=useState<AiProvider>(aiProviders.deepseek.config);
 useEffect(()=>{
  let storedMode:Mode='server';
  try{const stored=browserStorage.getItem(MODE);storedMode=stored==='disabled'||stored==='personal'?stored:'server'}catch{}
  if(storedMode==='personal'){
   const saved=readCredentialSession(browserSessionStorage);
   if(saved){setKey(saved.key);setConfig(saved.config)}else{storedMode='disabled';try{browserStorage.setItem(MODE,'disabled')}catch{}}
  }
  setMode(storedMode);setReady(true);
  const changed=(e:StorageEvent)=>{if(e.key===MODE&&e.newValue==='disabled'){setKey('');setMode('disabled');clearCredentialSession(browserSessionStorage)}};
  window.addEventListener('storage',changed);return()=>window.removeEventListener('storage',changed);
 },[]);
 const remember=(next:Mode)=>{setMode(next);try{browserStorage.setItem(MODE,next)}catch{}};
 const clear=()=>{setKey('');remember('disabled');clearCredentialSession(browserSessionStorage)};
 return <Context.Provider value={{mode,key,ready,config,options:mode==='personal'?{provider:config}:{},headers:mode==='personal'?{'X-AI-Api-Key':key}:undefined,useKey:(value,next)=>{const target=next??config;setKey(value);setConfig(target);remember('personal');saveCredentialSession(browserSessionStorage,value,target)},useServer:()=>{setKey('');remember('server');clearCredentialSession(browserSessionStorage)},clear}}>{children}</Context.Provider>;
}
export const useAiCredentials=()=>useContext(Context);
