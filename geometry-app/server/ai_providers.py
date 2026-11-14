"""Small HTTP adapters; no vendor SDK or model is bundled into the website."""
import asyncio
import ipaddress
import json
import socket
from urllib.parse import urlsplit,quote
from pydantic import BaseModel,Field,model_validator
from typing import Literal
from fastapi import HTTPException
from .config import setting

PRESETS={
 'deepseek':{'label':'DeepSeek','baseUrl':'https://api.deepseek.com','protocol':'chat','model':'deepseek-flash'},
 'openai':{'label':'OpenAI','baseUrl':'https://api.openai.com/v1','protocol':'responses','model':''},
 'anthropic':{'label':'Claude / Anthropic','baseUrl':'https://api.anthropic.com/v1','protocol':'anthropic','model':''},
 'gemini':{'label':'Google Gemini','baseUrl':'https://generativelanguage.googleapis.com/v1beta','protocol':'gemini','model':''},
 'compatible':{'label':'其他 / 自定义服务','baseUrl':'','protocol':'chat','model':''},
}

class ProviderOptions(BaseModel):
    provider:str=Field(default='deepseek',max_length=100)
    baseUrl:str=Field(default='',max_length=2048)
    protocol:Literal['chat','responses','anthropic','gemini']='chat'
    model:str=Field(default='',max_length=256)
    reasoningEffort:Literal['low','medium','high','max']|None=None

    @model_validator(mode='after')
    def valid_url(self):
        if self.baseUrl:
            url=urlsplit(self.baseUrl)
            if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError('接口地址请填写服务商的 HTTPS Base URL，不要包含密钥、查询参数或账号密码。')
            try:literal=ipaddress.ip_address(url.hostname)
            except ValueError:literal=None
            if literal and not literal.is_global:raise ValueError('接口地址不能指向本机或内网。')
            if url.hostname.lower()=='localhost' or url.hostname.lower().endswith(('.localhost','.local')):raise ValueError('接口地址不能指向本机或内网。')
        return self

def resolve_provider(options=None):
    if options is None:
        name=setting('AI_PROVIDER','deepseek');preset=PRESETS.get(name,PRESETS['compatible'])
        options=ProviderOptions(provider=name,baseUrl=setting('AI_BASE_URL',preset['baseUrl']),protocol=setting('AI_PROTOCOL',preset['protocol']),
            model=setting('AI_MODEL',setting('DEEPSEEK_MODEL',preset['model']) if name=='deepseek' else preset['model']),
            reasoningEffort=setting('AI_REASONING_EFFORT') or None)
    preset=PRESETS.get(options.provider,{})
    selected=options.model_copy(update={'baseUrl':options.baseUrl or preset.get('baseUrl',''),'model':options.model or preset.get('model','')})
    # Keep existing open pages on the requested maximum setting without a refresh
    # that would discard their session-only API key. Custom endpoints keep defaults.
    if (selected.provider=='deepseek' and urlsplit(selected.baseUrl).hostname=='api.deepseek.com'
            and selected.protocol in ('chat','responses') and selected.reasoningEffort is None):
        selected=selected.model_copy(update={'reasoningEffort':'max'})
    return selected

def server_key():return setting('AI_API_KEY') or setting('DEEPSEEK_API_KEY')

def endpoint(options,path):
    base=options.baseUrl.rstrip('/')
    for suffix in ('/chat/completions','/responses','/messages'):
        if base.endswith(suffix):base=base[:-len(suffix)]
    return base+'/'+path.lstrip('/')

async def check_destination(options,transport=None,*,require_model=True):
    if not options.baseUrl or (require_model and not options.model):raise HTTPException(422,'请在 API 管理中填写接口地址和模型名称。')
    # Official presets avoid DNS work per call. Custom servers must resolve publicly.
    host=urlsplit(options.baseUrl).hostname
    if transport is not None or host in {'api.deepseek.com','api.openai.com','api.anthropic.com','generativelanguage.googleapis.com'}:return
    try:addresses=await asyncio.to_thread(socket.getaddrinfo,host,443,type=socket.SOCK_STREAM)
    except OSError:raise HTTPException(422,'接口地址无法解析，请检查服务商的 Base URL。') from None
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise HTTPException(422,'接口地址不能指向本机或内网。')

