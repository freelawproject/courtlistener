"""Lock-protected enqueue helpers for audio standardization and transcription.

The lock prevents two simultaneous tasks from running for the same audio_pk
(via scraper, in-task hand-off, or manual re-enqueue). The TTL is the soft
recovery window for cases where the task crashes silently — once it expires,
the audio becomes eligible for re-dispatch.
"""

from cl.lib.redis_utils import get_redis_interface

# Generous: longer than any plausible legitimate run, short enough that a
# silent worker crash doesn't strand an audio for hours.
TRANSCRIBE_LOCK_TTL = 30 * 60  # 30 minutes
PROCESS_LOCK_TTL = 15 * 60  # 15 minutes


def _lock_key(prefix: str, audio_pk: int) -> str:
    return f"dispatch:{prefix}:{audio_pk}"


def _try_lock(prefix: str, audio_pk: int, ttl: int) -> bool:
    r = get_redis_interface("CACHE")
    return bool(r.set(_lock_key(prefix, audio_pk), "1", ex=ttl, nx=True))


def _release_lock(prefix: str, audio_pk: int) -> None:
    get_redis_interface("CACHE").delete(_lock_key(prefix, audio_pk))


def dispatch_transcribe(
    audio_pk: int,
    *,
    queue: str | None = None,
    dont_retry: bool = False,
) -> bool:
    """Enqueue transcribe_from_open_ai_api for ``audio_pk`` if no other
    transcription is already in flight for that pk.

    :param audio_pk: Audio primary key.
    :param queue: Optional Celery queue name. Defaults to the task's
        configured queue. Used by ops backfills that target a separate
        queue from the daemon's regular dispatches.
    :param dont_retry: Pass-through to the task; disables its in-task
        retry on APIConnectionError. Used for diagnostic runs.
    :return: True if dispatched, False if skipped because the lock is held.
    """
    # Local import to avoid a circular import with cl.audio.tasks.
    from cl.audio.tasks import transcribe_from_open_ai_api

    if not _try_lock("transcribe", audio_pk, TRANSCRIBE_LOCK_TTL):
        return False
    try:
        if queue is None and not dont_retry:
            # .delay() uses task's decorator settings. apply_async overrides them
            transcribe_from_open_ai_api.delay(audio_pk)
        else:
            transcribe_from_open_ai_api.apply_async(
                args=(audio_pk, dont_retry),
                queue=queue,
            )
    except Exception:
        # Broker blip — don't strand the pk for the full TTL. Releasing
        # makes the next daemon cycle eligible to retry.
        _release_lock("transcribe", audio_pk)
        raise
    return True


def dispatch_process_audio_file(audio_pk: int) -> bool:
    """Enqueue process_audio_file for ``audio_pk`` if no other standardization
    is already in flight for that pk.

    :param audio_pk: Audio primary key.
    :return: True if dispatched, False if skipped because the lock is held.
    """
    from cl.scrapers.tasks import process_audio_file

    if not _try_lock("process_audio_file", audio_pk, PROCESS_LOCK_TTL):
        return False
    try:
        process_audio_file.delay(audio_pk)
    except Exception:
        _release_lock("process_audio_file", audio_pk)
        raise
    return True
