import os

from celery.canvas import chain
from django.conf import settings
from juriscraper.pacer import PacerSession
from requests import Session

from cl.corpus_importer.tasks import add_tags, get_pacer_doc_by_rd
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import build_main_query_from_query_string
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import RECAPDocument
from cl.search.tasks import add_items_to_solr

PACER_USERNAME = os.environ["PACER_USERNAME"]
PACER_PASSWORD = os.environ["PACER_PASSWORD"]

TAG = "legal-robot-contracts"

# District and bankruptcy court docket entries with contract in their *short*
# description. Ensure to order by date and not by score.
QUERY_STRING = "q=short_description%3Acontract+AND+-short_description%3Aexecutory+AND+document_number%3A[1+TO+*]&type=r&order_by=dateFiled+asc&court=dcd+almd+alnd+alsd+akd+azd+ared+arwd+cacd+caed+cand+casd+cod+ctd+ded+flmd+flnd+flsd+gamd+gand+gasd+hid+idd+ilcd+ilnd+ilsd+innd+insd+iand+iasd+ksd+kyed+kywd+laed+lamd+lawd+med+mdd+mad+mied+miwd+mnd+msnd+mssd+moed+mowd+mtd+ned+nvd+nhd+njd+nmd+nyed+nynd+nysd+nywd+nced+ncmd+ncwd+ndd+ohnd+ohsd+oked+oknd+okwd+ord+paed+pamd+pawd+rid+scd+sdd+tned+tnmd+tnwd+txed+txnd+txsd+txwd+utd+vtd+vaed+vawd+waed+wawd+wvnd+wvsd+wied+wiwd+wyd+gud+nmid+prd+vid+almb+alnb+alsb+akb+arb+areb+arwb+cacb+caeb+canb+casb+cob+ctb+deb+dcb+flmb+flnb+flsb+gamb+ganb+gasb+hib+idb+ilcb+ilnb+ilsb+innb+insb+ianb+iasb+ksb+kyeb+kywb+laeb+lamb+lawb+meb+mdb+mab+mieb+miwb+mnb+msnb+mssb+moeb+mowb+mtb+nebraskab+nvb+nhb+njb+nmb+nyeb+nynb+nysb+nywb+nceb+ncmb+ncwb+ndb+ohnb+ohsb+okeb+oknb+okwb+orb+paeb+pamb+pawb+rib+scb+sdb+tneb+tnmb+tnwb+txeb+txnb+txsb+txwb+utb+vtb+vaeb+vawb+waeb+wawb+wvnb+wvsb+wieb+wiwb+wyb+gub+nmib+prb+vib"


def get_documents(options):
    """Download documents from PACER if we don't already have them."""
    q = options["queue"]

    throttle = CeleryThrottle(queue_name=q)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()

    page_size = 20000
    main_query = build_main_query_from_query_string(
        QUERY_STRING,
        {"rows": page_size, "fl": ["id", "docket_id"]},
        {"group": False, "facet": False, "highlight": False},
    )
    with Session() as session:
        si = ExtraSolrInterface(
            settings.SOLR_RECAP_URL, http_connection=session, mode="r"
        )
        results = si.query().add_extra(**main_query).execute()
    logger.info("Got %s search results.", results.result.numFound)

    for i, result in enumerate(results):
        if i < options["offset"]:
            continue
        if i >= options["limit"] > 0:
            break
        throttle.maybe_wait()

        logger.info(
            "Doing item %s w/rd: %s, d: %s",
            i,
            result["id"],
            result["docket_id"],
        )

        try:
            rd = RECAPDocument.objects.get(pk=result["id"])
        except RECAPDocument.DoesNotExist:
            logger.warning(
                "Unable to find RECAP Document with id %s", result["id"]
            )
            continue

        if rd.is_available:
            logger.info("Already have pk %s; just tagging it.", rd.pk)
            add_tags(rd, TAG)
            continue

        if not rd.pacer_doc_id:
            logger.info("Unable to find pacer_doc_id for: %s", rd.pk)
            continue

        chain(
            get_pacer_doc_by_rd.s(rd.pk, session.cookies, tag=TAG).set(
                queue=q
            ),
            extract_recap_pdf.si(rd.pk).set(queue=q),
            add_items_to_solr.si([rd.pk], "search.RECAPDocument").set(queue=q),
        ).apply_async()


class Command(VerboseCommand):
    help = "Get lots of contracts from PACER."

    def add_arguments(self, parser):
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="The number of items to skip before beginning. Default is to "
            "skip none.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="After doing this number, stop. This number is not additive "
            "with the offset parameter. Default is to do all of them.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        logger.info(f"Using PACER username: {PACER_USERNAME}")
        get_documents(options)
