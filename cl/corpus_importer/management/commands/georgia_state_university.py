import csv
from datetime import datetime, timedelta

from cl.lib.command_utils import VerboseCommand, CommandUtils, logger
from cl.recap.constants import CV_2017
from cl.recap.models import FjcIntegratedDatabase
from cl.search.models import Court


def lookup_row(row):
    """Lookup the row provided in the FJC DB.

    :param row: A row dict as pulled from the CSV using the csv DictReader
    :returns int: The PK of the row that matched.
    """
    plaintiff, defendant = row['Case Name'].split(' v. ', 1)
    opinion_date = datetime.strptime(row['Date'], '%m/%d/%Y')
    results = FjcIntegratedDatabase.objects.filter(
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
    )

    # Start with the strictest, then broaden when you fail. Truncate at 30
    # chars (that's all the field can contain).
    kwarg_filters = [{
        'plaintiff__iexact': plaintiff[:30],
        'defendant__iexact': defendant[:30],
    }, {
        'plaintiff__istartswith': plaintiff[:30],
        'defendant__istartswith': defendant[:30],
    }]

    for kwargs in kwarg_filters:
        results = results.filter(**kwargs)
        count = results.count()
        if count == 0:
            logger.warn("Unable to find result (%s)." % kwargs)
            continue
        if count == 1:
            logger.info("Got one result. Bingo.")
            return results[0]
        elif count > 1:
            logger.info("Got too many results. Refining further.")
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

        with open(options['input_file'], 'r') as f:
            dialect = csv.Sniffer().sniff(f.read(1024))
            f.seek(0)
            reader = csv.DictReader(f, dialect=dialect)
            for i, row in enumerate(reader):
                if i < options['offset']:
                    continue
                if i >= options['limit'] > 0:
                    break
                logger.info("Doing row with contents: '%s'" % row)
                result = lookup_row(row)
                logger.info(result)
