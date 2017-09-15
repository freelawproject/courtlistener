import io
import os
import re
import sys

from dateutil import parser
from django.core.management import CommandError

from cl.lib.command_utils import VerboseCommand, logger
from cl.recap.constants import DATASET_SOURCES, CV_OLD, CV_2017, CR_OLD, \
    CR_2017, APP_2017, APP_OLD, BANKR_2017, idb_field_mappings
from cl.recap.models import FjcIntegratedDatabase
from cl.search.models import Court


class Command(VerboseCommand):
    help = 'Import a tab-separated file as produced by FJC for their IDB'
    BAD_CHARS = re.compile(u'[\u0000\u001E]')

    INT_FIELDS = ['DOCKET', 'ORIGIN', 'JURIS', 'NOS', 'RESIDENC', 'DEMANDED',
                  'COUNTY', 'TRCLACT', 'PROCPROG', 'DISP', 'NOJ', 'AMTREC',
                  'JUDGMENT', 'PROSE', 'TAPEYEAR']
    DATE_FIELDS = ['FILEDATE', 'TRANSDAT', 'TERMDATE']
    BOOL_FIELDS = ['CLASSACT']
    NULLABLE_FIELDS = INT_FIELDS + DATE_FIELDS + BOOL_FIELDS

    def add_arguments(self, parser):
        parser.add_argument(
            '--input-file',
            help="The IDB file to import",
            required=True,
        )
        parser.add_argument(
            '--filetype',
            help="The type of file from FJC. One of: %s" % '\n '.join(
                '%s: %s' % (t[0], t[1]) for t in DATASET_SOURCES),
            required=True,
            type=int,
        )
        parser.add_argument(
            '--start-line',
            help="The line to start on. Useful for crashed scripts.",
            default=-1,
            type=int,
        )

    @staticmethod
    def ensure_file_ok(file_path):
        if not os.path.exists(file_path):
            raise CommandError("Unable to find file at %s" % file_path)
        if not os.access(file_path, os.R_OK):
            raise CommandError("Unable to read file at %s" % file_path)

    @staticmethod
    def ensure_filetype_ok(filetype):
        allowed_types = [d[0] for d in DATASET_SOURCES]
        if filetype not in allowed_types:
            raise CommandError("%s not a valid filetype. Valid types are: %s" %
                               (filetype, allowed_types))

    def make_csv_row_dict(self, line, col_headers):
        """Because the PACER data is so nasty, we need our own CSV parser. I
        guess this is how we learn, by doing things at lower and lower levels.
        For that, I thank PACER. In any case, this little guy takes in a line of
        text from a PACER file, and makes it into a nice dict of data.

        Along the way, it:
         1. Removes bad characters, like null values, information separators,
         and tabs
         2. Handles splitting on the tab character with quotechar = '"'
        """
        line = self.BAD_CHARS.sub('', line)
        row_values = line.strip().split('\t')

        # Take care of quoted characters like:
        #   col1\t"\tcol2"\tcol3
        #   col1\t"col2start\tcol2more\t"\tcol3
        row = []
        merged_contents = ''
        merging_cells = False
        for value in row_values:
            if merging_cells:
                if value.endswith('"'):
                    merging_cells = False
                    merged_contents += value
                    row.append(merged_contents.strip('"'))
                else:
                    merged_contents += value
            elif value.startswith('"'):
                if value.endswith('"') and len(value) > 1:
                    # Just a value in quotes, like "TOYS 'R US". And not just
                    # the " character.
                    row.append(value)
                else:
                    merging_cells = True
                    merged_contents = value
            else:
                row.append(value)

        # Convert to dict with column headers as keys.
        row_dict = {}
        for row_value, col_header in zip(row, col_headers):
            row_dict[col_header] = row_value

        return row_dict

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        self.ensure_file_ok(options['input_file'])
        self.ensure_filetype_ok(options['filetype'])
        self.filetype = options['filetype']
        logger.info("Importing IDB file at: %s" % options['input_file'])
        f = io.open(options['input_file'], mode='r', encoding='cp1252',
                    newline="\r\n")
        col_headers = f.next().strip().split('\t')
        for i, line in enumerate(f):
            sys.stdout.write('\rDoing line: %s' % i)
            sys.stdout.flush()
            if i < options['start_line']:
                continue

            row = self.make_csv_row_dict(line, col_headers)
            self.normalize_nulls(row)
            self.normalize_court_fields(row)
            self.normalize_booleans(row)
            self.normalize_dates(row)
            self.normalize_ints(row)
            if options['filetype'] == CV_OLD:
                raise NotImplementedError("This file type not yet implemented.")
            elif options['filetype'] == CV_2017:
                self.import_civil_row(row, CV_2017)
            elif options['filetype'] == CR_OLD:
                raise NotImplementedError("This file type not yet implemented.")
            elif options['filetype'] == CR_2017:
                self.import_criminal_row(row)
            elif options['filetype'] == APP_OLD:
                raise NotImplementedError("This file type not yet implemented.")
            elif options['filetype'] == APP_2017:
                self.import_appellate_row(row)
            elif options['filetype'] == BANKR_2017:
                raise NotImplementedError("This file type not yet implemented.")
        f.close()

    def normalize_nulls(self, row):
        """The IDB uses the value -8 to indicate a null value. Fix this
        and normalize to either a blank entry ('') or None.
        """
        for k, v in row.items():
            if v == '-8' or v == '':
                if k in self.NULLABLE_FIELDS:
                    row[k] = None
                else:
                    row[k] = ''

    def normalize_ints(self, row):
        """Normalize any column that should be an integer"""
        for col in self.INT_FIELDS:
            if row[col] is None:
                continue
            row[col] = int(row[col])

    def normalize_dates(self, row):
        """Normalize any column that should be a date"""
        for col in self.DATE_FIELDS:
            if row[col] is None:
                continue
            row[col] = parser.parse(row[col]).date()

    def normalize_booleans(self, row):
        """Normalize boolean fields"""
        for col in self.BOOL_FIELDS:
            if row[col] is None:
                continue

            if row[col] == '1':
                row[col] = True
            else:
                row[col] = False

    def normalize_court_fields(self, row):
        """Convert the court values into CL court values.

        Because FJC IDs are the same for a district and a bankruptcy court in a
        jurisdiction, use different logic for bankruptcy data.
        """
        if row['CIRCUIT']:
            matches = Court.objects.filter(jurisdiction='F',
                                           fjc_court_id=row['CIRCUIT'])
            if matches.count() == 1:
                row['CIRCUIT'] = matches[0]
            else:
                raise Exception("Unable to match CIRCUIT column value %s to "
                                "Court object" % row['CIRCUIT'])

        if row['DISTRICT']:
            if self.filetype == BANKR_2017:
                matches = Court.objects.filter(jurisdiction="FB",
                                               fjc_court_id=row['DISTRICT'])
            else:
                matches = Court.objects.filter(jurisdiction="FD",
                                               fjc_court_id=row['DISTRICT'])

            if matches.count() == 1:
                row['DISTRICT'] = matches[0]
            else:
                raise Exception("Unable to match CIRCUIT column value %s to "
                                "Court object" % row['CIRCUIT'])

    @staticmethod
    def import_civil_row(row, source):
        values = {}
        for k, v in row.items():
            if k in idb_field_mappings:
                values[idb_field_mappings[k]] = v
        FjcIntegratedDatabase.objects.create(
            dataset_source=source,
            **values
        )

    def import_criminal_row(self, csv_reader):
        pass

    def import_appellate_row(self, csv_reader):
        pass
