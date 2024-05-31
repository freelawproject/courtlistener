from asgiref.sync import async_to_sync
from django.core.management import BaseCommand
from django.core.paginator import Paginator
from django.db import transaction

from cl.lib.command_utils import logger
from cl.lib.microservice_utils import microservice
from cl.search.models import (
    SOURCES,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
    RECAPDocument,
)


def import_opinions_from_recap(court=None, total_count=0):
    """Import recap documents into opinion db

    :param court: Court ID if any
    :param total_count: The number of new opinions to add
    :return: None
    """
    count = 0
    if not court:
        courts = Court.objects.filter(jurisdiction=Court.FEDERAL_DISTRICT)
    else:
        courts = Court.objects.filter(id=court)
    for court in courts:
        logger.info(f"Importing RECAP documents for {court}")
        cluster = (
            OpinionCluster.objects.filter(docket__court=court)
            .order_by("-date_filed")
            .first()
        )
        if not cluster:
            print("No clusters for this court")
            logger.info(f"Court {court} has no opinion clusters")

            continue
        documents = RECAPDocument.objects.filter(
            docket_entry__docket__court=court,
            docket_entry__docket__date_filed__lte=cluster.date_filed,
            is_available=True,
            is_free_on_pacer=True,
        ).order_by("docket_entry__docket__date_filed")

        chunk_size = 100
        paginator = Paginator(documents, chunk_size)
        for page_number in paginator.page_range:
            chunk = paginator.page(page_number).object_list
            for recap_document in chunk:
                docket = Docket.objects.get(
                    docket_entries__recap_documents__id=recap_document.id
                )
                if "-cv-" not in docket.docket_number:
                    logger.info(f"Skipping non civil opinion")
                    continue

                ops = Opinion.objects.filter(sha1=recap_document.sha1)
                if ops.count() > 0:
                    print("Skipping previously imported opinion")
                    continue

                response = async_to_sync(microservice)(
                    service="recap-extract",
                    filepath=recap_document.filepath_local,
                    params={"strip_margin": True},
                )
                with transaction.atomic():
                    cluster = OpinionCluster.objects.create(
                        case_name_full=docket.case_name_full,
                        case_name=docket.case_name,
                        case_name_short=docket.case_name_short,
                        docket=docket,
                        date_filed=recap_document.docket_entry.date_filed,
                        source=SOURCES.RECAP,
                    )
                    Opinion.objects.create(
                        cluster=cluster,
                        type=Opinion.TRIAL_COURT,
                        plain_text=response.json()["content"],
                        page_count=recap_document.page_count,
                        sha1=recap_document.sha1,
                        download_url=recap_document.filepath_local,
                    )

                    logger.info(
                        f"Sucessfully imported https://www.courtlistener.com/opinion/{cluster.id}/decision/"
                    )
                    count += 1
                    if total_count > 0 and count >= total_count:
                        logger.info(
                            f"RECAP import completed for {total_count} documents"
                        )
                        break


class Command(BaseCommand):
    help = "Import recap documents into opinions"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--court",
            help="Specific court ID to import - skip if want to ingest everything",
            type=str,
            required=False,
        )
        parser.add_argument(
            "--total",
            type=int,
            help="Number of files to import - set to 0 to import endlessly",
            default=10,
            required=True,
        )

    def handle(self, *args, **options):
        court = options.get("court")
        total_count = options.get("total")
        import_opinions_from_recap(court, total_count)
