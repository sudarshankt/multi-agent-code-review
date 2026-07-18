"""ARQ worker for background job processing.

NOTE: redis_settings MUST be a class attribute, not a @staticmethod (bug #1).
"""

from __future__ import annotations

from src.infrastructure.redis.queue import get_redis_settings


class WorkerSettings:
    # Class attribute (not @staticmethod) — spec bug #1
    redis_settings = get_redis_settings()
    max_jobs = 5
    job_timeout = 600  # 10 minutes


async def startup(ctx):
    print("Worker starting...")


async def shutdown(ctx):
    print("Worker stopping...")


# The worker will look for a function like `async def my_job(...)`
# in this module and execute it when jobs are enqueued.
# For now, this is a stub; jobs would be enqueued via src/infrastructure/redis/queue.py
