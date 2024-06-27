from math import ceil

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import transaction
from django.utils.text import slugify
from httpx import Response
from openai import (
    APIConnectionError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    OpenAI,
    RateLimitError,
    UnprocessableEntityError,
)
from sentry_sdk import capture_exception

from cl.audio.models import Audio, AudioTranscriptionMetadata
from cl.audio.utils import make_af_filename, transcription_was_hallucinated
from cl.celery_init import app
from cl.corpus_importer.tasks import increment_failure_count, upload_to_ia
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.command_utils import logger
from cl.lib.microservice_utils import microservice
from cl.lib.recap_utils import get_bucket_name


@app.task(bind=True, max_retries=15, interval_start=5, interval_step=5)
def upload_audio_to_ia(self, af_pk: int) -> None:
    af = Audio.objects.get(pk=af_pk)
    d = af.docket
    file_name = make_af_filename(
        d.court_id,
        d.docket_number,
        d.date_argued,
        af.local_path_original_file.name.rsplit(".", 1)[1],
    )
    bucket_name = get_bucket_name(d.court_id, slugify(d.docket_number))
    responses = upload_to_ia(
        self,
        identifier=bucket_name,
        files={file_name: af.local_path_original_file},
        title=best_case_name(d),
        collection=settings.IA_OA_COLLECTIONS,
        court_id=d.court_id,
        source_url=f"https://www.courtlistener.com{af.get_absolute_url()}",
        media_type="audio",
        description="This item represents an oral argument audio file as "
        "scraped from a U.S. Government website by Free Law "
        "Project.",
    )
    if responses is None:
        increment_failure_count(af)
        return

    if all(r.ok for r in responses):
        af.ia_upload_failure_count = None
        af.filepath_ia = (
            f"https://archive.org/download/{bucket_name}/{file_name}"
        )
        af.save()
    else:
        increment_failure_count(af)


# Error handling inspired by openai's package retry policy
# https://github.com/openai/openai-python/blob/54a5911f5215148a0bdeb10e2bcfb84f635a75b9/src/openai/_base_client.py#L679-L712
@app.task(
    bind=True,
    max_retries=3,
    retry_backoff=1 * 60,
    retry_backoff_max=10 * 60,
)
def transcribe_from_open_ai_api(self, audio_pk: int, dont_retry: bool = False):
    """Get transcription from OpenAI API whisper-1 model

    openai.OpenAI() client expects the environment
    variable OPENAI_API_KEY to be set

    If successful, updates Audio object and creates
    related AudioTranscriptionMetadata object

    :param audio_pk: audio object primary key
    """
    audio = Audio.objects.get(pk=audio_pk)
    logger.info(
        "Starting transcription for audio %s retry %s",
        audio_pk,
        self.request.retries,
    )

    # Double check for Audio.stt_status in case the request was
    # duplicated for some reason
    if audio.stt_status == Audio.STT_COMPLETE:
        logger.error(
            "Audio %s with status STT_COMPLETE was sent for transcription",
            audio_pk,
        )
        return

    audio_file = audio.local_path_mp3
    file_name = audio_file.name.split("/")[-1]
    size_mb = audio_file.size / 1_000_000
    # Check size and downsize file if necessary.
    if size_mb >= 25:
        audio_response: Response = async_to_sync(microservice)(
            service="downsize-audio",
            item=audio,
        )
        audio_response.raise_for_status()
        # Removes the ".mp3" extension from the filename
        name = file_name.split(".")[0]
        file = (f"{name}.ogg", audio_response.content, "ogg")
    else:
        file = (file_name, audio_file.read(), "mp3")

    # Prevent default openai client retrying
    with OpenAI(max_retries=0) as client:
        kwargs = {
            "file": file,
            "model": "whisper-1",
            "language": "en",
            "response_format": "verbose_json",
            "timestamp_granularities": ["word", "segment"],
            "prompt": audio.case_name,
        }

        # The most common hallucination we have seen is the case name
        # repeated in a loop. Manual testing showed that not sending
        # the case name helps to get a clean transcript
        if audio.stt_status == Audio.STT_HALLUCINATION:
            kwargs.pop("prompt", "")

        try:
            transcript = client.audio.transcriptions.create(**kwargs)
        except (
            RateLimitError,
            APIConnectionError,
            ConflictError,
            InternalServerError,
        ) as exc:
            # Handle retryable exception here so as to monitor them in
            # Sentry
            if self.request.retries < self.max_retries and not dont_retry:
                raise self.retry(exc=exc)
            return
        except (UnprocessableEntityError, BadRequestError):
            # BadRequestError is an HTTP 400 and has this message:
            # 'The audio file could not be decoded or its format is not supported'
            audio.stt_status = Audio.STT_FAILED
            audio.save()
            return
        except Exception as e:
            # Sends to Sentry errors that we don't expect or
            # don't want to retry. Includes some openai package errors:
            # (openai.AuthenticationError, openai.PermissionDeniedError,
            # openai.NotFoundError)
            capture_exception(e)
            return

        transcript_dict = transcript.to_dict()

        with transaction.atomic():
            audio.stt_transcript = transcript_dict["text"]
            audio.duration = ceil(transcript_dict["duration"])
            audio.stt_source = Audio.STT_OPENAI_WHISPER

            if transcription_was_hallucinated(audio):
                if audio.stt_status == Audio.STT_HALLUCINATION:
                    logger.error(
                        "Audio %s: hallucination was not corrected", audio.pk
                    )
                audio.stt_status = Audio.STT_HALLUCINATION
            else:
                audio.stt_status = Audio.STT_COMPLETE

            audio.save()
            metadata = {
                "segments": transcript_dict["segments"],
                "words": transcript_dict["words"],
            }
            AudioTranscriptionMetadata.objects.create(
                audio=audio, metadata=metadata
            )
