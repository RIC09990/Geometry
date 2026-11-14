import json
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Barrier, Event, Lock

import pytest
from fastapi.testclient import TestClient

from server import topics_store
from server.main import app


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(topics_store, 'STORE', tmp_path / 'topics')
    return tmp_path / 'topics'


def problem(topic_id='custom-test', title='等腰三角形'):
    return {'schemaVersion': 1, 'id': topic_id, 'title': title, 'version': 1,
            'points': [{'id': 'A', 'x': 0, 'y': 3}, {'id': 'B', 'x': -3, 'y': 0}, {'id': 'C', 'x': 3, 'y': 0}],
            'segments': [{'id': 'AB', 'points': ['A', 'B']}], 'circles': [], 'constructions': [],
            'conditions': [{'id': 'side', 'kind': 'equal_length', 'args': ['A', 'B', 'A', 'C']}],
            'goal': {'id': 'goal', 'kind': 'equal_angle', 'args': ['A', 'B', 'C', 'A', 'C', 'B']},
            'nondegenerate': {'distinct': True, 'triangles': [['A', 'B', 'C']]}}


def topic(topic_id='custom-test', title='等腰三角形', **extra):
    return {'id': topic_id, 'problem': problem(topic_id, title), 'recognizedText': '题目原文',
            'createdAt': '2026-01-01T00:00:00Z', 'updatedAt': '2026-01-01T00:00:00Z', **extra}


def test_saving_lists_and_reading_a_topic_round_trips(store):
    client = TestClient(app)
    saved = client.post('/api/topics', json=topic(result={'version': 1, 'proofs': []})).json()
    assert saved['title'] == '等腰三角形'
    listing = client.get('/api/topics').json()
    assert [item['id'] for item in listing] == ['custom-test']
    assert 'problem' not in listing[0]
    document = client.get('/api/topics/custom-test').json()
    assert document['problem']['title'] == '等腰三角形'
    assert document['result'] == {'version': 1, 'proofs': []}


def test_search_matches_titles_and_recognized_text(store):
    client = TestClient(app)
    client.post('/api/topics', json=topic('custom-a', '等腰三角形'))
    client.post('/api/topics', json=topic('custom-b', '圆内接四边形', recognizedText='四点共圆'))
    assert [item['id'] for item in client.get('/api/topics?q=等腰').json()] == ['custom-a']
    assert [item['id'] for item in client.get('/api/topics?q=共圆').json()] == ['custom-b']
    assert client.get('/api/topics?q=不存在').json() == []


def test_renaming_updates_the_problem_title_and_keeps_the_record(store):
    client = TestClient(app)
    client.post('/api/topics', json=topic())
    renamed = client.patch('/api/topics/custom-test', json={'title': '新的标题'}).json()
    assert renamed['title'] == '新的标题'
    assert client.get('/api/topics/custom-test').json()['problem']['title'] == '新的标题'


def test_saving_without_text_keeps_the_previous_recognized_text(store):
    client = TestClient(app)
    client.post('/api/topics', json=topic())
    client.post('/api/topics', json={**topic(), 'recognizedText': ''})
    assert client.get('/api/topics/custom-test').json()['recognizedText'] == '题目原文'


def test_deleting_removes_the_topic_and_its_metadata(store):
    client = TestClient(app)
    client.post('/api/topics', json=topic())
    assert client.delete('/api/topics/custom-test').json() == {'deleted': True}
    assert client.get('/api/topics').json() == []
    assert client.get('/api/topics/custom-test').status_code == 404


@pytest.mark.parametrize('topic_id', ['../../secret', 'variant-1'])
def test_invalid_ids_are_refused(store, topic_id):
    client = TestClient(app)
    assert client.get('/api/topics/' + topic_id).status_code in (404, 422)


def test_oversized_topics_are_refused_before_writing(store, monkeypatch):
    monkeypatch.setattr(topics_store, 'MAX_BYTES', 200)
    client = TestClient(app)
    assert client.post('/api/topics', json=topic()).status_code == 413
    assert client.get('/api/topics').json() == []


def test_concurrent_writes_use_independent_temporary_files(store, monkeypatch):
    barrier = Barrier(2)
    replace_lock = Lock()
    replace = topics_store.os.replace
    sources = []

    def concurrent_replace(source, target):
        sources.append(source)
        barrier.wait(timeout=5)
        with replace_lock:
            replace(source, target)

    monkeypatch.setattr(topics_store.os, 'replace', concurrent_replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        writes = [pool.submit(topics_store._write, store / 'custom-test.json', {'writer': i})
                  for i in range(2)]
        for write in writes:
            write.result(timeout=10)
    assert len(set(sources)) == 2
    assert json.loads((store / 'custom-test.json').read_text()) in [{'writer': 0}, {'writer': 1}]
    assert list(store.glob('*.tmp')) == []


def test_failed_replacement_preserves_the_document_and_cleans_up(store, monkeypatch):
    path = store / 'custom-test.json'
    topics_store._write(path, {'writer': 'original'})

    def fail_replace(source, target):
        raise PermissionError('replacement failed')

    monkeypatch.setattr(topics_store.os, 'replace', fail_replace)
    with pytest.raises(PermissionError):
        topics_store._write(path, {'writer': 'new'})
    assert json.loads(path.read_text()) == {'writer': 'original'}
    assert list(store.glob('*.tmp')) == []


def test_rename_waits_for_save_and_keeps_document_and_metadata_consistent(store, monkeypatch):
    client = TestClient(app)
    assert client.post('/api/topics', json=topic()).status_code == 200
    document_written, release_save, rename_started = Event(), Event(), Event()
    write = topics_store._write

    def paused_write(path, value):
        write(path, value)
        if path.name == 'custom-test.json' and value['problem']['title'] == '保存中的标题':
            document_written.set()
            assert release_save.wait(timeout=5)

    def rename():
        rename_started.set()
        return client.patch('/api/topics/custom-test', json={'title': '重命名后的标题'})

    monkeypatch.setattr(topics_store, '_write', paused_write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        save = pool.submit(client.post, '/api/topics', json=topic(title='保存中的标题', result={'version': 1}))
        try:
            assert document_written.wait(timeout=5)
            renamed = pool.submit(rename)
            assert rename_started.wait(timeout=5)
            with pytest.raises(TimeoutError):
                renamed.result(timeout=0.2)
        finally:
            release_save.set()
        assert save.result(timeout=5).status_code == 200
        assert renamed.result(timeout=5).status_code == 200
    document = client.get('/api/topics/custom-test').json()
    summary = client.get('/api/topics').json()[0]
    assert document['problem']['title'] == summary['title'] == '重命名后的标题'
    assert document['result'] == {'version': 1}
