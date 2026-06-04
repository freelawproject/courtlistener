import sys
from itertools import batched

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Q
from lxml.etree import XMLSyntaxError

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.scrapers.tasks import extract_pdf_document
from cl.search.models import Docket, RECAPDocument


def extract_unextracted_rds(
    queue: str, chunk_size: int, db_connection: str = "default"
) -> None:
    """Performs content extraction for all recap documents that need to be
    extracted.

    :param queue: The celery queue to use
    :param chunk_size: The number of items to extract in a single celery task.
    :param db_connection: The database connection to use.
    :return: None
    """

    rd_needs_extraction = (
        RECAPDocument.objects.using(db_connection)
        .filter(
            Q(ocr_status__isnull=True)
            | Q(ocr_status=RECAPDocument.OCR_NEEDED),
            is_available=True,
        )
        .exclude(filepath_local="")
        .values_list("pk", flat=True)
        .order_by()
    )
    count = rd_needs_extraction.count()
    # Set low throttle. Higher values risk crashing Redis.
    throttle = CeleryThrottle(queue_name=queue)
    processed_count = 0
    for chunk in batched(rd_needs_extraction.iterator(), chunk_size):
        throttle.maybe_wait()
        processed_count += len(chunk)
        extract_pdf_document.si(list(chunk)).set(queue=queue).apply_async()
        sys.stdout.write(
            f"\rProcessed {processed_count}/{count} ({processed_count * 1.0 / count:.0%})"
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
            "--extract-unextracted-rds",
            action="store_true",
            default=False,
            help="Extract all recap documents that need to be extracted.",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default="10",
            help="The number of PDFs to extract in a single celery task.",
        )
        parser.add_argument(
            "--use-replica",
            action="store_true",
            default=False,
            help="Use this flag to run the queries in the replica db",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        db_connection = (
            "replica"
            if options.get("use_replica") and "replica" in settings.DATABASES
            else "default"
        )
        if options["extract_unextracted_rds"]:
            queue = options["queue"]
            chunk_size = options["chunk_size"]
            sys.stdout.write(
                "Extracting all recap documents that need extraction. \n"
            )
            extract_unextracted_rds(queue, chunk_size, db_connection)
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
            except (OSError, XMLSyntaxError):
                # Happens when the local IA XML file is empty. Not sure why
                # these happen.
                xml_error_ids.append(d.pk)
                continue

        print(f"Encountered XMLSyntaxErrors/IOErrors for: {xml_error_ids}")
