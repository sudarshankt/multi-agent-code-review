"""ARQ Redis task queue."""

from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)


def get_redis_settings() -> RedisSettings:
    """Get ARQ Redis connection settings."""
    settings = get_settings()
    redis = settings.redis
    return RedisSettings(
        host=redis.host,
        port=redis.port,
        database=redis.db,
    )


async def enqueue_job(job_name: str, *args: Any, **kwargs: Any) -> str | None:
    """Enqueue a job to Redis/ARQ (MVP: not yet fully wired)."""
    try:
        from arq.connections import create_pool

        settings = get_redis_settings()
        redis = await create_pool(settings)
        job = await redis.enqueue(job_name, *args, **kwargs)
        logger.info("job_enqueued", job_id=job.job_id, job_name=job_name)
        return job.job_id
    except Exception as exc:
        logger.error("job_enqueue_failed", job_name=job_name, error=str(exc))
        return None
