from django.conf import settings
from django.utils.text import slugify

from cl.audio.models import Audio
from cl.audio.utils import make_af_filename
from cl.celery_init import app
from cl.corpus_importer.tasks import increment_failure_count, upload_to_ia
from cl.custom_filters.templatetags.text_filters import best_case_name
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
