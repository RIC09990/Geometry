'use client';
import {useEffect,useRef,useState,type FormEvent} from 'react';
import {KeyRound} from 'lucide-react';
import {useAiCredentials} from '@/lib/ai-credentials';
import {aiProviders,detectAiProvider,suggestAiModel,deepseekThinkingEffort,type AiModel,type AiProvider,type AiReasoningEffort} from '@/lib/ai-providers';
import {api} from '@/lib/geometry';
import {useT} from '@/lib/i18n';
import {Modal} from './common';

export function AiKeyDialog({onClose,serverConfigured=false}:{onClose:()=>void;serverConfigured?:boolean}){
 const t=useT(),credentials=useAiCredentials();
 const hasSession=credentials.mode==='personal'&&!!credentials.key;
 const [config,setConfig]=useState<AiProvider>(hasSession?credentials.config:{...aiProviders.compatible.config,provider:''});
 const [key,setKey]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[detected,setDetected]=useState(false);
 const [models,setModels]=useState<AiModel[]>([]),[advanced,setAdvanced]=useState(false);
 const manual=useRef(false),request=useRef<AbortController|null>(null);
 const reusable=hasSession&&config.provider===credentials.config.provider&&config.baseUrl===credentials.config.baseUrl;
 useEffect(()=>()=>request.current?.abort(),[]);
 function cancel(resetModels=true){request.current?.abort();request.current=null;setBusy(false);setError('');if(resetModels)setModels([])}
 function enterKey(value:string){
  cancel();setKey(value);if(manual.current)return;
  const provider=detectAiProvider(value);setDetected(!!provider);
  if(provider)setConfig({...aiProviders[provider].config});
  else if(value.trim()||!hasSession)setConfig({...aiProviders.compatible.config,provider:''});
  else setConfig(credentials.config);
 }
 async function useKey(e:FormEvent){
  e.preventDefault();if(busy)return;
  const value=key.trim()||(reusable?credentials.key:'');
  if(!value||value.length>4096||/[^\x21-\x7e]/.test(value)){setError(t('请检查 API Key 格式。'));return}
  if(!config.provider){setError(t('无法仅凭密钥确定服务商，请选择一次。'));return}
  try{const url=new URL(config.baseUrl);if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash)throw new Error()}catch{setError(t('请填写服务商的 HTTPS Base URL。'));setAdvanced(true);return}
  let selected=config;
  if(!selected.model.trim()){
   if(selected.provider==='compatible'||selected.baseUrl.replace(/\/$/,'')!==aiProviders[selected.provider]?.config.baseUrl){setAdvanced(true);setError(t('自定义服务请填写模型名称。'));return}
   const abort=new AbortController();request.current=abort;setBusy(true);setError('');
   try{
    const result=await api<{models:AiModel[]}>('ai/models',{provider:selected},abort.signal,{'X-AI-Api-Key':value});
    if(abort.signal.aborted)return;
    const model=suggestAiModel(selected.provider,result.models);setModels(result.models);
    if(!model){setAdvanced(true);setError(t('已连接，但未找到可自动选择的对话模型，请选择或填写模型。'));return}
    selected={...selected,model};setConfig(selected);
   }catch(err){if(!abort.signal.aborted){setAdvanced(true);setError(t((err as Error).message))}return}
   finally{if(request.current===abort){request.current=null;setBusy(false)}}
  }
  credentials.useKey(value,{...selected,model:selected.model.trim()});onClose();
 }
 let host='';try{host=new URL(config.baseUrl).host}catch{}
 const thinkingEffort=deepseekThinkingEffort(config);
 return <Modal title={t('AI 服务与 API Key')} onClose={onClose}><form className="ai-key-form" onSubmit={useKey}>
  <label className="field">API Key<input type="password" autoComplete="off" spellCheck={false} aria-label="API Key" value={key} placeholder={reusable?t('留空继续使用本次密钥'):t('粘贴 API Key，自动识别服务商')} onChange={e=>enterKey(e.target.value)} maxLength={4096}/></label>
  <label className="field">{t('服务商')}<select aria-label={t('服务商')} value={config.provider} onChange={e=>{cancel();manual.current=!!e.target.value;setDetected(false);setConfig(e.target.value?{...aiProviders[e.target.value].config}:{...aiProviders.compatible.config,provider:''})}}>
   <option value="">{t('自动识别')}</option>{Object.entries(aiProviders).map(([id,p])=><option key={id} value={id}>{t(p.label)}</option>)}
  </select></label>
  {detected&&<p role="status">{t('已按密钥格式识别服务商；连接时再验证。')}</p>}
  {!!key.trim()&&!config.provider&&<p role="status">{t('无法仅凭密钥确定服务商，请选择一次。')}</p>}
  {!!config.provider&&config.provider!=='compatible'&&host&&<p>{t('连接至')} {host}{!config.model&&' · '+t('自动读取可用模型')}</p>}
  {thinkingEffort&&<label className="field">{t('思考档位')}<select aria-label={t('思考档位')} value={thinkingEffort} onChange={e=>{cancel(false);setConfig({...config,reasoningEffort:e.target.value as AiReasoningEffort})}}>
   <option value="low">{t('较快')}</option><option value="high">{t('中档')}</option><option value="max">{t('最高（Max）')}</option>
  </select></label>}
  <details open={advanced||config.provider==='compatible'} onToggle={e=>setAdvanced(e.currentTarget.open)}>
   <summary>{t('接口与模型（可选）')}</summary>
   <label className="field">{t('接口地址')} (Base URL)<input type="url" aria-label="Base URL" placeholder="https://api.example.com/v1" value={config.baseUrl} onChange={e=>{cancel();manual.current=true;setConfig({...config,baseUrl:e.target.value})}}/></label>
   <label className="field">{t('模型名称')}<input aria-label={t('模型名称')} list="ai-model-options" placeholder={t('留空自动选择可用模型')} value={config.model} onChange={e=>{cancel(false);setConfig({...config,model:e.target.value})}} maxLength={256}/><datalist id="ai-model-options">{models.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</datalist></label>
   {config.provider==='compatible'&&<label className="field">{t('接口协议')}<select value={config.protocol} onChange={e=>{cancel();setConfig({...config,protocol:e.target.value as AiProvider['protocol']})}}><option value="chat">Chat Completions</option><option value="responses">Responses</option><option value="anthropic">Anthropic Messages</option><option value="gemini">Gemini</option></select></label>}
  </details>
  <p>{t('密钥仅保留在当前会话内，不会写入本机文件或浏览器长期存储。')}</p>
  {error&&<p role="alert" className="ai-key-error">{error}</p>}<div className="ai-key-actions"><button className="button primary" disabled={busy||(!key.trim()&&!(reusable&&credentials.key))}><KeyRound size={16}/>{t(busy?'正在读取模型…':'连接并使用')}</button><button type="button" className="button secondary" onClick={()=>{cancel();credentials.clear();onClose()}}>{t('清除并停用')}</button></div>
  {serverConfigured&&<button type="button" className="text-button" onClick={()=>{cancel();credentials.useServer();onClose()}}>{t('改用服务器配置')}</button>}
 </form></Modal>;
}
