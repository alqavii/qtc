"""
Activity stream endpoints.
"""

import asyncio
import threading
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.telemetry import get_recent_activity_entries, subscribe_activity

router = APIRouter(prefix="/activity", tags=["Activity"])


@router.get("/recent")
def get_activity_recent(limit: int = 100):
    """Get recent activity entries."""
    limit = max(1, min(limit, 500))
    return {"activity": get_recent_activity_entries(limit)}


@router.get("/stream")
async def stream_activity(request: Request):
    """Stream activity entries via Server-Sent Events."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str] = asyncio.Queue()
    stop_event = threading.Event()

    def pump() -> None:
        try:
            for entry in subscribe_activity(tail=200, stop_event=stop_event):
                payload = f"{entry.timestamp.isoformat()} | {entry.message}"
                loop.call_soon_threadsafe(queue.put_nowait, payload)
                if stop_event.is_set():
                    break
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if item is None:
                    break
                yield f"data: {item}\n\n"
        finally:
            stop_event.set()
            thread.join(timeout=1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
