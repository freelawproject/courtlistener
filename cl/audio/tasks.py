from math import ceil

import openai
from django.conf import settings
from django.db import transaction
from django.utils.text import slugify
from sentry_sdk import capture_exception

from cl.audio.models import Audio, AudioTranscriptionMetadata
from cl.audio.utils import make_af_filename
from cl.celery_init import app
from cl.corpus_importer.tasks import increment_failure_count, upload_to_ia
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.command_utils import logger
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


@app.task
def transcribe_from_open_ai_api(audio_pk: int):
    """Get transcription from OpenAI API whisper-1 model

    openai.OpenAI() client expects the environment
    variable OPENAI_API_KEY to be set

    If successful, updates Audio object and creates
    related AudioTranscriptionMetadata object

    :param audio_pk: audio object primary key
    """
    audio = Audio.objects.get(pk=audio_pk)
    audio_file = audio.local_path_mp3
    file = (audio_file.name.split("/")[-1], audio_file.read(), "mp3")

    logger.info("Starting transcription for audio %s", audio_pk)

    # openai client will retry by default "Connection errors,
    # 408 Request Timeout, 409 Conflict, 429 Rate Limit, and
    # >=500 Internal errors". See more:
    # https://github.com/openai/openai-python?tab=readme-ov-file#retries
    with openai.OpenAI(max_retries=5) as client:
        try:
            transcript = client.audio.transcriptions.create(
                file=file,
                model="whisper-1",
                language="en",
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"],
                prompt=audio.case_name,
            )
        except openai.UnprocessableEntityError:
            audio.stt_status = Audio.STT_FAILED
            audio.save()
            logger.warning("UnprocessableEntityError for audio %s", audio_pk)
            return
        except (openai.APIStatusError, openai.APIConnectionError) as e:
            # Sending to Sentry errors that are not auto-retried
            # or that have failed many times
            capture_exception(e)
            return

        transcript_dict = transcript.to_dict()

        with transaction.atomic():
            audio.stt_transcript = transcript_dict["text"]
            audio.stt_status = Audio.STT_COMPLETE
            audio.stt_source = Audio.STT_OPENAI_WHISPER
            audio.duration = ceil(transcript_dict["duration"])
            audio.save()

            metadata = {
                "segments": transcript_dict["segments"],
                "words": transcript_dict["words"],
            }
            AudioTranscriptionMetadata.objects.create(
                audio=audio, metadata=metadata
            )
