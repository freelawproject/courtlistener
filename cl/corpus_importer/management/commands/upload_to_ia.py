import argparse
import os

from django.conf import settings
from django.db.models import Q

from cl.audio.models import Audio
from cl.audio.tasks import upload_audio_to_ia
from cl.corpus_importer.tasks import upload_pdf_to_ia
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import RECAPDocument

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)


def upload_non_free_pdfs_to_internet_archive(options):
    upload_pdfs_to_internet_archive(options, do_non_free=True)


def upload_pdfs_to_internet_archive(options, do_non_free=False):
    """Upload items to the Internet Archive."""
    q = options['queue']
    rds = RECAPDocument.objects.filter(
        Q(ia_upload_failure_count__lt=3) | Q(ia_upload_failure_count=None),
        is_available=True,
        filepath_ia='',
    ).exclude(
        filepath_local='',
    ).values_list(
        'pk',
        flat=True,
    ).order_by()
    if do_non_free:
        rds = rds.filter(Q(is_free_on_pacer=False) | Q(is_free_on_pacer=None))
    else:
        rds = rds.filter(is_free_on_pacer=True)

    count = rds.count()
    logger.info("Sending %s items to Internet Archive.", count)
    throttle = CeleryThrottle(queue_name=q)
    for i, rd in enumerate(rds):
        throttle.maybe_wait()
        if i > 0 and i % 1000 == 0:
            logger.info("Sent %s/%s tasks to celery so far.", i, count)
        upload_pdf_to_ia.si(rd).set(queue=q).apply_async()


def upload_oral_arguments_to_internet_archive(options):
    """Upload oral arguments to the Internet Archive"""
    q = options['queue']
    af_pks = Audio.objects.filter(Q(ia_upload_failure_count__lt=3) |
                               Q(ia_upload_failure_count=None),
                               filepath_ia='')\
        .exclude(local_path_mp3='')\
        .values_list('pk', flat=True)\
        .order_by()
    count = len(af_pks)
    logger.info("Sending %s oral argument files to Internet Archive", count)
    throttle = CeleryThrottle(queue_name=q)
    for i, af_pk in enumerate(af_pks):
        throttle.maybe_wait()
        if i > 0 and i % 1000 == 0:
            logger.info("Sent %s/%s tasks to celery so far.", i, count)
        upload_audio_to_ia.si(af_pk).set(queue=q).apply_async()


def do_everything(options):
    logger.info("Uploading free opinions to Internet Archive.")
    upload_pdfs_to_internet_archive(options)
    logger.info("Uploading non-free PDFs to Internet Archive.")
    upload_non_free_pdfs_to_internet_archive(options)
    logger.info("Uploading oral arguments to Internet Archive.")
    upload_oral_arguments_to_internet_archive(options)


class Command(VerboseCommand):
    help = "Get all the free content from PACER. There are three modes."

    def valid_actions(self, s):
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s" % (
                    ', '.join(self.VALID_ACTIONS.keys())
                )
            )

        return self.VALID_ACTIONS[s]

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: %s" % (
                ', '.join(self.VALID_ACTIONS.keys())
            )
        )
        parser.add_argument(
            '--queue',
            default='batch1',
            help="The celery queue where the tasks should be processed.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options['action'](options)

    VALID_ACTIONS = {
        'do-everything': do_everything,
        'upload-pdfs-to-ia': upload_pdfs_to_internet_archive,
        'upload-non-free-pdfs-to-ia': upload_non_free_pdfs_to_internet_archive,
        'upload-oral-arguments-to-ia': upload_oral_arguments_to_internet_archive,
    }
