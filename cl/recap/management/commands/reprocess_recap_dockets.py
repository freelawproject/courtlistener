import sys

from celery.canvas import chain
from django.db import IntegrityError
from django.db.models import Q
from lxml.etree import XMLSyntaxError

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import Docket, RECAPDocument
from cl.search.tasks import add_items_to_solr


def extract_unextracted_rds_and_add_to_solr(queue: str) -> None:
    """Performs content extraction for all recap documents that need to be
    extracted and then add to solr.

    :param queue: The celery queue to use
    :return: None
    """

    rd_needs_extraction = [
        x.pk
        for x in RECAPDocument.objects.filter(
            (Q(ocr_status=None) | Q(ocr_status=RECAPDocument.OCR_NEEDED))
            & Q(is_available=True)
            & ~Q(filepath_local="")
        ).only("pk")
    ]
    count = len(rd_needs_extraction)

    # The count to send in a single Celery task
    chunk_size = 100
    # Set low throttle. Higher values risk crashing Redis.
    throttle = CeleryThrottle(queue_name=queue)
    processed_count = 0
    chunk = []
    for item in rd_needs_extraction:
        processed_count += 1
        last_item = count == processed_count
        chunk.append(item)
        if processed_count % chunk_size == 0 or last_item:
            throttle.maybe_wait()
            chain(
                extract_recap_pdf.si(chunk).set(queue=queue),
                add_items_to_solr.s("search.RECAPDocument").set(queue=queue),
            ).apply_async()
            chunk = []
            sys.stdout.write(
                "\rProcessed {}/{} ({:.0%})".format(
                    processed_count, count, processed_count * 1.0 / count
                )
            )
            sys.stdout.flush()
    sys.stdout.write("\n")


class Command(VerboseCommand):
    help = "Reprocess all dockets in the RECAP Archive."

    def add_arguments(self, parser):
        parser.add_argument(
            "--start-pk",
            type=int,
            default=0,
            help="Skip any primary keys lower than this value. (Useful for "
            "restarts.)",
        )

        parser.add_argument(
            "--queue",
            type=str,
            default="celery",
            help="The celery queue where the tasks should be processed.",
        )

        parser.add_argument(
            "--extract-and-add-solr-unextracted-rds",
            action="store_true",
            default=False,
            help="Extract all recap documents that need to be extracted and "
            "then add to solr.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        if options["extract_and_add_solr_unextracted_rds"]:
            queue = options["queue"]
            sys.stdout.write(
                "Extracting all recap documents that need extraction and then "
                "add to solr. \n"
            )
            extract_unextracted_rds_and_add_to_solr(queue)
            return

        ds = (
            Docket.objects.filter(
                # Only do ones that have HTML files *or* that have an IA XML file.
                # The latter is defined by ones that *don't* have blank
                # filepath_local fields.
                Q(html_documents__isnull=False) | ~Q(filepath_local=""),
                source__in=Docket.RECAP_SOURCES(),
            )
            .distinct()
            .only("pk", "case_name")
        )
        if options["start_pk"]:
            ds = ds.filter(pk__gte=options["start_pk"])
        count = ds.count()
        xml_error_ids = []
        for i, d in enumerate(ds.iterator()):
            sys.stdout.write(
                f"\rDoing docket: {i} of {count}, with pk: {d.pk}"
            )
            sys.stdout.flush()

            try:
                d.reprocess_recap_content(do_original_xml=True)
            except IntegrityError:
                # Happens when there's wonkiness in the source data. Move on.
                continue
            except (XMLSyntaxError, IOError):
                # Happens when the local IA XML file is empty. Not sure why
                # these happen.
                xml_error_ids.append(d.pk)
                continue

        print(f"Encountered XMLSyntaxErrors/IOErrors for: {xml_error_ids}")
