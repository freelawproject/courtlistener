import os

from celery.canvas import chain
from django.conf import settings
from juriscraper.lib.string_utils import CaseNameTweaker
from juriscraper.pacer import PacerSession

from cl.corpus_importer.tasks import make_fjc_idb_lookup_params, \
    get_pacer_case_id_and_title
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, CommandUtils, logger
from cl.lib.db_tools import queryset_generator
from cl.recap.constants import CV_2017
from cl.recap.models import FjcIntegratedDatabase
from cl.recap.tasks import merge_docket_with_idb, create_new_docket_from_idb, \
    update_docket_from_hidden_api
from cl.search.models import Docket
from cl.search.tasks import add_or_update_recap_docket

cnt = CaseNameTweaker()

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)


class Command(VerboseCommand, CommandUtils):
    help = 'Iterate over the IDB data and merge it into our existing ' \
           'datasets. Where we lack a Docket object for an item in the IDB, ' \
           'create one.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--queue',
            default='batch1',
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            '--offset',
            type=int,
            default=0,
            help="The number of items to skip before beginning. Default is to "
                 "skip none.",
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help="After doing this number, stop. This number is not additive "
                 "with the offset parameter. Default is to do all of them.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        idb_rows = FjcIntegratedDatabase.objects.filter(
            dataset_source=CV_2017,
        ).order_by('pk')
        q = options['queue']
        throttle = CeleryThrottle(queue_name=q)
        session = PacerSession(username=PACER_USERNAME,
                               password=PACER_PASSWORD)
        session.login()
        for i, idb_row in enumerate(queryset_generator(idb_rows)):
            # Iterate over all items in the IDB and find them in the Docket
            # table. If they're not there, create a new item.
            if i < options['offset']:
                continue
            if i >= options['limit'] > 0:
                break

            if i % 5000 == 0:
                # Re-authenticate just in case the auto-login mechanism isn't
                # working.
                session = PacerSession(username=PACER_USERNAME,
                                       password=PACER_PASSWORD)
                session.login()

            throttle.maybe_wait()
            ds = Docket.objects.filter(
                docket_number_core=idb_row.docket_number,
                court=idb_row.district,
            )
            count = ds.count()
            if count == 0:
                logger.info("%s: Creating new docket for IDB row: %s",
                            i, idb_row)
                params = make_fjc_idb_lookup_params(idb_row)
                chain(
                    create_new_docket_from_idb.s(idb_row.pk).set(queue=q),
                    get_pacer_case_id_and_title.s(
                        docket_number=idb_row.docket_number,
                        court_id=idb_row.district_id,
                        cookies=session.cookies,
                        **params
                    ).set(queue=q),
                    update_docket_from_hidden_api.s().set(queue=q)
                ).apply_async()

            elif count == 1:
                d = ds[0]
                logger.info("%s: Merging Docket %s with IDB row: %s",
                            i, d, idb_row)
                tasks = [
                    merge_docket_with_idb.s(d.pk, idb_row.pk).set(queue=q)
                ]
                if d.source in d.RECAP_SOURCES:
                    tasks.append(
                        add_or_update_recap_docket.si({
                            'docket_pk': d.pk,
                            'content_updated': True,
                        }).set(queue=q)
                    )
                chain(*tasks).apply_async()
            elif count > 1:
                logger.warn("%s: Unable to merge. Got %s dockets for row: %s",
                            i, count, idb_row)
