import argparse
import time

from django.db.models import Q

from cl.audio.models import Audio
from cl.audio.tasks import transcribe_from_open_ai_api
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.types import OptionsType


def audio_can_be_processed_by_open_ai_api(audio: Audio) -> bool:
    """Check that the audio file exists and that it's size is
    25MB or less

    OpenAI API' whisper-1 model has a limit of 25MB

    :param audio: audio object

    :return: True if audio can be processed by OpenAI API
    """
    try:
        # audio.duration should map to the file size with little variability
        # However, it can be unreliable, so we trust it only for shorter files
        if audio.local_path_mp3 and audio.duration and audio.duration < 3000:
            return True

        # Request the file size from the storage
        # currently an AWS bucket
        size_mb = audio.local_path_mp3.size / 1_000_000
        if size_mb < 25:
            return True

        logger.warning(
            "Audio id %s actual size is greater than API limit %s",
            audio.pk,
            size_mb,
        )
    except (FileNotFoundError, ValueError):
        # FileNotFoundError: when the name does not exist in the bucket
        # ValueError: when local_path_mp3 is None or a null FileField
        logger.warning(
            "Audio id %s has no local_path_mp3, needs reprocessing",
            audio.pk,
        )

    return False


def handle_open_ai_transcriptions(options) -> None:
    """Get Audio objects from DB according to `options`,
    validate and call a celery task for processing them

    :param options: argparse options

    :return None
    """
    requests_per_minute = options["rpm"]

    if options.get("retry_failures"):
        query = Q(stt_status=Audio.STT_FAILED)
    else:
        query = Q(stt_status=Audio.STT_NEEDED)

    queryset = Audio.objects.filter(query)
    logger.info("%s audio files to transcribe", queryset.count())

    if options["limit"]:
        queryset = queryset[: options["limit"]]
        logger.info("Processing only %s audio files", options["limit"])

    valid_count = 0
    for audio in queryset:
        if not audio_can_be_processed_by_open_ai_api(audio):
            continue

        valid_count += 1
        transcribe_from_open_ai_api.delay(audio.pk)

        # For parallel processing: seed RPM requests per minute
        # if requests_per_minute == 0, do not sleep
        if requests_per_minute and valid_count % requests_per_minute == 0:
            logger.info(
                "Sent %s transcription requests, sleeping for 1 minute",
                requests_per_minute,
            )
            time.sleep(61)


class Command(VerboseCommand):
    help = "Transcribe audio files using a Speech to Text model"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--model",
            choices=[
                "open-ai-api",
            ],
            default="open-ai-api",
            help="Model to use for extraction",
        )
        parser.add_argument(
            "--rpm",
            type=int,
            default=50,
            help="Requests Per Minute, a rate limit in the model API",
        )
        parser.add_argument(
            "--retry-failures",
            action="store_true",
            default=False,
            help="Retry transcription of failed audio files",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="""Max number of audio files to get from the database
            for processing. '--limit 0' means there is no limit. Default: 0""",
        )

    def handle(self, *args: list[str], **options: OptionsType) -> None:
        super().handle(*args, **options)

        if options["model"] == "open-ai-api":
            handle_open_ai_transcriptions(options)
