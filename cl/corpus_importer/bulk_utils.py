from celery import chain
from django.conf import settings
from django.core.paginator import Paginator
from juriscraper.pacer import PacerSession
from requests import Session

from cl.corpus_importer.tasks import get_pacer_doc_by_rd
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import logger
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import build_main_query_from_query_string
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import RECAPDocument
from cl.search.tasks import add_items_to_solr


def docket_pks_for_query(query_string):
    """Yield docket PKs for a query by iterating over the full result set

    :param query_string: The query to run as a URL-encoded string (typically
    starts with 'q='). E.g. 'q=foo&type=r&order_by=dateFiled+asc&court=dcd'
    :return: The next docket PK in the results
    """
    main_query = build_main_query_from_query_string(
        query_string,
        {"fl": ["docket_id"]},
        {"group": True, "facet": False, "highlight": False},
    )
    main_query["group.limit"] = 0
    main_query["sort"] = "dateFiled asc"
    with Session() as session:
        si = ExtraSolrInterface(
            settings.SOLR_RECAP_URL, http_connection=session, mode="r"
        )
        search = si.query().add_extra(**main_query)
    page_size = 100
    paginator = Paginator(search, page_size)
    for page_number in paginator.page_range:
        page = paginator.page(page_number)
        for item in page:
            yield item["groupValue"]


def make_bankr_docket_number(docket_number: str, office_code: str) -> str:
    """Combine the office number and core docket number to make a nice one

    E.g., docket number of 1421168 + office number of 2 becomes '2:14-bk-21168'

    :param docket_number: The docket number from the FJC IDB, as a string of
    numbers.
    :param office_code: The office code
    """
    return f"{office_code}:{docket_number[:2]}-bk-{docket_number[-5:]}"


def get_petitions(
    options,
    pacer_username: str,
    pacer_password: str,
    tag: str,
    tag_petitions: str,
) -> None:
    """Get dockets by tag, find item 1, download and tag it."""
    rds = (
        RECAPDocument.objects.filter(
            tags__name=tag,
            document_number="1",
            document_type=RECAPDocument.PACER_DOCUMENT,
            is_available=False,
        )
        .exclude(pacer_doc_id="")
        .order_by("pk")
        .values_list("pk", flat=True)
        .iterator()
    )
    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    pacer_session = PacerSession(
        username=pacer_username, password=pacer_password
    )
    pacer_session.login()
    for i, rd_pk in enumerate(rds):
        if i < options["offset"]:
            i += 1
            continue
        if i >= options["limit"] > 0:
            break

        if i % 1000 == 0:
            pacer_session = PacerSession(
                username=pacer_username, password=pacer_password
            )
            pacer_session.login()
            logger.info(f"Sent {i} tasks to celery so far.")
        logger.info("Doing row %s", i)
        throttle.maybe_wait()

        chain(
            get_pacer_doc_by_rd.s(
                rd_pk, pacer_session.cookies, tag=tag_petitions
            ).set(queue=q),
            extract_recap_pdf.si(rd_pk).set(queue=q),
            add_items_to_solr.si([rd_pk], "search.RECAPDocument").set(queue=q),
        ).apply_async()
