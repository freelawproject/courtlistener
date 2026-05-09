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


def _try_lock(prefix: str, audio_pk: int, ttl: int) -> bool:
    r = get_redis_interface("CACHE")
    return bool(r.set(f"dispatch:{prefix}:{audio_pk}", "1", ex=ttl, nx=True))


def dispatch_transcribe(audio_pk: int) -> bool:
    """Enqueue transcribe_from_open_ai_api for ``audio_pk`` if no other
    transcription is already in flight for that pk.

    :param audio_pk: Audio primary key.
    :return: True if dispatched, False if skipped because the lock is held.
    """
    # Local import to avoid a circular import with cl.audio.tasks.
    from cl.audio.tasks import transcribe_from_open_ai_api

    if not _try_lock("transcribe", audio_pk, TRANSCRIBE_LOCK_TTL):
        return False
    transcribe_from_open_ai_api.delay(audio_pk)
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
    process_audio_file.delay(audio_pk)
    return True
