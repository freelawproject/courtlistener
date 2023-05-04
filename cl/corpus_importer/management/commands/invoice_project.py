import os

from celery.canvas import chain
from django.conf import settings
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from juriscraper.pacer import PacerSession
from requests import Session

from cl.corpus_importer.tasks import (
    add_tags,
    get_attachment_page_by_rd,
    get_pacer_doc_by_rd,
    make_attachment_pq_object,
)
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import build_main_query_from_query_string
from cl.recap.tasks import process_recap_attachment
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import RECAPDocument
from cl.search.tasks import add_items_to_solr

PACER_USERNAME = os.environ["PACER_USERNAME"]
PACER_PASSWORD = os.environ["PACER_PASSWORD"]

TAG_PHASE_1 = "hDResWFzUBzlAOKP"
TAG_PHASE_2 = "sSgVwjmTsAZAFLPR"

# District and bankruptcy court non-attachment
# documents with invoice in their description.
Q_DOCS_ONLY = 'q=document_type%3A"PACER+Document"+description%3Ainvoice&type=r&order_by=dateFiled+asc&court=dcd+almd+alnd+alsd+akd+azd+ared+arwd+cacd+caed+cand+casd+cod+ctd+ded+flmd+flnd+flsd+gamd+gand+gasd+hid+idd+ilcd+ilnd+ilsd+innd+insd+iand+iasd+ksd+kyed+kywd+laed+lamd+lawd+med+mdd+mad+mied+miwd+mnd+msnd+mssd+moed+mowd+mtd+ned+nvd+nhd+njd+nmd+nyed+nynd+nysd+nywd+nced+ncmd+ncwd+ndd+ohnd+ohsd+oked+oknd+okwd+ord+paed+pamd+pawd+rid+scd+sdd+tned+tnmd+tnwd+txed+txnd+txsd+txwd+utd+vtd+vaed+vawd+waed+wawd+wvnd+wvsd+wied+wiwd+wyd+gud+nmid+prd+vid+californiad+caca+circtdel+illinoised+illinoisd+indianad+orld+circtnc+ohiod+pennsylvaniad+southcarolinaed+southcarolinawd+tennessed+circttenn+canalzoned+bap1+bap2+bap6+bap8+bap9+bap10+bapme+bapma+almb+alnb+alsb+akb+arb+areb+arwb+cacb+caeb+canb+casb+cob+ctb+deb+dcb+flmb+flnb+flsb+gamb+ganb+gasb+hib+idb+ilcb+ilnb+ilsb+innb+insb+ianb+iasb+ksb+kyeb+kywb+laeb+lamb+lawb+meb+mdb+mab+mieb+miwb+mnb+msnb+mssb+moeb+mowb+mtb+nebraskab+nvb+nhb+njb+nmb+nyeb+nynb+nysb+nywb+nceb+ncmb+ncwb+ndb+ohnb+ohsb+okeb+oknb+okwb+orb+paeb+pamb+pawb+rib+scb+sdb+tneb+tnmb+tnwb+tennesseeb+txeb+txnb+txsb+txwb+utb+vtb+vaeb+vawb+waeb+wawb+wvnb+wvsb+wieb+wiwb+wyb+gub+nmib+prb+vib'

# District and bankruptcy court docket entries with invoice in their *short*
# description that do not already have PDFs (is_available:false). Ensure to
# order by date and not by score. Ordering by score will mess up the
# pagination, since the document scores will be changing under you as you
# paginate.
Q_INVOICES = "q=short_description%3Ainvoice+is_available%3Afalse&type=r&order_by=dateFiled+asc&court=dcd+almd+alnd+alsd+akd+azd+ared+arwd+cacd+caed+cand+casd+cod+ctd+ded+flmd+flnd+flsd+gamd+gand+gasd+hid+idd+ilcd+ilnd+ilsd+innd+insd+iand+iasd+ksd+kyed+kywd+laed+lamd+lawd+med+mdd+mad+mied+miwd+mnd+msnd+mssd+moed+mowd+mtd+ned+nvd+nhd+njd+nmd+nyed+nynd+nysd+nywd+nced+ncmd+ncwd+ndd+ohnd+ohsd+oked+oknd+okwd+ord+paed+pamd+pawd+rid+scd+sdd+tned+tnmd+tnwd+txed+txnd+txsd+txwd+utd+vtd+vaed+vawd+waed+wawd+wvnd+wvsd+wied+wiwd+wyd+gud+nmid+prd+vid+californiad+caca+circtdel+illinoised+illinoisd+indianad+orld+circtnc+ohiod+pennsylvaniad+southcarolinaed+southcarolinawd+tennessed+circttenn+canalzoned+bap1+bap2+bap6+bap8+bap9+bap10+bapme+bapma+almb+alnb+alsb+akb+arb+areb+arwb+cacb+caeb+canb+casb+cob+ctb+deb+dcb+flmb+flnb+flsb+gamb+ganb+gasb+hib+idb+ilcb+ilnb+ilsb+innb+insb+ianb+iasb+ksb+kyeb+kywb+laeb+lamb+lawb+meb+mdb+mab+mieb+miwb+mnb+msnb+mssb+moeb+mowb+mtb+nebraskab+nvb+nhb+njb+nmb+nyeb+nynb+nysb+nywb+nceb+ncmb+ncwb+ndb+ohnb+ohsb+okeb+oknb+okwb+orb+paeb+pamb+pawb+rib+scb+sdb+tneb+tnmb+tnwb+tennesseeb+txeb+txnb+txsb+txwb+utb+vtb+vaeb+vawb+waeb+wawb+wvnb+wvsb+wieb+wiwb+wyb+gub+nmib+prb+vib"


