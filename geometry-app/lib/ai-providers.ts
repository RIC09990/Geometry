export type AiReasoningEffort='low'|'medium'|'high'|'max';
export type AiProvider={provider:string;baseUrl:string;protocol:'chat'|'responses'|'anthropic'|'gemini';model:string;reasoningEffort?:AiReasoningEffort};
export const aiProviders:Record<string,{label:string;config:AiProvider}>={
 deepseek:{label:'DeepSeek',config:{provider:'deepseek',baseUrl:'https://api.deepseek.com',protocol:'chat',model:'deepseek-flash',reasoningEffort:'max'}},
 openai:{label:'OpenAI',config:{provider:'openai',baseUrl:'https://api.openai.com/v1',protocol:'responses',model:''}},
 anthropic:{label:'Claude / Anthropic',config:{provider:'anthropic',baseUrl:'https://api.anthropic.com/v1',protocol:'anthropic',model:''}},
 gemini:{label:'Google Gemini',config:{provider:'gemini',baseUrl:'https://generativelanguage.googleapis.com/v1beta',protocol:'gemini',model:''}},
 compatible:{label:'其他 / 自定义服务',config:{provider:'compatible',baseUrl:'',protocol:'chat',model:''}},
};

/** Use the requested maximum by default; DeepSeek's medium alias still means high. */
export function deepseekThinkingEffort(config:AiProvider):'low'|'high'|'max'|undefined{
 if(config.provider!=='deepseek'||!['chat','responses'].includes(config.protocol))return;
 try{const url=new URL(config.baseUrl);if(url.protocol!=='https:'||url.hostname!=='api.deepseek.com')return}catch{return}
 if(config.reasoningEffort==='low')return 'low';
 if(config.reasoningEffort==='medium'||config.reasoningEffort==='high')return 'high';
 return 'max';
}

// This local format hint is not authentication. Never probe different services with one key.
export function detectAiProvider(key:string):string|null{
 const value=key.trim();
 if(/^sk-ant-api\d+-[A-Za-z0-9_-]+$/.test(value))return 'anthropic';
 if(/^sk-(?:proj|svcacct)-[A-Za-z0-9_-]+$/.test(value))return 'openai';
 if(/^AIza[A-Za-z0-9_-]{35}$/.test(value))return 'gemini';
 return null;
}
export type AiModel={id:string;name:string};
export function suggestAiModel(provider:string,models:AiModel[]):string{
 if(provider==='deepseek')return models.some(({id})=>id==='deepseek-flash')?'deepseek-flash':'';
 const candidates=models.filter(({id})=>{
  if(/(?:audio|realtime|tts|transcrib|whisper|embedding|moderation|image|video|robot|computer-use|deep-research|search|codex)/i.test(id))return false;
  if(provider==='openai')return /^gpt-\d/i.test(id)&&!/(?:instruct|pro(?:-|$)|nano|turbo)/i.test(id);
  if(provider==='anthropic')return /^claude-(?:sonnet|haiku|\d)/i.test(id)&&!id.includes('opus');
  if(provider==='gemini')return /^gemini-.*(?:flash|pro)/i.test(id)&&!id.includes('lite');
  return /^deepseek-(?:flash|chat)/i.test(id);
 });
 const rank=({id}:AiModel)=>[/(?:preview|exp(?:-|$)|latest)/i.test(id)?0:1,/(?:mini|sonnet|flash)/i.test(id)?1:0];
 candidates.sort((a,b)=>{const x=rank(a),y=rank(b);return y[0]-x[0]||y[1]-x[1]||b.id.localeCompare(a.id,undefined,{numeric:true})});
 return candidates[0]?.id||'';
}
