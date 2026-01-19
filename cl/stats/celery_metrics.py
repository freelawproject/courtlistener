"""Celery task metrics via Redis for Prometheus.

Uses Celery signals to track task executions and durations in Redis.
A custom Prometheus collector reads these at scrape time.
"""

import time

from celery.signals import task_failure, task_postrun, task_prerun

from cl.lib.redis_utils import get_redis_interface

METRICS_PREFIX = "prometheus:celery:"

# Track task start times per task_id (worker-local, cleared on completion)
_task_start_times: dict[str, float] = {}


def _incr_task_counter(task_name: str, status: str) -> None:
    """Increment task execution counter in Redis."""
    r = get_redis_interface("STATS")
    r.incr(f"{METRICS_PREFIX}task_total:{task_name}:{status}")


def _record_task_duration(task_name: str, duration_seconds: float) -> None:
    """Record task duration (sum + count for computing averages)."""
    r = get_redis_interface("STATS")
    pipe = r.pipeline()
    pipe.incrbyfloat(
        f"{METRICS_PREFIX}task_duration_sum:{task_name}", duration_seconds
    )
    pipe.incr(f"{METRICS_PREFIX}task_duration_count:{task_name}")
    pipe.execute()


@task_prerun.connect
def _track_task_start(task_id: str, task, **kwargs) -> None:
    """Record task start time."""
    _task_start_times[task_id] = time.perf_counter()


@task_postrun.connect
def _track_task_complete(task_id: str, task, **kwargs) -> None:
    """Record successful task completion with duration."""
    start = _task_start_times.pop(task_id, None)
    if start:
        duration = time.perf_counter() - start
        _record_task_duration(task.name, duration)
    _incr_task_counter(task.name, "success")


@task_failure.connect
def _track_task_failure(task_id: str, task, **kwargs) -> None:
    """Record task failure."""
    _task_start_times.pop(task_id, None)  # Clean up start time
    _incr_task_counter(task.name, "failure")
