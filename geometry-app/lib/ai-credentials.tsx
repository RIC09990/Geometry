'use client';
import {browserStorage} from '@/lib/browser-storage';
import {createContext,useContext,useEffect,useState,type ReactNode} from 'react';
import {aiProviders,type AiProvider} from './ai-providers';

type Mode='disabled'|'personal'|'server';
type Credentials={mode:Mode;key:string;ready:boolean;config:AiProvider;options:{provider?:AiProvider};headers?:Record<string,string>;useKey:(key:string,config?:AiProvider)=>void;useServer:()=>void;clear:()=>void};
const Context=createContext<Credentials>({mode:'disabled',key:'',config:aiProviders.deepseek.config,options:{},ready:false,useKey:()=>{},useServer:()=>{},clear:()=>{}});
const MODE='geometry.ai.mode.v1';
export function AiCredentialsProvider({children}:{children:ReactNode}){
 const [mode,setMode]=useState<Mode>('disabled');const [key,setKey]=useState('');const [ready,setReady]=useState(false);
 const [config,setConfig]=useState<AiProvider>(aiProviders.deepseek.config);
 useEffect(()=>{try{const stored=browserStorage.getItem(MODE);setMode(stored==='disabled'||stored==='personal'?stored:'server')}catch{setMode('server')}setReady(true);const changed=(e:StorageEvent)=>{if(e.key===MODE&&e.newValue==='disabled'){setKey('');setMode('disabled')}};window.addEventListener('storage',changed);return()=>window.removeEventListener('storage',changed)},[]);
 const remember=(next:Mode)=>{setMode(next);try{browserStorage.setItem(MODE,next)}catch{}};
 const clear=()=>{setKey('');remember('disabled')};
 return <Context.Provider value={{mode,key,ready,config,options:mode==='personal'?{provider:config}:{},headers:mode==='personal'?{'X-AI-Api-Key':key}:undefined,useKey:(value,next)=>{setKey(value);if(next)setConfig(next);remember('personal')},useServer:()=>{setKey('');remember('server')},clear}}>{children}</Context.Provider>;
}
export const useAiCredentials=()=>useContext(Context);
