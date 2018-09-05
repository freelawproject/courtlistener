import hashlib
import json
import subprocess
import traceback
from tempfile import NamedTemporaryFile

import httplib2
from celery.canvas import chain
from django.conf import settings
from django.utils.text import slugify
from google.cloud import storage
from google.cloud.exceptions import Forbidden, NotFound
from google.cloud.storage import Blob
from googleapiclient import discovery
from oauth2client.client import GoogleCredentials

from cl.audio.models import Audio
from cl.audio.utils import get_audio_binary, make_af_filename
from cl.celery import app
from cl.corpus_importer.tasks import upload_to_ia, increment_failure_count
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.recap_utils import get_bucket_name

TRANSCRIPTS_BUCKET_NAME = 'freelawproject-transcripts'


def make_transcription_chain(path, phrases, af_id):
    """Make a celery chain that combines the whole transcription workflow.

    The way this works is that the return values from each task are appended as
    positional arguments to the task that follows.

    :type path: str
    :param path: The path to the input file.
    :type phrases: list
    :param phrases: A list of phrases or words that are expected to be in the
    audio. Typically, this will be proper nouns like the case name, for example.
    :type af_id: int
    :param af_id: The ID of the Audio item that will be updated in the end.
    """
    return chain(
        upload_item_as_raw_file.s(path),
        do_speech_to_text.s(phrases),
        poll_for_result_and_save.s(af_id),
        delete_blob_from_google.s(),
    )


def get_storage_client():
    """Build a storage client for the user, and return it."""
    return storage.Client.from_service_account_json(
        settings.GOOGLE_AUTH['PATH'],
        project=settings.GOOGLE_AUTH['PROJECT'],
    )


def get_speech_service():
    """Make a speech service that we can use to make requests.

    This is lifted from the API examples provided here:
    https://github.com/GoogleCloudPlatform/python-docs-samples/blob/master/speech/api-client/transcribe_async.py#L35
    """
    credentials = GoogleCredentials.from_stream(
        settings.GOOGLE_AUTH['PATH'],
    ).create_scoped(
        ['https://www.googleapis.com/auth/cloud-platform'],
    )
    http = httplib2.Http()
    credentials.authorize(http)
    return discovery.build('speech', 'v1beta1', http=http)


