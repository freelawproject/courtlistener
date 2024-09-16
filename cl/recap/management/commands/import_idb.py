import re
import sys
from datetime import date
from typing import Dict, Optional

from dateutil import parser
from django.core.management import CommandError
from django.utils.timezone import now

from cl.lib.command_utils import CommandUtils, VerboseCommand, logger
from cl.recap.constants import (
    BANKR_2017,
    CR_2017,
    CV_2017,
    CV_2020,
    CV_2021,
    CV_2022,
    DATASET_SOURCES,
    IDB_FIELD_DATA,
)
from cl.recap.models import FjcIntegratedDatabase
from cl.search.models import Court


def create_or_update_row(
    values: Dict[str, str],
) -> Optional[FjcIntegratedDatabase]:
    fjc_filters = [
        {
            "district": values["district"],
            "docket_number": values["docket_number"],
            "origin": values["origin"],
            "date_filed": values["date_filed"],
        },
        # Match on defendant (that'll work better on criminal cases). It can
        # change over time, but if we find a match that's a very strong
        # indicator and we should use it.
        {"defendant": values["defendant"]},
    ]
    existing_rows = FjcIntegratedDatabase.objects.all()
    for fjc_filter in fjc_filters:
        existing_rows = existing_rows.filter(**fjc_filter)
        existing_row_count = existing_rows.count()
        if existing_row_count == 0:
            fjc_row = FjcIntegratedDatabase.objects.create(**values)
            logger.info("Added row: %s", fjc_row)
            break
        elif existing_row_count == 1:
            existing_rows.update(date_modified=now(), **values)
            fjc_row = existing_rows[0]
            logger.info(f"Updated row: {fjc_row}")
            break
    else:
        # Didn't hit a break b/c too many matches.
        logger.warning(
            "Got %s results when looking up row by filters: %s",
            existing_row_count,
            fjc_filter,
        )
        fjc_row = None

    return fjc_row


class Command(VerboseCommand, CommandUtils):
    help = (
        "Import a tab-separated file as produced by FJC for their IDB. "
        "Do not check for duplicates."
    )
    BAD_CHARS = re.compile("[\u0000\u001E]")

    def add_arguments(self, parser):
        parser.add_argument(
            "--input-file",
            help="The IDB file to import",
            required=True,
        )
        parser.add_argument(
            "--filetype",
            help="The type of file from FJC. One of: %s"
            % "\n ".join(f"{t[0]}: {t[1]}" for t in DATASET_SOURCES),
            required=True,
            type=int,
        )
        parser.add_argument(
            "--start-line",
            help="The line to start on. Useful for crashed scripts.",
            default=-1,
            type=int,
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_mappings = {}
        self.int_fields = []
        self.str_fields = []
        self.bool_fields = []
        self.date_fields = []
        self.court_fields = []
        self.nullable_fields = None

    @staticmethod
    def ensure_filetype_ok(filetype: int) -> None:
        allowed_types = [d[0] for d in DATASET_SOURCES]
        if filetype not in allowed_types:
            raise CommandError(
                f"{filetype} not a valid filetype. Valid types are: {allowed_types}"
            )

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
        value = re.sub(r'"$', "", value)
        value = re.sub(r'^"', "", value)
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
        line = self.BAD_CHARS.sub("", line)
        row_values = line.strip().split("\t")

        # Take care of quoted characters like:
        #   col1\t"\tcol2"\tcol3
        #   col1\t"col2start\tcol2more\t"\tcol3
        row = []
        merged_contents = ""
        merging_cells = False
        for value in row_values:
            if merging_cells:
                if value.endswith('"'):
                    merged_contents += value
                    row.append(self._normalize_row_value(merged_contents))
                    merging_cells = False
                    merged_contents = ""
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
        super().handle(*args, **options)

        self.ensure_file_ok(options["input_file"])
        self.ensure_filetype_ok(options["filetype"])
        self.filetype = options["filetype"]
        self.build_field_data()

        logger.info(f"Importing IDB file at: {options['input_file']}")
        with open(
            options["input_file"], mode="r", encoding="cp1252", newline="\r\n"
        ) as f:
            col_headers = f.readline().strip().split("\t")
            for i, line in enumerate(f):
                sys.stdout.write(f"\rDoing line: {i}")
                sys.stdout.flush()
                if i < options["start_line"]:
                    continue

                row = self.make_csv_row_dict(line, col_headers)
                if options["filetype"] == CR_2017 and row["SOURCE"] != "CMECF":
                    continue

                self.normalize_nulls(row)
                self.normalize_court_fields(row)
                self.normalize_booleans(row)
                self.normalize_dates(row)
                self.normalize_ints(row)
                if options["filetype"] not in [
                    CV_2017,
                    CV_2020,
                    CV_2021,
                    CV_2022,
                    CR_2017,
                ]:
                    raise NotImplementedError(
                        "This file type not implemented."
                    )
                else:
                    values = self.convert_to_cl_data_model(
                        row, options["filetype"]
                    )
                create_or_update_row(values)

    def normalize_nulls(self, row):
        """The IDB uses the value -8 to indicate a null value. Fix this
        and normalize to either a blank entry ('') or None.
        """
        for k, v in row.items():
            if v == "-8" or v == "" or v == "01/01/1900":
                if k in self.nullable_fields:
                    row[k] = None
                else:
                    row[k] = ""

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

            if row[col] == "1":
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
        if row["CIRCUIT"].startswith("0") and len(row["CIRCUIT"]) == 2:
            row["CIRCUIT"] = row["CIRCUIT"][1]

        if row["CIRCUIT"]:
            matches = Court.federal_courts.appellate_courts().filter(
                fjc_court_id=row["CIRCUIT"],
            )
            if matches.count() == 1:
                row["CIRCUIT"] = matches[0]
            else:
                raise Exception(
                    "Unable to match CIRCUIT column value %s to "
                    "Court object" % row["CIRCUIT"]
                )

        if row["DISTRICT"]:
            if self.filetype == BANKR_2017:
                matches = Court.federal_courts.bankruptcy_courts().filter(
                    fjc_court_id=row["DISTRICT"],
                )
            else:
                matches = Court.federal_courts.district_courts().filter(
                    fjc_court_id=row["DISTRICT"],
                )

            if matches.count() == 1:
                row["DISTRICT"] = matches[0]
            else:
                raise Exception(
                    "Unable to match DISTRICT column value %s to "
                    "Court object" % row["DISTRICT"]
                )

    def convert_to_cl_data_model(self, row, source):
        """Convert the CSV dict with it's headers to our data model"""
        values = {"dataset_source": source}
        for k, v in row.items():
            if k in self.field_mappings:
                values[self.field_mappings[k]] = v
        return values

    def build_field_data(self):
        """Build up fields for the selected filetype."""
        for k, v in IDB_FIELD_DATA.items():
            if self.filetype in v["sources"]:
                self.field_mappings[k] = v["field"]
                if v["type"] == int:
                    self.int_fields.append(k)
                elif v["type"] == str:
                    self.str_fields.append(k)
                elif v["type"] == bool:
                    self.bool_fields.append(k)
                elif v["type"] == date:
                    self.date_fields.append(k)
                elif v["type"] == Court:
                    self.court_fields.append(k)
        self.nullable_fields = (
            self.int_fields + self.date_fields + self.bool_fields
        )
