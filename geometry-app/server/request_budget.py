"""One wall-clock budget for an AI request, including queueing and all passes.

This ASGI boundary has no imports from the AI routers. Cancellation propagates
to their awaited HTTPX requests; a disconnected browser cannot start a later
search, completion, or review. A PDF worker already running in a thread may
finish locally, but its result is discarded.
"""
import asyncio

from starlette.responses import JSONResponse


AI_REQUEST_SECONDS = 300


class AIRequestBudgetMiddleware:
    def __init__(self, app, seconds=AI_REQUEST_SECONDS):
        self.app = app
        self.seconds = seconds

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') != 'POST' or not scope.get('path', '').startswith('/api/ai/'):
            return await self.app(scope, receive, send)

        # A single reader owns ASGI receive. The queue relays body chunks to the
        # app while the reader continues listening for a browser disconnect.
        inbox = asyncio.Queue(maxsize=1)
        disconnected = asyncio.Event()
        response_started = False

        async def read_request():
            try:
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        disconnected.set()
                        return
                    await inbox.put(message)
            except Exception:
                disconnected.set()

        async def app_receive():
            if disconnected.is_set() and inbox.empty():
                return {'type': 'http.disconnect'}
            return await inbox.get()

        async def app_send(message):
            nonlocal response_started
            if message['type'] == 'http.response.start':
                response_started = True
            await send(message)

        reader = asyncio.create_task(read_request())
        work = asyncio.create_task(self.app(scope, app_receive, app_send))
        disconnect = asyncio.create_task(disconnected.wait())
        try:
            done, _ = await asyncio.wait({work, disconnect}, timeout=self.seconds, return_when=asyncio.FIRST_COMPLETED)
            if work in done:
                return await work
            work.cancel()
            await asyncio.gather(work, return_exceptions=True)
            if not disconnected.is_set() and not response_started:
                response = JSONResponse(
                    {'detail': 'AI 请求超过等待时间，已停止本次处理，请稍后重试。'},
                    status_code=504,
                    headers={'Cache-Control': 'no-store'},
                )
                await response(scope, receive, send)
        finally:
            for task in (work, reader, disconnect):
                if not task.done():
                    task.cancel()
            await asyncio.gather(work, reader, disconnect, return_exceptions=True)