def encode_as_linear16(path, tmp):
    # From: https://cloud.google.com/speech/support#troubleshooting:
    # "The LINEAR16 encoding must be 16-bits, signed-integer,
    # little-endian."
    # In avconv, this translates to "s16le". See also:
    # http://stackoverflow.com/a/4854627/64911 and
    # https://trac.ffmpeg.org/wiki/audio%20types
    assert isinstance(path, basestring), "path argument is not a str."
    av_path = get_audio_binary()
    av_command = [
        av_path,
        '-y',           # Assume yes (clobber existing files)
        '-i', path,     # Input file
        '-f', 's16le',  # Force output format
        '-ac', '1',     # Mono
        '-ar', '16k',   # Sample rate of 16000Mhz
        tmp.name,       # Output file
    ]
    try:
        _ = subprocess.check_output(av_command, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print('%s failed command: %s\n'
              'error code: %s\n'
              'output: %s\n' % (av_path, av_command, e.returncode, e.output))
        print(traceback.format_exc())
        raise e


@app.task
def upload_item_as_raw_file(path, client=None):
    """Set things up, convert the file, and upload it."""
    if client is None:
        client = get_storage_client()

    # Check that the bucket exists, make it if not.
    try:
        b = client.get_bucket(TRANSCRIPTS_BUCKET_NAME)
    except Forbidden as e:
        print("Received Forbidden (403) error while getting bucket. This could "
              "mean that you do not have billing set up for this "
              "account/project, or that somebody else has taken this bucket "
              "from the global namespace.")
        raise e
    except NotFound:
        b = client.bucket(TRANSCRIPTS_BUCKET_NAME)
        b.lifecycle_rules = [{
            'action': {'type': 'Delete'},
            'condition': {'age': 7},
        }]
        b.create()
        b.make_public(future=True)

    # Re-encode the file as a temp file and upload it. When we leave the context
    # manager, the temp file gets automatically deleted.
    with NamedTemporaryFile(prefix='transcode_', suffix='.raw') as tmp:
        encode_as_linear16(path, tmp)

        # Name it after a SHA2 hash of the item, to avoid collisions.
        file_name = 'transcripts-%s' % hashlib.sha256(tmp.read()).hexdigest()
        blob = Blob(file_name, b)
        blob.upload_from_file(tmp, rewind=True)

    return {'blob_name': blob.name, 'bucket_name': blob.bucket.name}


@app.task
def do_speech_to_text(returned_info, phrases, service=None):
    """Convert the file to text

    This creates an operation on Google's servers to convert the item to text.
    In general, this process takes about as long as the file to complete (so a
    10 minute MP3 will take about 10 minutes to complete).

    When this task is completed, it hands off the remote task ID to another
    Celery task that polls for the final result.
    """
    if service is None:
        service = get_speech_service()
    default_phrases = [
        'remand', 'appellant', 'appellee', 'et al.', 'deposition', 'officer',
        'factual', 'reasonable', 'claimant', 'complainant', 'defendant',
        'devisee', 'executor', 'executrix', 'petitioner', 'plaintiff',
        'respondant',
    ]
    default_phrases.extend(phrases)
    assert len(default_phrases) <= 500, "phrase API limit exceeded."
    response = service.speech().asyncrecognize(
        body={
            'config': {
                'encoding': 'LINEAR16',
                'sampleRate': 16000,
                'maxAlternatives': 10,
                'speechContext': {'phrases': default_phrases},
            },
            'audio': {
                'uri': 'gs://%s/%s' % (returned_info['bucket_name'],
                                       returned_info['blob_name']),
            }
        }).execute()

    # Use a dict to send all values to the next task as a single var
    returned_info.update({'operation_name': response['name']})
    return returned_info


@app.task(bind=True, max_retries=6)
def poll_for_result_and_save(self, returned_info, af_id, service=None):
    """Poll Google for the completed STT and save it to the DB.

    Using an exponential backoff, ask google for the completed operation. If
    it's complete, save the results.
    """
    # 5, 10, 20, 40, 80, 160, 320 minutes (longest item is currently 240 min.)
    countdown = 5 * 60 * (2 ** self.request.retries)
    if service is None:
        service = get_speech_service()
    af = Audio.objects.get(pk=af_id)

    polling_response = (service.operations()
                        .get(name=returned_info['operation_name'])
                        .execute())
    if 'done' in polling_response and polling_response['done']:
        af.stt_google_response = json.dumps(polling_response, indent=2)
        af.stt_status = af.STT_COMPLETE
        af.save()
        return returned_info
    else:
        last_try = (self.request.retries == self.max_retries)
        if last_try:
            af.stt_status = af.STT_FAILED
            af.save(index=False)  # Skip indexing if we have no new content.
            return returned_info
        else:
            try:
                raise Exception("STT not yet complete.")
            except Exception as exc:
                raise self.retry(exc=exc, countdown=countdown)


@app.task
def delete_blob_from_google(returned_info, client=None):
    """Delete the blob from Google Storage.

    If the bucket is set up properly, the lifecycle rules will automatically
    delete items, however, the sooner we do so the better.
    """
    if client is None:
        client = get_storage_client()
    b = client.get_bucket(returned_info['bucket_name'])
    blob = b.get_blob(returned_info['blob_name'])
    blob.delete()


@app.task(bind=True, max_retries=15, interval_start=5, interval_step=5)
def upload_audio_to_ia(self, af_pk):
    af = Audio.objects.get(pk=af_pk)
    d = af.docket
    file_name = make_af_filename(
        d.court_id,
        d.docket_number,
        d.date_argued,
        af.local_path_original_file.path.rsplit('.', 1)[1]
    )
    bucket_name = get_bucket_name(d.court_id, slugify(d.docket_number))
    responses = upload_to_ia(
        self,
        identifier=bucket_name,
        files={file_name: af.local_path_original_file.path},
        title=best_case_name(d),
        collection=settings.IA_OA_COLLECTIONS,
        court_id=d.court_id,
        source_url='https://www.courtlistener.com%s' % af.get_absolute_url(),
        media_type='audio',
        description='This item represents an oral argument audio file as '
                    'scraped from a U.S. Government website by Free Law '
                    'Project.',
    )
    if responses is None:
        increment_failure_count(af)
        return

    if all(r.ok for r in responses):
        af.ia_upload_failure_count = None
        af.filepath_ia = "https://archive.org/download/%s/%s" % (
            bucket_name, file_name)
        af.save()
    else:
        increment_failure_count(af)

