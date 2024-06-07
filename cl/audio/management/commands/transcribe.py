import argparse
import time
from typing import List

from django.db.models import Q

from cl.audio.models import Audio
from cl.audio.tasks import transcribe_from_open_ai_api
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.types import OptionsType


class Command(VerboseCommand):
    help = "Transcribe audio files using a Speech to Text model"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--model",
            choices=[
                "openai-api",
            ],
            default="openai-api",
            help="Model to use for extraction",
        )
        parser.add_argument(
            "--rpm",
            type=int,
            default=50,
            help="Requests Per Minute, a rate limit in the model API",
        )
        parser.add_argument(
            "--retry",
            action="store_true",
            default=False,
            help="Retry transcription of failed audio files",
        )

    def handle(self, *args: List[str], **options: OptionsType) -> None:
        super().handle(*args, **options)
        requests_per_minute = options["rpm"]

        if options.get("retry"):
            query = Q(stt_status=Audio.STT_FAILED)
        else:
            query = Q(stt_status=Audio.STT_NEEDED)

        # OpenAI API' whisper-1 model has a limit of 25MB for the
        # audio file, which matches an Audio.duration of up to 4000
        # seconds. However, Audio.duration value is not reliable
        # from 2020 - present due to a bug in its calculation
        if options.get("model") == "openai-api":
            duration_query_1 = Q(
                duration__lt=3500, date_created__year__gt=2019
            )
            duration_query_2 = Q(
                duration__lt=4000, date_created__year__lte=2019
            )
            query = query & (duration_query_1 | duration_query_2)

        logger.info(
            "%s audio files to transcribe", Audio.objects.filter(query).count()
        )

        valid_count = 0
        for audio in Audio.objects.filter(query):
            # Validate that audio can actually be processed
            try:
                # Following the previous comment about Audio.duration
                # only check durations that may cause a problem
                if audio.duration and audio.duration > 3500:
                    size_mb = audio.local_path_mp3.size / 1_000_000
                    if size_mb > 25:
                        logger.warning(
                            "Audio id %s actual size is greater than API limit %s",
                            audio.pk,
                            size_mb,
                        )
                        continue
            except FileNotFoundError:
                # Triggered when local_path_mp3 does not exist
                logger.warning(
                    "Audio id %s has no local_path_mp3, needs reprocessing",
                    audio.pk,
                )
                continue

            valid_count += 1
            transcribe_from_open_ai_api(audio.pk)

            # For parallel processing: seed RPM requests per minute
            # if requests_per_minute == 0, do not sleep
            if requests_per_minute and valid_count % requests_per_minute == 0:
                logger.info(
                    "Sent %s transcription requests, sleeping for 1 minute",
                    requests_per_minute,
                )
                time.sleep(61)
