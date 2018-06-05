import csv
from datetime import datetime, timedelta

from django.db.models import Q
from reporters_db import CASE_NAME_ABBREVIATIONS
from requests.structures import CaseInsensitiveDict

from cl.lib.command_utils import VerboseCommand, CommandUtils, logger
from cl.recap.constants import CV_2017
from cl.recap.models import FjcIntegratedDatabase
from cl.search.models import Court

# Case insensitive dict for abbreviation lookups.
CASE_NAME_IABBREVIATIONS = CaseInsensitiveDict(CASE_NAME_ABBREVIATIONS)


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


class Command(VerboseCommand, CommandUtils):
    help = "Do tasks related to GSU DoL project"

    def add_arguments(self, parser):
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

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        self.ensure_file_ok(options['input_file'])

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
