import os

from celery.canvas import chain
from django.conf import settings
from juriscraper.pacer.http import PacerSession
from requests import Session

from cl.corpus_importer.tasks import get_docket_by_pacer_case_id
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import build_main_query_from_query_string
from cl.search.models import Docket
from cl.search.tasks import add_or_update_recap_docket

# Do not order by score!
QUERY_STRING = "q=entry_date_filed%3A%5B2018-05-01T00%3A00%3A00Z+TO+*%5D&type=r&order_by=dateFiled+asc&description=%22Vacat*%22+AND+2255+AND+%22Granted%22+NOT+%22Denied%22+NOT+%22Dismiss*%22&court=dcd+almd+alnd+alsd+akd+azd+ared+arwd+cacd+caed+cand+casd+cod+ctd+ded+flmd+flnd+flsd+gamd+gand+gasd+hid+idd+ilcd+ilnd+ilsd+innd+insd+iand+iasd+ksd+kyed+kywd+laed+lamd+lawd+med+mdd+mad+mied+miwd+mnd+msnd+mssd+moed+mowd+mtd+ned+nvd+nhd+njd+nmd+nyed+nynd+nysd+nywd+nced+ncmd+ncwd+ndd+ohnd+ohsd+oked+oknd+okwd+ord+paed+pamd+pawd+rid+scd+sdd+tned+tnmd+tnwd+txed+txnd+txsd+txwd+utd+vtd+vaed+vawd+waed+wawd+wvnd+wvsd+wied+wiwd+wyd+gud+nmid+prd+vid"

PACER_USERNAME = os.environ.get("PACER_USERNAME", settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get("PACER_PASSWORD", settings.PACER_PASSWORD)

BAL_TAG = "AKHBLTIIGFYYGKKY"
BAL_TAG_2019 = "AKHBLTIIGFYYGKKY-2019"


def get_docket_ids(main_query):
    """Get the docket IDs for a query dict.

    :returns: a set() of docket IDs
    """
    with Session() as session:
        si = ExtraSolrInterface(
            settings.SOLR_RECAP_URL, http_connection=session, mode="r"
        )
        results = si.query().add_extra(**main_query).execute()
    docket_ids = set()

    for result in results:
        docket_ids.add(result["docket_id"])

    logger.info(f"Got {len(docket_ids)} docket IDs back from Solr.")
    return docket_ids


def get_pacer_dockets(options, docket_pks, tags):
    """Get the pacer dockets identified by the FJC IDB rows"""
    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    pacer_session = None
    for i, docket_pk in enumerate(docket_pks):
        if i < options["offset"]:
            continue
        if i >= options["limit"] > 0:
            break
        throttle.maybe_wait()
        if i % 1000 == 0 or pacer_session is None:
            pacer_session = PacerSession(
                username=PACER_USERNAME, password=PACER_PASSWORD
            )
            pacer_session.login()
            logger.info(f"Sent {i} tasks to celery so far.")
        d = Docket.objects.get(pk=docket_pk)
        chain(
            get_docket_by_pacer_case_id.s(
                {"pacer_case_id": d.pacer_case_id, "docket_pk": d.pk},
                d.court_id,
                cookies=pacer_session.cookies,
                tag_names=tags,
                **{
                    "show_parties_and_counsel": True,
                    "show_terminated_parties": True,
                    "show_list_of_member_cases": False,
                },
            ).set(queue=q),
            add_or_update_recap_docket.s().set(queue=q),
        ).apply_async()


class Command(VerboseCommand):
    help = "Get dockets matching a search string from PACER."

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
        main_query = build_main_query_from_query_string(
            QUERY_STRING,
            {"rows": 10000, "fl": ["id", "docket_id"]},
            {"group": False, "facet": False, "highlight": False},
        )
        docket_ids = get_docket_ids(main_query)
        get_pacer_dockets(options, docket_ids, [BAL_TAG, BAL_TAG_2019])
