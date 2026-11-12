import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.request_budget import AIRequestBudgetMiddleware


def scope(path='/api/ai/chat'):
    return {'type': 'http', 'method': 'POST', 'path': path}


async def exercise(app, *, seconds=.06, disconnect_after=None, path='/api/ai/chat', chunks=None):
    incoming = asyncio.Queue()
    for body, more in chunks or [(b'{}', False)]:
        incoming.put_nowait({'type': 'http.request', 'body': body, 'more_body': more})
    sent = []

    async def send(message):
        sent.append(message)

    async def disconnect():
        await asyncio.sleep(disconnect_after)
        await incoming.put({'type': 'http.disconnect'})

    disconnected = asyncio.create_task(disconnect()) if disconnect_after is not None else None
    try:
        await AIRequestBudgetMiddleware(app, seconds)(scope(path), incoming.get, send)
    finally:
        if disconnected:
            disconnected.cancel()
            await asyncio.gather(disconnected, return_exceptions=True)
    return sent


def test_total_deadline_covers_search_completion_and_prevents_later_review():
    async def run():
        events = []

        async def app(scope, receive, send):
            await receive()
            events.append('search')
            await asyncio.sleep(.035)
            try:
                events.append('completion')
                await asyncio.sleep(5)
                events.append('review')
            finally:
                events.append('completion cancelled')

        sent = await exercise(app)
        assert events == ['search', 'completion', 'completion cancelled']
        assert sent[0]['status'] == 504
        assert '已停止' in json.loads(sent[1]['body'])['detail']

    asyncio.run(run())


def test_queue_wait_counts_toward_budget_without_starting_billable_work():
    async def run():
        capacity = asyncio.Semaphore(0)
        events = []

        async def app(scope, receive, send):
            await receive()
            async with capacity:
                events.append('completion')

        sent = await exercise(app, seconds=.01)
        capacity.release()
        await asyncio.sleep(0)
        assert events == []
        assert sent[0]['status'] == 504
        assert not capacity.locked()

    asyncio.run(run())


@pytest.mark.parametrize('path', ['/api/ai/chat', '/api/ai/review-proof', '/api/ai/import-topic', '/api/ai/proof-ideas'])
def test_disconnect_cancels_current_transport_and_never_starts_next_pass(path):
    async def run():
        events = []

        class Transport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                events.append('request')
                try:
                    await asyncio.sleep(5)
                    return httpx.Response(200, json={})
                finally:
                    events.append('request cancelled')

            async def aclose(self):
                events.append('transport closed')

        async def app(scope, receive, send):
            await receive()
            async with httpx.AsyncClient(transport=Transport()) as client:
                await client.post('https://unit-test.invalid/completion')
            events.append('next pass')

        sent = await exercise(app, path=path, seconds=1, disconnect_after=.02)
        assert events == ['request', 'request cancelled', 'transport closed']
        assert sent == []

    asyncio.run(run())


def test_normal_body_chunks_and_response_are_preserved_without_task_leaks():
    async def run():
        before = asyncio.all_tasks()

        async def app(scope, receive, send):
            body = b''
            while True:
                message = await receive()
                body += message['body']
                if not message['more_body']:
                    break
            assert body == b'{"x":1}'
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'ok'})

        for _ in range(10):
            sent = await exercise(app, chunks=[(b'{"x":', True), (b'1}', False)])
            assert sent[-1]['body'] == b'ok'
        assert asyncio.all_tasks() == before

    asyncio.run(run())


def test_non_ai_routes_are_not_changed_by_ai_deadline():
    async def app(scope, receive, send):
        await asyncio.sleep(.02)
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok'})

    sent = asyncio.run(exercise(app, path='/api/validate', seconds=.001))
    assert sent[0]['status'] == 200


def test_app_exception_is_not_converted_to_timeout_or_hidden():
    async def app(scope, receive, send):
        raise ValueError('test failure')

    with pytest.raises(ValueError, match='test failure'):
        asyncio.run(exercise(app))


def test_deadline_works_outside_fastapi_http_middleware():
    app = FastAPI()
    cancelled = []

    @app.middleware('http')
    async def service_boundary(request, call_next):
        return await call_next(request)

    @app.post('/api/ai/chat')
    async def chat():
        try:
            await asyncio.sleep(5)
        finally:
            cancelled.append(True)

    app.add_middleware(AIRequestBudgetMiddleware, seconds=.02)
    response = TestClient(app).post('/api/ai/chat', json={})
    assert response.status_code == 504
    assert cancelled == [True]


def test_outer_cancellation_also_cleans_up_all_owned_tasks():
    async def run():
        before = asyncio.all_tasks()
        started = asyncio.Event()
        cancelled = []

        async def app(scope, receive, send):
            started.set()
            try:
                await asyncio.sleep(5)
            finally:
                cancelled.append(True)

        task = asyncio.create_task(exercise(app, seconds=5))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled == [True]
        assert asyncio.all_tasks() == before

    asyncio.run(run())