def reasoning_fields(options,protocol=None):
    """Send an explicit user choice using the selected provider's wire format.

    OpenAI-compatible chat and Responses endpoints accept an explicit effort.
    Anthropic and Gemini use different thinking parameters and are refused
    instead of silently translated. No level is inferred for a third-party
    endpoint; only the official DeepSeek host defaults to the maximum.
    """
    if options.reasoningEffort is None:return {}
    protocol=protocol or options.protocol
    if protocol not in ('chat','responses'):
        raise HTTPException(422,'思考档位仅支持 Chat Completions 或 Responses 协议。')
    # DeepSeek names its middle setting high; medium is an official alias.
    effort='high' if options.reasoningEffort=='medium' else options.reasoningEffort
    if protocol=='responses':return {'reasoning':{'effort':effort}}
    fields={'reasoning_effort':effort}
    # DeepSeek's Chat protocol turns thinking on with this field. Other
    # OpenAI-compatible servers may reject unknown fields, so mark only
    # DeepSeek targets (official host or a DeepSeek model name).
    if urlsplit(options.baseUrl).hostname=='api.deepseek.com' or 'deepseek' in options.model.lower():
        fields['thinking']={'type':'enabled'}
    return fields


def request_body(messages,options,system,structured,*,stream=False):
    tokens=8192 if structured else 4096
    reasoning=reasoning_fields(options)
    # DeepSeek's thinking and answer share the output budget. The old 4K/8K
    # cap could consume every token on Max reasoning before an answer existed.
    # Keep the selected effort and use the official thinking-mode default.
    provider_budget={} if reasoning else {'max_output_tokens':tokens} if options.protocol=='responses' else {'max_tokens':tokens}
    if options.protocol=='anthropic':
        items=[]
        for m in messages:
            blocks=[{'type':'text','text':m.content}]
            for image in m.images:
                mime,data=image.dataUrl.split(',',1);blocks.append({'type':'image','source':{'type':'base64','media_type':mime[5:].split(';')[0],'data':data}})
            items.append({'role':m.role,'content':blocks})
        return 'messages',{'model':options.model,'system':system,'messages':items,'max_tokens':tokens}
    if options.protocol=='gemini':
        items=[]
        for m in messages:
            parts=[{'text':m.content}]
            for image in m.images:
                mime,data=image.dataUrl.split(',',1);parts.append({'inlineData':{'mimeType':mime[5:].split(';')[0],'data':data}})
            items.append({'role':'model' if m.role=='assistant' else 'user','parts':parts})
        return 'models/'+quote(options.model,safe='')+':generateContent',{'systemInstruction':{'parts':[{'text':system}]},'contents':items,'generationConfig':{'maxOutputTokens':tokens,**({'responseMimeType':'application/json'} if structured else {})}}
    if options.protocol=='responses':
        items=[]
        for m in messages:
            content=m.content if not m.images else [{'type':'input_text','text':m.content},*[{'type':'input_image','image_url':image.dataUrl} for image in m.images]]
            items.append({'role':m.role,'content':content})
        return 'responses',{'model':options.model,'instructions':system,'input':items,**provider_budget,'store':False,
                            **reasoning,
                            **({'text':{'format':{'type':'json_object'}}} if structured else {})}
    items=[]
    for m in messages:
        content=m.content if not m.images else [{'type':'text','text':m.content},*[{'type':'image_url','image_url':{'url':image.dataUrl,**({'detail':'original'} if options.provider=='deepseek' else {})}} for image in m.images]]
        items.append({'role':m.role,'content':content})
    return 'chat/completions',{'model':options.model,'messages':[{'role':'system','content':system},*items],'stream':stream,
        **({'stream_options':{'include_usage':True}} if stream else {}),
        **reasoning,
        **({'max_completion_tokens':tokens} if urlsplit(options.baseUrl).hostname=='api.openai.com' else provider_budget),
        **({'response_format':{'type':'json_object'}} if structured else {})}


def stream_chat_events(lines):
    """Yield ('reasoning'|'text'|'finish'|'usage', value) from Chat Completions SSE.

    Text stays the raw JSON fragment: the caller decodes the tutor envelope.
    """
    for line in lines:
        line=line.strip()
        if not line.startswith('data:'):continue
        payload=line[5:].strip()
        if not payload or payload=='[DONE]':continue
        try:chunk=json.loads(payload)
        except ValueError:continue
        if not isinstance(chunk,dict):continue
        if isinstance(chunk.get('usage'),dict):yield 'usage',chunk['usage']
        choices=chunk.get('choices')
        if not isinstance(choices,list) or not choices:continue
        choice=choices[0]
        if not isinstance(choice,dict):continue
        delta=choice.get('delta')
        if isinstance(delta,dict):
            reasoning=delta.get('reasoning_content',delta.get('reasoning'))
            if isinstance(reasoning,str) and reasoning:yield 'reasoning',reasoning
            content=delta.get('content')
            if isinstance(content,str) and content:yield 'text',content
        finish=choice.get('finish_reason')
        if isinstance(finish,str) and finish:yield 'finish',finish


