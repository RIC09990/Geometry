"""Saved explorations on this machine, one JSON document per topic."""
import json
import os
import re
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from fastapi import APIRouter, HTTPException
from pydantic import Field

from .models import StrictModel, Problem

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / '.local' / 'topics'
MAX_BYTES = 32 * 1024 * 1024
ID_PATTERN = re.compile(r'^custom-[A-Za-z0-9-]{1,80}$')
# Keep document and metadata operations together in the local server's worker threads.
STORE_LOCK = Lock()

router = APIRouter(prefix='/api/topics')


class TopicInput(StrictModel):
    id:str
    problem:Problem
    recognizedText:str=Field(default='',max_length=20000)
    createdAt:str=Field(default='',max_length=40)
    updatedAt:str=Field(default='',max_length=40)
    result:dict|None=None


class RenameInput(StrictModel):
    title:str=Field(min_length=1,max_length=80)


def _path(topic_id):
    if not ID_PATTERN.fullmatch(topic_id):
        raise HTTPException(422,'探究标识格式不正确')
    return STORE/(topic_id+'.json')


def _meta_path(topic_id):
    return STORE/(topic_id+'.meta.json')


def _write(path,value):
    STORE.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,
                                prefix=path.name+'.',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name)
            json.dump(value,stream,ensure_ascii=False,separators=(',',':'))
        os.replace(temporary,path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def _read(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:return None
    except (OSError,ValueError):raise HTTPException(500,'本机探究记录读取失败。') from None


def _meta(document):
    return {'id':document['id'],'title':document['problem']['title'],
            'createdAt':document.get('createdAt',''),'updatedAt':document.get('updatedAt',''),
            'recognizedText':str(document.get('recognizedText') or '')[:200]}


def _stored_meta(topic_id):
    meta=_read(_meta_path(topic_id))
    if isinstance(meta,dict) and isinstance(meta.get('title'),str):return meta
    document=_read(_path(topic_id))
    if not isinstance(document,dict):return None
    meta=_meta(document)
    _write(_meta_path(topic_id),meta)
    return meta


def _save(document):
    encoded=json.dumps(document,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    if len(encoded)>MAX_BYTES:
        raise HTTPException(413,'这次探究超过本机存储上限（32 MiB），请精简图片或记录后重试。')
    _write(_path(document['id']),document)
    meta=_meta(document)
    _write(_meta_path(document['id']),meta)
    return meta


@router.get('')
def list_topics(q:str=''):
    with STORE_LOCK:
        STORE.mkdir(parents=True,exist_ok=True)
        query=q.strip().casefold()
        items=[]
        for path in STORE.glob('*.meta.json'):
            topic_id=path.name[:-len('.meta.json')]
            if not ID_PATTERN.fullmatch(topic_id):continue
            meta=_stored_meta(topic_id)
            if not meta:continue
            if query and query not in (str(meta.get('title',''))+'\n'+str(meta.get('recognizedText',''))).casefold():continue
            items.append(meta)
        items.sort(key=lambda item:item.get('updatedAt',''),reverse=True)
        return items


@router.post('')
def save_topic(request:TopicInput):
    with STORE_LOCK:
        path=_path(request.id)
        previous=_read(path) or {}
        now=time.strftime('%Y-%m-%dT%H:%M:%S',time.gmtime())+'Z'
        document={'id':request.id,'problem':request.problem.model_dump(),
                  'recognizedText':request.recognizedText or str(previous.get('recognizedText') or ''),
                  'createdAt':previous.get('createdAt') or request.createdAt or now,
                  'updatedAt':now,
                  'result':request.result}
        return _save(document)


@router.get('/{topic_id}')
def read_topic(topic_id:str):
    with STORE_LOCK:
        document=_read(_path(topic_id))
        if not isinstance(document,dict):raise HTTPException(404,'没有找到这次探究')
        return document


@router.patch('/{topic_id}')
def rename_topic(topic_id:str,request:RenameInput):
    with STORE_LOCK:
        document=_read(_path(topic_id))
        if not isinstance(document,dict):raise HTTPException(404,'没有找到这次探究')
        document['problem']['title']=request.title.strip()
        document['updatedAt']=time.strftime('%Y-%m-%dT%H:%M:%S',time.gmtime())+'Z'
        return _save(document)


@router.delete('/{topic_id}')
def delete_topic(topic_id:str):
    with STORE_LOCK:
        for target in (_path(topic_id),_meta_path(topic_id)):
            try:target.unlink()
            except FileNotFoundError:pass
            except OSError:raise HTTPException(500,'本机探究记录删除失败。') from None
        return {'deleted':True}
