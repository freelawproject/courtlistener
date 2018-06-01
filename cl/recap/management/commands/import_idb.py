import io
import re
import sys
from datetime import date

from dateutil import parser
from django.core.management import CommandError

from cl.lib.command_utils import VerboseCommand, CommandUtils, logger
from cl.recap.constants import (
    DATASET_SOURCES, CV_OLD, CV_2017, CR_OLD, CR_2017, APP_2017, APP_OLD,
    BANKR_2017, IDB_FIELD_DATA
)
from cl.recap.models import FjcIntegratedDatabase
from cl.search.models import Court


class Command(VerboseCommand, CommandUtils):
    help = 'Import a tab-separated file as produced by FJC for their IDB'
    BAD_CHARS = re.compile(u'[\u0000\u001E]')

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

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.field_mappings = {}
        self.int_fields = []
        self.str_fields = []
        self.bool_fields = []
        self.date_fields = []
        self.court_fields = []
        self.nullable_fields = None

    @staticmethod
    def ensure_filetype_ok(filetype):
        allowed_types = [d[0] for d in DATASET_SOURCES]
        if filetype not in allowed_types:
            raise CommandError("%s not a valid filetype. Valid types are: %s" %
                               (filetype, allowed_types))

    # noinspection PySingleQuotedDocstring
    @staticmethod
    def _normalize_row_value(value):
        '''Normalize a TSV value.

        Some examples include:
            "VESSEL ""HORIZONTE"""
            "M/V ""THEODORA MARIA"" HER ENGIN"

        According to RFC 4180, double quotes in a CSV field get escaped by
        being doubled up as double-double-quotes. The solution is to strip one
        double quote off either end, and then replace double-double quotes with
        singles.

        That makes the above:
            VESSEL "HORIZONTE"
            M/V "THEODORA MARIA" HER ENGIN
        '''
        value = re.sub(r'"$', '', value)
        value = re.sub(r'^"', '', value)
        value = re.sub(r'""', '"', value)
        return value

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
                    merged_contents += value
                    row.append(self._normalize_row_value(merged_contents))
                    merging_cells = False
                    merged_contents = ''
                else:
                    merged_contents += value
            elif value.startswith('"'):
                if value.endswith('"') and len(value) > 1:
                    # Just a value in quotes, like "TOYS 'R US". And not just
                    # the " character.
                    value = self._normalize_row_value(value)
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
        self.build_field_data()

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
            if options['filetype'] == CR_2017 and row['SOURCE'] != 'CMECF':
                continue

            self.normalize_nulls(row)
            self.normalize_court_fields(row)
            self.normalize_booleans(row)
            self.normalize_dates(row)
            self.normalize_ints(row)
            if options['filetype'] in [CV_OLD, CR_OLD, APP_OLD, BANKR_2017]:
                raise NotImplementedError("This file type not yet implemented.")
            elif options['filetype'] == CV_2017:
                self.import_row(row, CV_2017)
            elif options['filetype'] == CR_2017:
                self.import_row(row, CR_2017)
            elif options['filetype'] == APP_2017:
                self.import_appellate_row(row, APP_2017)
        f.close()

    def normalize_nulls(self, row):
        """The IDB uses the value -8 to indicate a null value. Fix this
        and normalize to either a blank entry ('') or None.
        """
        for k, v in row.items():
            if v == '-8' or v == '' or v == '01/01/1900':
                if k in self.nullable_fields:
                    row[k] = None
                else:
                    row[k] = ''

    def normalize_ints(self, row):
        """Normalize any column that should be an integer"""
        for col in self.int_fields:
            if row[col] is None:
                continue
            row[col] = int(row[col])

    def normalize_dates(self, row):
        """Normalize any column that should be a date"""
        for col in self.date_fields:
            if row[col] is None:
                continue
            row[col] = parser.parse(row[col]).date()

    def normalize_booleans(self, row):
        """Normalize boolean fields"""
        for col in self.bool_fields:
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
        # Strip the leading zero if there is one. Different datasets have
        # or don't have leading zeroes, and we can't use an int for this field.
        if row['CIRCUIT'].startswith('0') and len(row['CIRCUIT']) == 2:
            row['CIRCUIT'] = row['CIRCUIT'][1]

        if row['CIRCUIT']:
            matches = Court.objects.filter(jurisdiction=Court.FEDERAL_APPELLATE,
                                           fjc_court_id=row['CIRCUIT'])
            if matches.count() == 1:
                row['CIRCUIT'] = matches[0]
            else:
                raise Exception("Unable to match CIRCUIT column value %s to "
                                "Court object" % row['CIRCUIT'])

        if row['DISTRICT']:
            if self.filetype == BANKR_2017:
                matches = Court.objects.filter(
                    jurisdiction=Court.FEDERAL_BANKRUPTCY,
                    fjc_court_id=row['DISTRICT'],
                )
            else:
                matches = Court.objects.filter(
                    jurisdiction=Court.FEDERAL_DISTRICT,
                    fjc_court_id=row['DISTRICT'],
                )

            if matches.count() == 1:
                row['DISTRICT'] = matches[0]
            else:
                raise Exception("Unable to match DISTRICT column value %s to "
                                "Court object" % row['DISTRICT'])

    def import_row(self, row, source):
        values = {}
        for k, v in row.items():
            if k in self.field_mappings:
                values[self.field_mappings[k]] = v
        FjcIntegratedDatabase.objects.create(
            dataset_source=source,
            **values
        )

    def import_appellate_row(self, row, source):
        pass

    def build_field_data(self):
        """Build up fields for the selected filetype."""
        for k, v in IDB_FIELD_DATA.items():
            if self.filetype in v['sources']:
                self.field_mappings[k] = v['field']
                if v['type'] == int:
                    self.int_fields.append(k)
                elif v['type'] == str:
                    self.str_fields.append(k)
                elif v['type'] == bool:
                    self.bool_fields.append(k)
                elif v['type'] == date:
                    self.date_fields.append(k)
                elif v['type'] == Court:
                    self.court_fields.append(k)
        self.nullable_fields = self.int_fields + self.date_fields + \
                               self.bool_fields