def normalize_usage(usage):
    """Normalize provider token counters; omit anything the provider did not report."""
    if not isinstance(usage,dict):return {}
    details=usage.get('prompt_tokens_details')
    cached=usage.get('prompt_cache_hit_tokens',details.get('cached_tokens') if isinstance(details,dict) else None)
    completion_details=usage.get('completion_tokens_details')
    reasoning=usage.get('reasoning_tokens',completion_details.get('reasoning_tokens') if isinstance(completion_details,dict) else None)
    values={'promptTokens':usage.get('prompt_tokens',usage.get('input_tokens')),'cachedTokens':cached,
            'completionTokens':usage.get('completion_tokens',usage.get('output_tokens')),'reasoningTokens':reasoning}
    return {k:v for k,v in values.items() if isinstance(v,(int,float)) and not isinstance(v,bool)}

USER_AGENT='Geometry/1.0'
OPENCODE_SESSION_HEADER='x-opencode-session'

def provider_headers(options,key,session_id=None):
    headers=({'x-api-key':key,'anthropic-version':'2023-06-01'} if options.protocol=='anthropic'
             else {'x-goog-api-key':key} if options.protocol=='gemini'
             else {'Authorization':'Bearer '+key})
    # Identify the client; OpenCode rejects generic SDK/HTTP-library agents in its abuse policy.
    headers['User-Agent']=USER_AGENT
    # OpenCode routes and caches per conversation and returns 400 without this header.
    if session_id and urlsplit(options.baseUrl).hostname=='opencode.ai':
        headers[OPENCODE_SESSION_HEADER]=session_id
    return headers

async def list_models(client,options,key):
    """Read public model metadata from one explicitly selected official service."""
    preset=PRESETS[options.provider]
    # Listing uses the selected vendor's authentication, independent of chat protocol.
    options=options.model_copy(update={'protocol':preset['protocol']})
    params={'pageSize':1000} if options.provider=='gemini' else {'limit':1000} if options.provider=='anthropic' else {}
    models={};cursors=set()
    for _ in range(10):
        response=await client.get(endpoint(options,'models'),headers=provider_headers(options,key),params=params)
        if response.status_code!=200:
            reasons={401:'API Key 无效，请检查服务商和密钥是否匹配。',403:'该密钥没有查询模型的权限，请手动填写模型名称。',429:'AI 服务繁忙，请稍后重试。'}
            raise HTTPException(502,reasons.get(response.status_code,'无法获取模型列表，请检查服务商或手动填写模型名称。'))
        data=response.json()
        if not isinstance(data,dict) or data.get('error') or data.get('type')=='error':
            raise ValueError('Invalid model list response')
        items=data.get('models',[]) if options.provider=='gemini' else data['data']
        if not isinstance(items,list):raise ValueError('Invalid model list')
        for item in items:
            if not isinstance(item,dict):raise ValueError('Invalid model metadata')
            if options.provider=='gemini':
                if 'generateContent' not in item.get('supportedGenerationMethods',[]):continue
                identifier=item.get('name','')
                if isinstance(identifier,str):identifier=identifier.removeprefix('models/')
                name=item.get('displayName')
            else:
                identifier=item.get('id');name=item.get('display_name') or item.get('name')
            if item.get('lifecycle')=='retired':continue
            if not isinstance(identifier,str) or not identifier or len(identifier)>256:continue
            if any(c.isspace() or ord(c)<32 for c in identifier) or key in identifier:continue
            name=name if isinstance(name,str) and key not in name else identifier
            models[identifier]={'id':identifier,'name':(name or identifier)[:256]}
        cursor=data.get('nextPageToken') if options.provider=='gemini' else data.get('last_id') if options.provider=='anthropic' and data.get('has_more') else None
        if not cursor:return list(models.values())
        if not isinstance(cursor,str) or cursor in cursors:raise ValueError('Invalid model list cursor')
        cursors.add(cursor);params['pageToken' if options.provider=='gemini' else 'after_id']=cursor
    raise ValueError('Too many model list pages')


