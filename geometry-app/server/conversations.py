"""Local conversation history for the AI page, stored beside other local state."""
import json
import os
import re
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field

from .models import StrictModel

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / '.local' / 'ai-conversations'
MAX_BYTES = 24 * 1024 * 1024
MAX_SEARCH_CHARS = 20000
ID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

router = APIRouter(prefix='/api/ai/conversations')


class StoredImage(StrictModel):
    name:str=Field(default='图片',max_length=255)
    dataUrl:str=Field(max_length=45_000_000)


class StoredSource(StrictModel):
    title:str=Field(default='',max_length=2048)
    url:str=Field(max_length=2048)


class StoredUsage(StrictModel):
    promptTokens:float|None=None
    cachedTokens:float|None=None
    completionTokens:float|None=None
    reasoningTokens:float|None=None
    firstTokenMs:float|None=None
    elapsedMs:float|None=None
    generationMs:float|None=None
    tokensPerSecond:float|None=None


class StoredMessage(StrictModel):
    role:Literal['user','assistant']
    content:str=Field(max_length=100_000)
    reasoning:str|None=Field(default=None,max_length=100_000)
    images:list[StoredImage]=Field(default_factory=list,max_length=60)
    sources:list[StoredSource]=Field(default_factory=list,max_length=20)
    searchStatus:str|None=Field(default=None,max_length=32)
    mode:str|None=Field(default=None,max_length=16)
    elapsedMs:float|None=None
    usage:StoredUsage|None=None


class StoredSummary(StrictModel):
    text:str=Field(max_length=8000)
    through:int=Field(ge=0)


class ConversationInput(StrictModel):
    id:str
    title:str=Field(default='',max_length=120)
    messages:list[StoredMessage]=Field(default_factory=list,max_length=200)
    lastUsage:StoredUsage|None=None
    summary:StoredSummary|None=None


class RenameInput(StrictModel):
    title:str=Field(min_length=1,max_length=120)


def _document_path(conversation_id):
    if not ID_PATTERN.fullmatch(conversation_id):
        raise HTTPException(422,'会话标识格式不正确')
    return STORE/(conversation_id+'.json')


def _meta_path(conversation_id):
    return STORE/(conversation_id+'.meta.json')


def _write(path,value):
    STORE.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    os.replace(temporary,path)


def _read(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:return None
    except (OSError,ValueError):raise HTTPException(500,'本机会话记录读取失败。') from None


def _auto_title(document):
    for message in document.get('messages') or []:
        if message.get('role')=='user':
            text=str(message.get('content') or '').strip()
            if text:return text.splitlines()[0][:30]+('…' if len(text.splitlines()[0])>30 else '')
    return '新对话'


def _search_text(document):
    parts=[]
    for message in document.get('messages') or []:
        parts.append(str(message.get('content') or ''))
        if message.get('reasoning'):parts.append(str(message['reasoning']))
    return '\n'.join(parts)[:MAX_SEARCH_CHARS]


def _meta(document):
    messages=document.get('messages') or []
    preview=''
    for message in messages:
        if message.get('role')=='user' and str(message.get('content') or '').strip():
            preview=str(message['content']).strip().replace('\n',' ')[:80]
            break
    return {'id':document['id'],'title':document.get('title') or _auto_title(document),
            'createdAt':document.get('createdAt',0),'updatedAt':document.get('updatedAt',0),
            'messageCount':len(messages),'preview':preview,'text':_search_text(document)}


def _public(meta):
    return {key:value for key,value in meta.items() if key!='text'}


def _stored_meta(conversation_id):
    meta=_read(_meta_path(conversation_id))
    if isinstance(meta,dict) and isinstance(meta.get('title'),str):
        return meta
    document=_read(_document_path(conversation_id))
    if not isinstance(document,dict):return None
    meta=_meta(document)
    _write(_meta_path(conversation_id),meta)
    return meta


@router.get('')
def list_conversations(q:str=''):
    STORE.mkdir(parents=True,exist_ok=True)
    query=q.strip().casefold()
    summaries=[]
    for path in STORE.glob('*.meta.json'):
        conversation_id=path.name[:-len('.meta.json')]
        if not ID_PATTERN.fullmatch(conversation_id):continue
        meta=_stored_meta(conversation_id)
        if not meta:continue
        if query and query not in (str(meta.get('title',''))+'\n'+str(meta.get('preview',''))+'\n'+str(meta.get('text',''))).casefold():
            continue
        summaries.append(_public(meta))
    summaries.sort(key=lambda item:item.get('updatedAt',0),reverse=True)
    return summaries


@router.post('')
def save_conversation(request:ConversationInput):
    path=_document_path(request.id)
    previous=_read(path) or {}
    now=time.time()
    document={'id':request.id,'title':request.title.strip() or str(previous.get('title') or ''),
              'createdAt':previous.get('createdAt') or now,'updatedAt':now,
              'messages':[message.model_dump() for message in request.messages],
              'lastUsage':request.lastUsage.model_dump() if request.lastUsage else None,
              'summary':request.summary.model_dump() if request.summary else None}
    if not document['title']:document['title']=_auto_title(document)
    encoded=json.dumps(document,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    if len(encoded)>MAX_BYTES:
        raise HTTPException(413,'这次对话超过本机存储上限（24 MiB），请精简图片后重试。')
    _write(path,document)
    meta=_meta(document)
    _write(_meta_path(request.id),meta)
    return _public(meta)


@router.get('/{conversation_id}')
def read_conversation(conversation_id:str):
    document=_read(_document_path(conversation_id))
    if not isinstance(document,dict):raise HTTPException(404,'没有找到这次对话')
    return document


@router.patch('/{conversation_id}')
def rename_conversation(conversation_id:str,request:RenameInput):
    path=_document_path(conversation_id)
    document=_read(path)
    if not isinstance(document,dict):raise HTTPException(404,'没有找到这次对话')
    document['title']=request.title.strip()
    document['updatedAt']=time.time()
    _write(path,document)
    meta=_meta(document)
    _write(_meta_path(conversation_id),meta)
    return _public(meta)


@router.delete('/{conversation_id}')
def delete_conversation(conversation_id:str):
    path=_document_path(conversation_id)
    for target in (path,_meta_path(conversation_id)):
        try:target.unlink()
        except FileNotFoundError:pass
        except OSError:raise HTTPException(500,'本机会话记录删除失败。') from None
    return {'deleted':True}
