import os

from celery.canvas import chain
from django.conf import settings
from django.http import QueryDict
from juriscraper.pacer.http import PacerSession

from cl.corpus_importer.tasks import get_docket_by_pacer_case_id
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import build_main_query
from cl.search.forms import SearchForm
from cl.search.models import Docket
from cl.search.tasks import add_or_update_recap_docket

QUERY_STRING = 'q=&type=r&order_by=score+desc&description=%22Vacat*%22+AND+2255+AND+%22Granted%22+NOT+%22Denied%22+NOT+%22Dismiss*%22&court=dcd+almd+alnd+alsd+akd+azd+ared+arwd+cacd+caed+cand+casd+cod+ctd+ded+flmd+flnd+flsd+gamd+gand+gasd+hid+idd+ilcd+ilnd+ilsd+innd+insd+iand+iasd+ksd+kyed+kywd+laed+lamd+lawd+med+mdd+mad+mied+miwd+mnd+msnd+mssd+moed+mowd+mtd+ned+nvd+nhd+njd+nmd+nyed+nynd+nysd+nywd+nced+ncmd+ncwd+ndd+ohnd+ohsd+oked+oknd+okwd+ord+paed+pamd+pawd+rid+scd+sdd+tned+tnmd+tnwd+txed+txnd+txsd+txwd+utd+vtd+vaed+vawd+waed+wawd+wvnd+wvsd+wied+wiwd+wyd+gud+nmid+prd+vid'

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)

BAL_TAG = 'AKHBLTIIGFYYGKKY'


def make_main_query():
    """Make a main query by using the GET parameters provided by BAL."""
    qd = QueryDict(QUERY_STRING)
    search_form = SearchForm(qd)

    if not search_form.is_valid():
        logger.critial("Search form is invalid! Cannot continue")
        exit(1)

    cd = search_form.cleaned_data
    main_query = build_main_query(cd, facet=False)
    main_query['rows'] = 10000
    main_query['fl'] = ['id', 'docket_id']

    # Delete the grouping stuff. It's not needed.
    del main_query['group']
    del main_query['group.limit']
    del main_query['group.field']
    del main_query['group.sort']
    del main_query['group.ngroups']

    return main_query


def get_docket_ids(main_query):
    """Get the docket IDs for a query dict.

    :returns: a set() of docket IDs
    """
    si = ExtraSolrInterface(settings.SOLR_RECAP_URL, mode='r')
    results = si.query().add_extra(**main_query).execute()
    docket_ids = set()

    for result in results:
        docket_ids.add(result['docket_id'])

    logger.info("Got %s docket IDs back from Solr." % len(docket_ids))
    return docket_ids


def get_pacer_dockets(options, docket_pks, tag):
    """Get the pacer dockets identified by the FJC IDB rows"""
    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    for i, docket_pk in enumerate(docket_pks):
        if i >= options['count'] > 0:
            break
        throttle.maybe_wait()
        if i % 1000 == 0:
            pacer_session = PacerSession(username=PACER_USERNAME,
                                         password=PACER_PASSWORD)
            pacer_session.login()
            logger.info("Sent %s tasks to celery so far." % i)
        d = Docket.objects.get(pk=docket_pk)
        chain(
            get_docket_by_pacer_case_id.s(
                d.pacer_case_id,
                d.court_id,
                pacer_session,
                **{'tag': tag, 'show_parties_and_counsel': True,
                   'show_terminated_parties': True,
                   'show_list_of_member_cases': True}
            ).set(queue=q),
            add_or_update_recap_docket.s().set(queue=q),
        ).apply_async()


class Command(VerboseCommand):
    help = "Get dockets matching a search string from PACER."

    def add_arguments(self, parser):
        parser.add_argument(
            '--queue',
            default='batch1',
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            '--count',
            type=int,
            default=0,
            help="The number of items to do. Default is to do all of them.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        logger.info("Using PACER username: %s" % PACER_USERNAME)
        main_query = make_main_query()
        docket_ids = get_docket_ids(main_query)
        get_pacer_dockets(options, docket_ids, BAL_TAG)
