"""Import federal, magistrate, and bankruptcy judges from CSV files."""

import argparse

import numpy as np
import pandas as pd
from django.core.exceptions import ValidationError

from cl.lib.command_utils import VerboseCommand
from cl.people_db.import_judges.populate_fjc_judges import (
    make_federal_judge,
    make_mag_bk_judge,
)
from cl.search.models import Court


class Command(VerboseCommand):
    """Run a judge import action on an input file."""

    help = "Import judge data from various files."

    def valid_actions(self, s):
        """Look up the action method named by ``s``.

        ``s`` is validated in lowercase but looked up as given.

        Raises:
            argparse.ArgumentTypeError: If ``s``, lowercased, isn't a valid
                action.
        """
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: {}".format(
                    ", ".join(self.VALID_ACTIONS.keys())
                )
            )

        return self.VALID_ACTIONS[s]

    def ensure_input_file(self):
        """Check that an input file was given.

        Raises:
            argparse.ArgumentTypeError: If no input file was given.
        """
        if not self.options["input_file"]:
            raise argparse.ArgumentTypeError(
                "--input_file is a required argument for this action."
            )

    def add_arguments(self, parser):
        """Add the offset, limit, debug, action, input file, and jurisdiction options."""
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
        parser.add_argument(
            "--debug",
            action="store_true",
            default=False,
            help="Don't change the data.",
        )
        parser.add_argument(
            "--action",
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: {}".format(
                ", ".join(self.VALID_ACTIONS.keys())
            ),
        )
        parser.add_argument(
            "--input_file",
            help="The input file required for certain operations.",
        )
        parser.add_argument(
            "--jurisdictions",
            help="A list of jurisdiction abbreviations for use with the "
            "assign-authors command. If no value is provided it will "
            "default to all jurisdictions. Valid options are:\n{}".format(
                ", ".join(f"{j[0]} ({j[1]})" for j in Court.JURISDICTIONS)
            ),
            nargs="*",
        )

    def handle(self, *args, **options):
        """Run the chosen action."""
        super().handle(*args, **options)
        self.debug = options["debug"]
        self.options = options

        # Run the requested method.
        self.options["action"](self)

    def import_fjc_judges(self, infile=None):
        """Create federal judges from the rows of an FJC CSV, within the offset and limit.

        Uses ``--input_file`` if ``infile`` isn't given.
        """
        if infile is None:
            self.ensure_input_file()
            infile = self.options["input_file"]
        textfields = [
            "First Name",
            "Middle Name",
            "Last Name",
            "Gender",
            "Birth City",
            "Birth State",
            "Death City",
            "Death State",
        ]
        df = pd.read_csv(infile)
        df = df.replace(r"^\s+$", np.nan, regex=True)
        for x in textfields:
            df[x] = df[x].fillna("")
        # Assign the result back rather than using inplace=True: df[col] is a
        # temporary Series, so an inplace call on it is chained assignment,
        # which pandas 3's copy-on-write silently turns into a no-op.
        df["Professional Career"] = df["Professional Career"].replace(
            to_replace=r";\sno", value=r", no", regex=True
        )
        for i, row in df.iterrows():
            if i < self.options["offset"]:
                continue
            if i >= self.options["limit"] > 0:
                break
            make_federal_judge(dict(row), testing=self.debug)

    def process_mag_bk_entries(self, df):
        """Create magistrate and bankruptcy judges from a dataframe's rows, within the offset and limit.

        Rows that fail validation are collected and printed at the end.
        """
        bad_record = []

        textfields = [
            "NAME_FIRST",
            "NAME_MIDDLE",
            "NAME_LAST",
            "NAME_SUFFIX",
            "GENDER",
            "POSITION",
            "COURT",
            "START_DATE",
            "START_DATE_GRANULARITY",
            "END_DATE",
            "END_DATE_GRANULARITY",
        ]

        for x in textfields:
            df[x] = df[x].fillna("")
        for i, row in df.iterrows():
            if i < self.options["offset"]:
                continue
            if i >= self.options["limit"] > 0:
                break
            try:
                make_mag_bk_judge(dict(row), testing=self.debug)
            except ValidationError as e:
                bad_record.append(e[0])

        for b in bad_record:
            print(b)

    def import_mag_bk_judges(self, infile=None):
        """Create magistrate and bankruptcy judges from the CSV rows that have a start date granularity.

        Uses ``--input_file`` if ``infile`` isn't given.
        """
        if infile is None:
            self.ensure_input_file()
            infile = self.options["input_file"]
        df = pd.read_csv(infile)
        has_date = df["START_DATE_GRANULARITY"].notnull()
        df = df[has_date]
        df = df.replace(r"^\s+$", np.nan, regex=True)
        self.process_mag_bk_entries(df)

    VALID_ACTIONS = {
        "import-fjc-judges": import_fjc_judges,
        "import-mag-bk-judges": import_mag_bk_judges,
    }
