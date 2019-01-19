import os

from django.conf import settings
from juriscraper.pacer import PacerSession

from cl.corpus_importer.tasks import get_pacer_case_id_and_title, \
    make_fjc_idb_lookup_params
from cl.lib.command_utils import VerboseCommand, CommandUtils, logger
from cl.lib.db_tools import queryset_generator
from cl.recap.constants import CV_2017
from cl.recap.models import FjcIntegratedDatabase
from cl.search.models import Docket

from juriscraper.lib.string_utils import CaseNameTweaker

from cl.search.tasks import add_or_update_recap_docket

cnt = CaseNameTweaker()

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)


def create_new_docket_from_idb(idb_row):
    """Create a new docket for the IDB item found. Populate it with all
    applicable fields.

    :param idb_row: An FjcIntegratedDatabase object with which to create a
    Docket.
    :return Docket: The created Docket object.
    """
    case_name = idb_row.plaintiff + ' v. ' + idb_row.defendant
    d = Docket.objects.create(
        source=Docket.IDB,
        court=idb_row.district,
        idb_data=idb_row,
        date_filed=idb_row.date_filed,
        date_terminated=idb_row.date_terminated,
        case_name=case_name,
        case_name_short=cnt.make_case_name_short(case_name),
        docket_number_core=idb_row.docket_number,
        nature_of_suit=idb_row.get_nature_of_suit_display(),
        jurisdiction_type=idb_row.get_jurisdiction_display(),
    )
    d.save()
    return d


def merge_docket_with_idb(d, idb_row):
    """Merge an existing docket with an idb_row.

    :param d: A Docket object to update.
    :param idb_row: A FjcIntegratedDatabase object to use as a source for
    updates.
    :return None
    """
    d.add_idb_source()
    d.idb_data = idb_row
    d.date_filed = d.date_filed or idb_row.date_filed
    d.date_terminated = d.date_terminated or idb_row.date_terminated
    d.nature_of_suit = d.nature_of_suit or idb_row.get_nature_of_suit_display()
    d.jurisdiction_type = d.jurisdiction_type or \
        idb_row.get_jurisdiction_display()
    d.save()


class Command(VerboseCommand, CommandUtils):
    help = 'Iterate over the IDB data and merge it into our existing ' \
           'datasets. Where we lack a Docket object for an item in the IDB, ' \
           'create one.'

    def add_arguments(self, parser):
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

            ds = Docket.objects.filter(
                docket_number_core=idb_row.docket_number,
                court=idb_row.court,
            )
            count = ds.count()
            if count == 0:
                logger.info("%s: Creating new docket for IDB row: %s",
                            i, idb_row)
                d = create_new_docket_from_idb(idb_row)

                # Item created. Now get the pacer_case_id, and docket number
                params = make_fjc_idb_lookup_params(idb_row)
                data = get_pacer_case_id_and_title(
                    docket_number=idb_row.docket_number,
                    court_id=idb_row.district_id,
                    cookies=session.cookies,
                    **params
                )
                if data is not None:
                    d.docket_number = data['docket_number']
                    d.pacer_case_id = data['pacer_case_id']
                    d.save()
            elif count == 1:
                d = ds[0]
                logger.info("%s: Merging Docket %s with IDB row: %s",
                            i, d, idb_row)
                merge_docket_with_idb(d, idb_row)
                add_or_update_recap_docket({
                    'docket_pk': d.pk,
                    'content_updated': True,
                })
            elif count > 1:
                logger.warn("%s: Unable to merge. Got %s dockets for row: %s",
                            i, count, idb_row)
