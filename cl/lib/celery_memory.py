"""Per-task RSS logging for celery workers, for memory-leak investigation.

Emits an INFO log line at task_prerun (with the current resident set size)
and task_postrun (with pre/post RSS and the delta). The delta attributes
allocation growth to the task that caused it, which is valid only under
``--pool=prefork`` (one task at a time per child). Other pool types
(gevent, eventlet, threads) interleave tasks within a single process and
break per-task attribution; the module-level ``_last_pre_rss`` would also
be racy.

Reads /proc/self/statm directly so we don't add a psutil dependency.
Linux-only; on systems without /proc the signal handlers are not
registered and no log output is produced.
"""

import logging
import os
from typing import Any

from celery.signals import task_postrun, task_prerun

logger = logging.getLogger(__name__)

_PAGE_SIZE = os.sysconf("SC_PAGESIZE")
_STATM_AVAILABLE = os.path.exists("/proc/self/statm")

_last_pre_rss: int | None = None


def _rss_bytes() -> int:
    """Return the current process RSS in bytes, read from /proc/self/statm.

    statm fields, in pages: size, resident, shared, text, lib, data, dt.
    """
    with open("/proc/self/statm") as f:
        resident_pages = int(f.read().split()[1])
    return resident_pages * _PAGE_SIZE


if _STATM_AVAILABLE:

    @task_prerun.connect
    def log_rss_pre(
        sender: Any = None, task_id: str | None = None, **kwargs: Any
    ) -> None:
        global _last_pre_rss
        _last_pre_rss = _rss_bytes()
        logger.info(
            "celery.mem.pre task=%s task_id=%s pid=%d rss=%d",
            sender.name,
            task_id,
            os.getpid(),
            _last_pre_rss,
        )

    @task_postrun.connect
    def log_rss_post(
        sender: Any = None, task_id: str | None = None, **kwargs: Any
    ) -> None:
        global _last_pre_rss
        post_rss = _rss_bytes()
        # Fall back to post_rss when we have no pre (e.g. a task that
        # crashed the worker in pre, then a new child started mid-task).
        pre_rss = _last_pre_rss if _last_pre_rss is not None else post_rss
        logger.info(
            "celery.mem.post task=%s task_id=%s pid=%d "
            "rss_pre=%d rss_post=%d rss_delta=%d",
            sender.name,
            task_id,
            os.getpid(),
            pre_rss,
            post_rss,
            post_rss - pre_rss,
        )
        _last_pre_rss = None
