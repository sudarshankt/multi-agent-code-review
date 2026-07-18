"""Server-Sent Events endpoint for real-time review progress (spec bug #5)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.core.logging import get_logger
from src.models.review import TERMINAL_STATUSES

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
    """Generator yielding SSE-formatted messages from the channel."""
    channel = get_or_create_channel(review_id)
    ping_task = asyncio.create_task(_ping_loop())

    try:
        while True:
            # Wait for an event or a ping.
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(channel.get()),
                    ping_task,
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in done:
                if task is ping_task:
                    # Ping timeout; send a comment.
                    yield ": ping\n\n"
                    ping_task = asyncio.create_task(_ping_loop())
                else:
                    # Event from queue.
                    event_data = task.result()
                    yield f"data: {json.dumps(event_data)}\n\n"
                    # Check if terminal event; if so, close.
                    status = event_data.get("status")
                    if status in {s.value for s in TERMINAL_STATUSES}:
                        logger.debug("sse_stream_closing", status=status)
                        ping_task.cancel()
                        return
    finally:
        # Cleanup.
        if not ping_task.done():
            ping_task.cancel()


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