def response_text(data,protocol):
    if protocol=='anthropic':return '\n'.join(c['text'] for c in data['content'] if c.get('type')=='text'), 'length' if data.get('stop_reason')=='max_tokens' else 'stop'
    if protocol=='gemini':
        candidate=data['candidates'][0]
        return '\n'.join(p['text'] for p in candidate['content']['parts'] if 'text' in p and not p.get('thought')),'length' if candidate.get('finishReason')=='MAX_TOKENS' else 'stop'
    if protocol=='responses':return '\n'.join(c['text'] for o in data['output'] if o.get('type')=='message' for c in o.get('content',[]) if c.get('type')=='output_text'),'length' if (data.get('incomplete_details') or {}).get('reason')=='max_output_tokens' else 'stop'
    return data['choices'][0]['message']['content'],data['choices'][0].get('finish_reason','stop')

async def native_search(client,query,options,key):
    if options.protocol=='responses' or options.provider=='openai':
        path='responses';body={'model':options.model,'input':query+'\nSearch the web and cite the matching source.','tools':[{'type':'web_search'}],'max_output_tokens':1500,'store':False}
    elif options.protocol=='anthropic':
        path='messages';body={'model':options.model,'messages':[{'role':'user','content':query}],'tools':[{'type':'web_search_20250305','name':'web_search','max_uses':2}],'max_tokens':1800}
    elif options.protocol=='gemini':
        path='models/'+quote(options.model,safe='')+':generateContent';body={'contents':[{'parts':[{'text':query}]}],'tools':[{'google_search':{}}]}
    else:raise HTTPException(502,'当前服务未提供标准联网搜索接口。')
    responses=[]
    for attempt in range(3):
        response=await client.post(endpoint(options,path),headers=provider_headers(options,key),json=body)
        if response.status_code!=200:raise HTTPException(502,'联网搜索暂时不可用')
        data=response.json()
        if not isinstance(data,dict) or data.get('error') or data.get('type')=='error':
            raise HTTPException(502,'联网搜索暂时不可用')
        responses.append(data)
        if options.protocol!='anthropic' or path!='messages':break
        blocks=data['content']
        if not isinstance(blocks,list) or any(not isinstance(block,dict) for block in blocks):
            raise ValueError('Invalid search content')
        for block in blocks:
            if block.get('type')=='web_search_tool_result' and not isinstance(block.get('content'),list):
                # Anthropic reports search failures inside HTTP 200 responses.
                raise HTTPException(502,'联网搜索暂时不可用')
        if data.get('stop_reason')!='pause_turn':break
        if attempt==2 or not blocks:raise HTTPException(502,'联网搜索暂时不可用')
        # Continuations contain only new content; preserve every paused turn as-is.
        body['messages'].append({'role':'assistant','content':blocks})
    sources=[]
    def collect(value):
        if isinstance(value,dict):
            url=value.get('url') or value.get('uri')
            if isinstance(url,str) and url.startswith(('http://','https://')):
                sources.append({'title':str(value.get('title') or url),'url':url,'content':str(value.get('cited_text') or '')})
            for v in value.values():collect(v)
        elif isinstance(value,list):
            for v in value:collect(v)
    collect(responses)
    protocol='responses' if options.provider=='openai' else options.protocol
    summary='\n'.join(response_text(data,protocol)[0] for data in responses)
    unique={s['url']:s for s in sources}
    for source in unique.values():source['content']=(source['content']+'\n'+summary)[:8000]
    return list(unique.values())

async def search(client,query,options,key):
    if options.provider!='deepseek' or urlsplit(options.baseUrl).hostname!='api.deepseek.com':
        return await native_search(client,query,options,key)
    response=await client.post('https://api.deepseek.com/v1/tools/search',headers={'Authorization':'Bearer '+key},json={'query':query.strip()[:128],'count':5,'need_content':True})
    if response.status_code!=200:raise HTTPException(502,'联网搜索暂时不可用')
    results=response.json()['results']
    return [{'title':str(item.get('title','')),'url':str(item.get('url','')),'content':str(item.get('content') or item.get('summary') or item.get('snippet',''))[:6000]} for item in results if str(item.get('url','')).startswith(('https://','http://'))]
