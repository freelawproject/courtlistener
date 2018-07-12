import csv
import os
from datetime import datetime, timedelta

from celery.canvas import chain
from django.conf import settings
from django.db.models import Q
from juriscraper.pacer import PacerSession
from reporters_db import CASE_NAME_ABBREVIATIONS
from requests.structures import CaseInsensitiveDict

from cl.corpus_importer.tasks import get_pacer_case_id_and_title, \
    get_docket_by_pacer_case_id
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import CommandUtils
from cl.lib.command_utils import VerboseCommand, logger
from cl.recap.constants import CV_2017
from cl.recap.models import FjcIntegratedDatabase
from cl.search.models import Court
from cl.search.tasks import add_or_update_recap_docket

# Case insensitive dict for abbreviation lookups.
CASE_NAME_IABBREVIATIONS = CaseInsensitiveDict(CASE_NAME_ABBREVIATIONS)

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)

TAG = 'yDVxdAsAKSixdsoM'

"""
This file contains some of the work product of our collaboration with GSU. The
process we went through for this project was:
   
 - They provided a spreadsheet with case names, jurisdictions, and dates.
  
 - We took that spreadsheet and looked up anything we could in our IDB DB.
 
 - That didn't always work, so we provided a spreadsheet of missing values
   back to GSU.
   
 - Students then completed the missing values, which we merged back into our
   spreadsheet.
   
 - From there, we used the new spreadsheet to look up the new and old values
   and download them.
   
 - Once the docket is downloaded, we get the docket entries matching the dates
   on the spreadsheet. 
   
All of this process is summarized in an email dated 2018-04-17. 
"""


def make_party_q(party, lookup_field, term_slice):
    """Make a Q object from a plaintiff or defendant string.

    Takes care of annoying things like normalizing abbreviations and ORing
    together the rest of the words. Makes for a pretty inefficient query, but
    better to get a hit than to not.
    :param party: The string representing the party
    :param lookup_field: The field to do lookups against
    :param term_slice: A python slice object representing the slice of the party
    parameter to use for queries.
    """
    # Set up Q objects with the first three words from plaintiff & defendant.
    new_q = Q()
    for word in party.split()[term_slice]:
        if word.endswith('.') and word in CASE_NAME_IABBREVIATIONS:
            # Lookup the word, and make an OR query.
            q = Q(**{'%s__icontains' % lookup_field: word})
            for abbrev in CASE_NAME_IABBREVIATIONS[word]:
                q |= Q(**{'%s__icontains' % lookup_field: abbrev})
        else:
            q = Q(**{'%s__icontains' % lookup_field: word})
        new_q &= q
    return new_q


def lookup_row(row):
    """Lookup the row provided in the FJC DB.

    :param row: A row dict as pulled from the CSV using the csv DictReader
    :returns int: The PK of the row that matched.
    """
    try:
        plaintiff, defendant = row['Case Name'].lower().split(' v. ', 1)
    except IndexError:
        logger.warn("Unable to find ' v. ' in case name.")
        return
    except ValueError:
        logger.warn("Got multiple ' v. ' in the case name.")
        return
    opinion_date = datetime.strptime(row['Date'], '%m/%d/%Y')
    orig_query = FjcIntegratedDatabase.objects.filter(
        # All of these are civil.
        dataset_source=CV_2017,
        # Ensure the correct court.
        district__fjc_court_id=row['AO ID'],
        # The docket must have been filed *before* the date of the opinion.
        date_filed__lte=opinion_date,
        # But not more than five years prior to the opinion.
        date_filed__gte=opinion_date - timedelta(days=365 * 5),
    ).exclude(
        # FJC Ids are duplicated across bankruptcy and district. Since we only
        # know the FJC court ID, just exclude bankruptcy cases as a rule. That
        # will ensure we limit ourselves to the correct jurisdiction.
        district__jurisdiction=Court.FEDERAL_BANKRUPTCY,
    ).order_by('-date_filed')

    # Start with the strictest, then broaden when you fail. Truncate at 30
    # chars (that's all the field can contain).
    filter_tuples = [(
        # Try an exact match on case name.
        (),
        {
            'plaintiff__iexact': plaintiff[:30],
            'defendant__iexact': defendant[:30],
        }
    ), (
        # Try a starts with match on case name.
        (),
        {
            'plaintiff__istartswith': plaintiff[:30],
            'defendant__istartswith': defendant[:30],
        }
    ), (
        # To to find a match that contains the first three words from the
        # plaintiff and defendant (in any order). Note Q objects are args, not
        # kwargs, hence different format here.
        (make_party_q(defendant, 'defendant', slice(None, 3)),
         make_party_q(plaintiff, 'plaintiff', slice(None, 3))),
        {},
    ), (
        # Broaden. Try just the first word from plaintiff & defendant matching.
        (make_party_q(defendant, 'defendant', slice(None, 1)),
         make_party_q(plaintiff, 'plaintiff', slice(None, 1))),
        {},
    ), (
        # Explore. Try the second word of the plaintiff instead. It's often a
        # last name and worth a try.
        (make_party_q(plaintiff, 'plaintiff', slice(1, 2)),
         make_party_q(defendant, 'defendant', slice(None, 1))),
        {},
    )]

    for args, kwargs in filter_tuples:
        results = orig_query.filter(*args, **kwargs)
        count = results.count()
        if count == 0:
            logger.warn("Unable to find result (args: %s, kwargs: %s). "
                        "Broadening if possible." % (args, kwargs))
            continue
        if count == 1:
            logger.info("Got one result. Bingo (args: %s, kwargs: %s)." %
                        (args, kwargs))
            return results[0]
        elif 5 > count > 1:
            logger.info("Got %s results. Choosing closest to document date." %
                        count)
            return results[0]
        else:
            logger.warn("Got too many results. Cannot identify correct case "
                        "(args: %s, kwargs: %s)." % (args, kwargs))
            return


