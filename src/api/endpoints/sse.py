"""Server-Sent Events endpoint for real-time review progress (spec bug #5)."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from src.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Global channel registry: review_id -> asyncio.Queue
_channels: dict[str, asyncio.Queue] = {}


def get_or_create_channel(review_id: str) -> asyncio.Queue:
    """Get or create a channel for a review. Create on first publish, not on connect (bug #5)."""
    if review_id not in _channels:
        _channels[review_id] = asyncio.Queue()
    return _channels[review_id]


async def publish_event(
    review_id: str, event_type: str, data: dict | None = None
) -> None:
    """Publish an SSE event to all subscribers. Creates the channel on first publish (bug #5)."""
    channel = get_or_create_channel(review_id)
    event_data = {"type": event_type, **(data or {})}
    await channel.put(event_data)
    logger.debug("sse_published", review_id=review_id, sse_event=event_type)


async def _event_stream(review_id: str) -> AsyncGenerator[str, None]:
    """Generator yielding SSE-formatted messages from the channel.

    The stream is intentionally NEVER closed based on the review reaching a
    terminal status: after the analysis pipeline finishes, the user still
    needs live updates for fix approval, commit, and the optional test gate —
    all of which happen after ReviewStatus.COMPLETED is set. There is no
    single "the user is truly done" signal, so we keep the stream open for
    the life of the HTTP connection and rely on the client (browser tab
    closing/navigating away) to disconnect, which cancels this coroutine via
    Starlette's request-cancellation and triggers the `finally` cleanup below.

    IMPORTANT: `get_task` is created ONCE and only replaced after it is
    actually consumed (i.e. it appears in `done`). Creating a fresh
    `channel.get()` task every loop iteration — even when only the ping
    fires — leaves the previous get() task dangling as a second concurrent
    consumer on the same queue. Two consumers racing on `queue.get()` will
    each independently pull events, so whichever call is *not* awaited by
    this generator silently swallows events that never reach the client.
    """
    channel = get_or_create_channel(review_id)
    ping_task = asyncio.create_task(_ping_loop())
    get_task = asyncio.create_task(channel.get())

    try:
        while True:
            done, _pending = await asyncio.wait(
                [get_task, ping_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if ping_task in done:
                yield ": ping\n\n"
                ping_task = asyncio.create_task(_ping_loop())

            if get_task in done:
                event_data = get_task.result()
                yield f"data: {json.dumps(event_data)}\n\n"
                get_task = asyncio.create_task(channel.get())
    finally:
        # Cleanup (runs when the client disconnects and this coroutine is cancelled).
        if not ping_task.done():
            ping_task.cancel()
        if not get_task.done():
            get_task.cancel()


async def _ping_loop() -> None:
    """Sleep for 30 seconds (ping interval)."""
    await asyncio.sleep(30)


@router.get("/reviews/{review_id}")
async def sse_stream(review_id: str):
    """Stream review progress as Server-Sent Events."""
    logger.debug("sse_stream_started", review_id=review_id)
    return StreamingResponse(
        _event_stream(review_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