def get_attachment_pages(options):
    """Find docket entries that look like invoices and get their attachment
    pages.
    """
    page_size = 100
    main_query = build_main_query_from_query_string(
        Q_DOCS_ONLY,
        {"rows": page_size, "fl": ["id", "docket_id"]},
        {"group": False, "facet": False, "highlight": False},
    )
    with Session() as session:
        si = ExtraSolrInterface(
            settings.SOLR_RECAP_URL, http_connection=session, mode="r"
        )
        results = si.query().add_extra(**main_query)

    q = options["queue"]
    recap_user = User.objects.get(username="recap")
    throttle = CeleryThrottle(queue_name=q)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()
    paginator = Paginator(results, page_size)
    i = 0
    for page_number in range(1, paginator.num_pages + 1):
        paged_results = paginator.page(page_number)
        for result in paged_results.object_list:
            if i < options["offset"]:
                i += 1
                continue
            if i >= options["limit"] > 0:
                break

            logger.info(
                "Doing row %s: rd: %s, docket: %s",
                i,
                result["id"],
                result["docket_id"],
            )
            throttle.maybe_wait()
            chain(
                # Query the attachment page and process it
                get_attachment_page_by_rd.s(result["id"], session.cookies).set(
                    queue=q
                ),
                # Take that in a new task and make a PQ object
                make_attachment_pq_object.s(result["id"], recap_user.pk).set(
                    queue=q
                ),
                # And then process that using the normal machinery.
                process_recap_attachment.s(tag_names=[TAG_PHASE_1]).set(
                    queue=q
                ),
            ).apply_async()
            i += 1
        else:
            # Inner loop exited normally (didn't "break")
            continue
        # Inner loop broke. Break outer loop too.
        break


def get_documents(options):
    """Download documents from PACER if we don't already have them."""
    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()

    page_size = 10000
    main_query = build_main_query_from_query_string(
        Q_INVOICES,
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
            i += 1
            continue
        if i >= options["limit"] > 0:
            break
        throttle.maybe_wait()

        rd = RECAPDocument.objects.get(pk=result["id"])
        logger.info(
            "Doing item %s w/rd: %s, d: %s", i, rd.pk, result["docket_id"]
        )

        if rd.is_available:
            logger.info("Already have pk %s; just tagging it.", rd.pk)
            add_tags(rd, TAG_PHASE_2)
            i += 1
            continue

        if not rd.pacer_doc_id:
            logger.info("Unable to find pacer_doc_id for: %s", rd.pk)
            i += 1
            continue

        chain(
            get_pacer_doc_by_rd.s(rd.pk, session.cookies, tag=TAG_PHASE_2).set(
                queue=q
            ),
            extract_recap_pdf.si(rd.pk).set(queue=q),
            add_items_to_solr.si([rd.pk], "search.RECAPDocument").set(queue=q),
        ).apply_async()
        i += 1


class Command(VerboseCommand):
    help = "Get lots of invoices and their attachment pages."

    allowed_tasks = [
        "attachment_pages",
        "documents",
    ]

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
        parser.add_argument(
            "--task",
            type=str,
            required=True,
            help="What task are we doing at this point?",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        logger.info(f"Using PACER username: {PACER_USERNAME}")
        if options["task"] == "attachment_pages":
            get_attachment_pages(options)
        elif options["task"] == "documents":
            get_documents(options)