def update_csv_with_idb_lookups(options):
    """Take in the CSV from the command line and update it with fields from
    our local IDB database, if we can find the value in there.
    """
    with open(options['input_file'], 'r') as f, \
            open('/tmp/final-pull-annotated.csv', 'wb') as o:
        dialect = csv.Sniffer().sniff(f.read(1024))
        f.seek(0)
        reader = csv.DictReader(f, dialect=dialect)
        out_fields = reader.fieldnames + ['fjc_id', 'docket_number',
                                          'case_name']
        writer = csv.DictWriter(o, fieldnames=out_fields)
        writer.writeheader()
        for i, row in enumerate(reader):
            if i < options['offset']:
                continue
            if i >= options['limit'] > 0:
                break
            logger.info("Doing row with contents: '%s'" % row)
            result = lookup_row(row)
            logger.info(result)
            if result is not None:
                row.update({
                    'fjc_id': result.pk,
                    'docket_number': result.docket_number,
                    'case_name': '%s v. %s' % (result.plaintiff,
                                               result.defendant)
                })
            if not options['log_only']:
                writer.writerow(row)


def download_dockets(options):
    """Download dockets listed in the spreadsheet."""
    with open(options['input_file'], 'r') as f:
        dialect = csv.Sniffer().sniff(f.read(1024))
        f.seek(0)
        reader = csv.DictReader(f, dialect=dialect)
        q = options['queue']
        throttle = CeleryThrottle(queue_name=q)
        session = PacerSession(username=PACER_USERNAME,
                               password=PACER_PASSWORD)
        session.login()
        for i, row in enumerate(reader):
            if i < options['offset']:
                continue
            if i >= options['limit'] > 0:
                break
            throttle.maybe_wait()

            logger.info("Doing row %s: %s", i, row)
            if row['idb_docket_number']:
                # Zero-pad the docket number up to seven digits because Excel
                # ate the leading zeros that these would normally have.
                docket_number = row['idb_docket_number'].rjust(7, '0')
            elif row['student_docket_number']:
                # Use the values collected by student
                # researchers, then cleaned up my mlr.
                docket_number = row['student_docket_number']
            else:
                # No docket number; move on.
                continue
            court = Court.objects.get(fjc_court_id=row['AO ID'].rjust(2, '0'),
                                      jurisdiction=Court.FEDERAL_DISTRICT)
            chain(
                get_pacer_case_id_and_title.s(
                    docket_number=docket_number,
                    court_id=court.pk,
                    cookies=session.cookies,
                    case_name=row['Case Name'],
                ).set(queue=q),
                get_docket_by_pacer_case_id.s(
                    court_id=court.pk,
                    cookies=session.cookies,
                    tag=TAG,
                ).set(queue=q),
                add_or_update_recap_docket.s().set(queue=q),
            ).apply_async()


class Command(VerboseCommand, CommandUtils):
    help = "Do tasks related to GSU DoL project"

    allowed_tasks = [
        'lookup_in_idb',
        'download_dockets',
        'download_documents',
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            '--queue',
            default='batch1',
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            '--input-file',
            help="The CSV file containing the data to analyze.",
            required=True,
        )
        parser.add_argument(
            '--log-only',
            action="store_true",
            default=False,
            help="Only log progress, don't do anything."
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
        parser.add_argument(
            '--task',
            type=str,
            required=True,
            help="What task are we doing at this point?",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        self.ensure_file_ok(options['input_file'])

        if options['task'] == 'lookup_in_idb':
            update_csv_with_idb_lookups(options)
        elif options['task'] == 'download_dockets':
            download_dockets(options)
