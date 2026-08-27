import argparse
from datetime import timedelta
from typing import cast

from django.utils import timezone

from cl.audio.dispatch import (
    dispatch_process_audio_file,
    dispatch_transcribe,
)
from cl.audio.models import Audio
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.types import OptionsType


def run_reenqueue_cycle(
    *,
    older_than_hours: int = 12,
    newer_than_days: int = 7,
    limit: int = 0,
    skip_processing: bool = False,
    skip_transcription: bool = False,
    dry_run: bool = False,
    verbose: bool = True,
) -> None:
    """Re-enqueue audios that are missing standardization or transcription.

    Single pass: queries for audios in the window, dispatches via the
    Redis-locked helpers, returns. Safe to run alongside the scraper —
    contended pks are no-ops.

    :param older_than_hours: Only consider audios created at least this
        many hours ago (avoids fighting with in-flight scraper enqueues).
    :param newer_than_days: Don't look further back than this many days.
    :param limit: Cap on rows per stage. 0 means no limit.
    :param skip_processing: Skip the standardization stage.
    :param skip_transcription: Skip the transcription stage.
    :param dry_run: Print what would be dispatched without acquiring locks.
    :param verbose: When False, per-pk dispatch logs go to DEBUG instead
        of INFO. Cycle summaries always log at INFO. Set to False from the
        daemon so steady-state hourly runs don't flood logs.
    """
    per_pk_log = logger.info if verbose else logger.debug

    now = timezone.now()
    older = now - timedelta(hours=older_than_hours)
    newer = now - timedelta(days=newer_than_days)

    logger.info(
        "Window: created between %s and %s  (older-than=%sh, newer-than=%sd)",
        newer,
        older,
        older_than_hours,
        newer_than_days,
    )

    # ---------- Stage 1: process_audio_file ----------
    process_pks: list[int] = []
    if not skip_processing:
        qs = (
            Audio.objects.filter(
                duration__isnull=True,
                date_created__lte=older,
                date_created__gte=newer,
            )
            .exclude(local_path_original_file="")
            .order_by("date_created")
        )
        if limit:
            qs = qs[:limit]
        process_pks = list(qs.values_list("id", flat=True))

        logger.info(
            "[stage 1] %s audios need process_audio_file",
            len(process_pks),
        )
        dispatched = skipped = 0
        for pk in process_pks:
            if dry_run:
                per_pk_log(
                    "[stage 1] [dry-run] would dispatch process_audio_file(audio=%s)",
                    pk,
                )
                continue
            if dispatch_process_audio_file(pk):
                dispatched += 1
                per_pk_log(
                    "[stage 1] dispatched process_audio_file(audio=%s)",
                    pk,
                )
            else:
                skipped += 1
                per_pk_log(
                    "[stage 1] skipped process_audio_file(audio=%s) — lock held",
                    pk,
                )
        logger.info(
            "[stage 1] dispatched=%s skipped=%s total=%s",
            dispatched,
            skipped,
            len(process_pks),
        )
    else:
        logger.info("[stage 1] skipped (--skip-processing)")

    # ---------- Stage 2: transcribe_from_open_ai_api ----------
    if skip_transcription:
        logger.info("[stage 2] skipped (--skip-transcription)")
        return

    # Exclude audios queued in stage 1: their process_audio_file task
    # almost certainly hasn't run yet (so duration is still NULL and
    # stage 2's query wouldn't match anyway), but guard against the
    # narrow race where stage 1's task races stage 2's query. The
    # next daemon cycle picks them up for transcription naturally.
    stage1_pks = set(process_pks)
    qs = (
        Audio.objects.filter(
            duration__isnull=False,
            stt_status=Audio.STT_NEEDED,
            date_created__lte=older,
            date_created__gte=newer,
        )
        .exclude(pk__in=stage1_pks)
        .order_by("date_created")
    )
    if limit:
        qs = qs[:limit]
    transcribe_pks = list(qs.values_list("id", flat=True))

    logger.info(
        "[stage 2] %s audios need transcription "
        "(after excluding %s from stage 1)",
        len(transcribe_pks),
        len(stage1_pks),
    )
    dispatched = skipped = 0
    for pk in transcribe_pks:
        if dry_run:
            per_pk_log(
                "[stage 2] [dry-run] would dispatch transcribe(audio=%s)",
                pk,
            )
            continue
        if dispatch_transcribe(pk):
            dispatched += 1
            per_pk_log("[stage 2] dispatched transcribe(audio=%s)", pk)
        else:
            skipped += 1
            per_pk_log(
                "[stage 2] skipped transcribe(audio=%s) — lock held",
                pk,
            )
    logger.info(
        "[stage 2] dispatched=%s skipped=%s total=%s",
        dispatched,
        skipped,
        len(transcribe_pks),
    )


class Command(VerboseCommand):
    help = (
        "Re-enqueue audios that are missing standardization (no duration) "
        "or missing transcription (stt_status=STT_NEEDED). The dispatch "
        "helpers acquire a per-audio Redis lock so this command is safe to "
        "run while the scraper is also enqueueing."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--older-than-hours",
            type=int,
            default=12,
            help=(
                "Only consider audios created at least this many hours ago, "
                "so we don't fight with in-flight scraper enqueues. "
                "Default: 12."
            ),
        )
        parser.add_argument(
            "--newer-than-days",
            type=int,
            default=7,
            help=(
                "Don't look further back than this many days. Audios older "
                "than this likely need investigation rather than blind "
                "re-enqueue. Default: 7."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Cap on rows per stage. 0 means no limit. Default: 0.",
        )
        parser.add_argument(
            "--skip-processing",
            action="store_true",
            help="Skip the standardization (process_audio_file) stage.",
        )
        parser.add_argument(
            "--skip-transcription",
            action="store_true",
            help="Skip the transcription stage.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Print what would be dispatched but don't acquire locks or "
                "enqueue."
            ),
        )

    def handle(self, *args, **options: OptionsType) -> None:
        super().handle(*args, **options)
        # OptionsType is too loose for the function signature, but argparse
        # has already coerced these via type=int / action="store_true".
        run_reenqueue_cycle(
            older_than_hours=cast(int, options["older_than_hours"]),
            newer_than_days=cast(int, options["newer_than_days"]),
            limit=cast(int, options["limit"]),
            skip_processing=cast(bool, options["skip_processing"]),
            skip_transcription=cast(bool, options["skip_transcription"]),
            dry_run=cast(bool, options["dry_run"]),
            verbose=True,
        )
        logger.info("Done.")
