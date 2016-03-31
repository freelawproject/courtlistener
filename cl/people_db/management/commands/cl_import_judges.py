import argparse

import numpy as np
import pandas as pd

from django.core.management import BaseCommand

from cl.people_db.import_judges.populate_state_judges import make_state_judge
from cl.people_db.import_judges.populate_fjc_judges import make_federal_judge


class Command(BaseCommand):
    help = 'Import judge data from various files.'

    def valid_actions(self, s):
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s" % (
                    ', '.join(self.VALID_ACTIONS.keys())
                )
            )

        return self.VALID_ACTIONS[s]

    def ensure_input_file(self):
        if not self.options['input_file']:
            raise argparse.ArgumentTypeError(
                "--input_file is a required argument for this action."
            )

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            default=False,
            help="Don't change the data."
        )
        parser.add_argument(
            '--action',
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: %s" % (
                ', '.join(self.VALID_ACTIONS.keys())
            )
        )
        parser.add_argument(
            '--input_file',
            help='The input file required for certain operations.'
        )

    def handle(self, *args, **options):
        self.debug = options['debug']
        self.options = options

        # Run the requested method.
        self.options['action'](self)

    def import_fjc_judges(self):
        self.ensure_input_file()
        textfields = ['firstname', 'midname', 'lastname', 'gender',
                      'Place of Birth (City)', 'Place of Birth (State)',
                      'Place of Death (City)', 'Place of Death (State)']
        df = pd.read_excel(self.options['input_file'], 0)
        for x in textfields:
            df[x] = df[x].replace(np.nan, '', regex=True)

        for i, row in df.iterrows():
            make_federal_judge(dict(row), testing=self.debug)

    def import_state_judges(self):
        self.ensure_input_file()
        textfields = ['firstname', 'midname', 'lastname', 'gender', 'howended']
        df = pd.read_excel(self.options['input_file'], 0)
        for x in textfields:
            df[x] = df[x].replace(np.nan, '', regex=True)
        for i, row in df.iterrows():
            make_state_judge(dict(row), testing=self.debug)

    VALID_ACTIONS = {
        'import-fjc-judges': import_fjc_judges,
        'import-state-judges': import_state_judges,
    }


