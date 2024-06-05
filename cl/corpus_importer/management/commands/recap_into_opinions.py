import eyecite
from asgiref.sync import async_to_sync
from django.core.management import BaseCommand
from django.db import transaction
from eyecite.tokenizers import HyperscanTokenizer
from httpx import (
    HTTPStatusError,
    NetworkError,
    RemoteProtocolError,
    Response,
    TimeoutException,
)

from cl.citations.utils import filter_out_non_case_law_citations
from cl.lib.command_utils import logger
from cl.lib.decorators import retry
from cl.lib.microservice_utils import microservice
from cl.search.models import (
    SOURCES,
    Court,
    Opinion,
    OpinionCluster,
    RECAPDocument,
)

HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")


@retry(
    ExceptionToCheck=(
        NetworkError,
        TimeoutException,
        RemoteProtocolError,
        HTTPStatusError,
    ),
    tries=3,
    delay=5,
    backoff=2,
    logger=logger,
)
def extract_recap_document(rd: RECAPDocument) -> Response:
    """Call recap-extract from doctor with retries

    :param rd: the recap document to extract
    :return: Response object
    """
    response = async_to_sync(microservice)(
        service="recap-extract",
        item=rd,
        params={"strip_margin": True},
    )
    response.raise_for_status()
    return response


def import_opinions_from_recap(court=None, total_count=0):
    """Import recap documents into opinion db

    :param court: Court ID if any
    :param total_count: The number of new opinions to add
    :return: None
    """
    count = 0
    if not court:
        courts = Court.objects.filter(
            jurisdiction=Court.FEDERAL_DISTRICT
        ).exclude(
            id__in=["orld", "dcd"]
        )  # orld is historical and we gather dcd opinions from the court
    else:
        courts = Court.objects.filter(pk=court)
    for court in courts:
        logger.info(f"Importing RECAP documents for {court}")
        cluster = (
            OpinionCluster.objects.filter(docket__court=court)
            .exclude(source=SOURCES.RECAP)
            .order_by("-date_filed")
            .first()
        )

        documents = RECAPDocument.objects.filter(
            docket_entry__docket__court=court,
            docket_entry__date_filed__gt=cluster.date_filed,
            is_available=True,
            is_free_on_pacer=True,
        ).order_by("id")

        for recap_document in documents.iterator():
            logger.info(f"Importing recap document {recap_document.id}")
            docket = recap_document.docket_entry.docket
            if "cv" not in docket.docket_number.lower():
                logger.info("Skipping non-civil opinion")
                continue

            ops = Opinion.objects.filter(sha1=recap_document.sha1)
            if ops.count() > 0:
                logger.info(
                    f"Skipping previously imported opinion: {ops[0].id}"
                )
                continue
            response = extract_recap_document(rd=recap_document)

            try:
                citations = eyecite.get_citations(
                    response.json()["content"], tokenizer=HYPERSCAN_TOKENIZER
                )
            except AttributeError:
                # Tokenizer fails with some unicode characters
                # Ex. 42\u2009U.S.C.\u2009§\u200912131 \u2009 is a small space
                # fallback to regular citation match
                logger.warning(
                    "Hyperscan failed for {}, trying w/o tokenizer".format(
                        recap_document
                    )
                )
                citations = eyecite.get_citations(response.json()["content"])

            case_law_citations = filter_out_non_case_law_citations(citations)
            if len(case_law_citations) == 0:
                logger.info(f"No citation found for rd: {recap_document.id}")
                continue

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
                    local_path=recap_document.filepath_local,
                )

                logger.info(
                    "Successfully imported https://www.courtlistener.com/opinion/{}/decision/".format(
                        cluster.id
                    )
                )
                count += 1
                if total_count > 0 and count >= total_count:
                    logger.info(
                        f"RECAP import completed for {total_count} documents"
                    )
                    return


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
            required=False,
        )

    def handle(self, *args, **options):
        court = options.get("court")
        total_count = options.get("total")
        import_opinions_from_recap(court, total_count)
