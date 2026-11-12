'use client';
import {useEffect,useState} from 'react';
import {KeyRound} from 'lucide-react';
import {api} from '@/lib/geometry';
import {useAiCredentials} from '@/lib/ai-credentials';
import {useT} from '@/lib/i18n';
import {AiKeyDialog} from './ai-key-dialog';
export function useTopicCredentials(){
 const credentials=useAiCredentials(),[server,setServer]=useState(false);
 useEffect(()=>{let live=true;void api<{configured:boolean}>('ai/status').then(s=>{if(live)setServer(s.configured)}).catch(()=>{});return()=>{live=false}},[]);
 return {...credentials,configured:credentials.ready&&(credentials.mode==='personal'?!!credentials.key:credentials.mode==='server'&&server),serverConfigured:server};
}
export function TopicKeyButton(){
 const t=useT(),credentials=useTopicCredentials(),[open,setOpen]=useState(false);
 return <><button type="button" className="text-button" onClick={()=>setOpen(true)}><KeyRound size={15}/>{t(credentials.configured?'管理 API Key':'填写 API Key')}</button>{open&&<AiKeyDialog serverConfigured={credentials.serverConfigured} onClose={()=>setOpen(false)}/>}</>;
}
