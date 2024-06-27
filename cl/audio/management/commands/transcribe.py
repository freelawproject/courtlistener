import argparse
import time

from cl.audio.models import Audio
from cl.audio.tasks import transcribe_from_open_ai_api
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.types import OptionsType
from cl.lib.utils import deepgetattr


def audio_can_be_processed_by_open_ai_api(audio: Audio) -> bool:
    """Check the audio file exists in the bucket.

    :param audio: audio object
    :return: True if audio can be processed by OpenAI API
    """
    # Checks if the the local_path_mp3 is not None and the file exists
    # in the bucket.
    if deepgetattr(audio, "local_path_mp3.name", None):
        return True

    logger.warning(
        "Audio id %s has no local_path_mp3, needs reprocessing",
        audio.pk,
    )
    if audio.stt_status != Audio.STT_NO_FILE:
        audio.stt_status = Audio.STT_NO_FILE
        audio.save()

    return False


def handle_open_ai_transcriptions(options) -> None:
    """Get Audio objects from DB according to `options`,
    validate and call a celery task for processing them

    :param options: argparse options

    :return None
    """
    requests_per_minute = options["rpm"]

    status_code = options.get("status_to_process")
    for code, descr in Audio.STT_STATUSES:
        if code == status_code:
            logger.info("Querying Audio.stt_status = %s. %s", code, descr)

    queryset = Audio.objects.filter(stt_status=status_code)
    if options["max_audio_duration"]:
        queryset = queryset.filter(duration__lte=options["max_audio_duration"])
    logger.info("%s audio files to transcribe", queryset.count())

    if options["limit"]:
        queryset = queryset[: options["limit"]]
        logger.info("Processing only %s audio files", options["limit"])

    valid_count = 0
    for audio in queryset:
        if not audio_can_be_processed_by_open_ai_api(audio):
            continue

        valid_count += 1
        transcribe_from_open_ai_api.apply_async(
            args=(audio.pk, options["dont_retry_task"]),
            queue=options["queue"],
        )

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
    status_choices = [
        code for code, _ in Audio.STT_STATUSES if code != Audio.STT_COMPLETE
    ]
    status_help = "; ".join(
        [f"{code} - {descr}" for code, descr in Audio.STT_STATUSES]
    )

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
            "--status-to-process",
            choices=self.status_choices,
            default=Audio.STT_NEEDED,
            type=int,
            help=f"Audio.stt_status value to process. Default {Audio.STT_NEEDED}. {self.status_help}",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="""Max number of audio files to get from the database
            for processing. '--limit 0' means there is no limit. Default: 0""",
        )
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--dont-retry-task",
            default=False,
            action="store_true",
            help="""Do not retry celery tasks. Useful to monitor or
            debug API requests""",
        )
        parser.add_argument(
            "--max-audio-duration",
            type=int,
            default=0,
            help="""Specify the maximum duration (in seconds) of the audio
            files to process""",
        )

    def handle(self, *args: list[str], **options: OptionsType) -> None:
        super().handle(*args, **options)

        if options["model"] == "open-ai-api":
            handle_open_ai_transcriptions(options)
