import argparse

import numpy as np
import pandas as pd
from django.core.management import BaseCommand

from cl.people_db.import_judges.assign_authors import assign_authors
from cl.people_db.import_judges.judge_utils import process_date_string
from cl.people_db.import_judges.populate_fjc_judges import make_federal_judge, \
    get_fed_court_object
from cl.people_db.import_judges.populate_presidents import make_president
from cl.people_db.import_judges.populate_state_judges import make_state_judge
from cl.people_db.models import Person, Position
from cl.search.models import Court
from cl.search.tasks import add_or_update_people


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

    def import_fjc_judges(self, infile=None):
        if infile is None:
            self.ensure_input_file()
            infile = self.options['input_file']
        textfields = ['firstname', 'midname', 'lastname', 'gender',
                      'Place of Birth (City)', 'Place of Birth (State)',
                      'Place of Death (City)', 'Place of Death (State)']
        df = pd.read_excel(infile, 0)
        for x in textfields:
            df[x] = df[x].replace(np.nan, '', regex=True)
        df['Employment text field'].replace(to_replace=r';\sno', value=r', no', inplace=True, regex=True)
        for i, row in df.iterrows():
            make_federal_judge(dict(row), testing=self.debug)

    def import_state_judges(self, infile=None):
        if infile is None:
            self.ensure_input_file()
            infile = self.options['input_file']
        textfields = ['firstname', 'midname', 'lastname', 'gender', 'howended']
        df = pd.read_excel(infile, 0)
        for x in textfields:
            df[x] = df[x].replace(np.nan, '', regex=True)
        for i, row in df.iterrows():
            make_state_judge(dict(row), testing=self.debug)

    def import_presidents(self, infile=None):
        if infile is None:
            self.ensure_input_file()
            infile = self.options['input_file']
        textfields = ['firstname', 'midname', 'lastname', 'death city', 'death state']
        df = pd.read_excel(infile, 0)
        for x in textfields:
            df[x] = df[x].replace(np.nan, '', regex=True)
        for i, row in df.iterrows():
            make_president(dict(row), testing=self.debug)

    def import_all(self):
        datadir = self.options['input_file']
        print('importing presidents...')
        self.import_presidents(infile=datadir+'/presidents.xlsx')
        print('importing FJC judges...')
        self.import_fjc_judges(infile=datadir+'/fjc-data.xlsx')
        print('importing state supreme court judges...')
        self.import_state_judges(infile=datadir+'/state-supreme-court-bios-2016-04-06.xlsx')
        print('importing state IAC judges...')
        self.import_state_judges(infile=datadir+'/state-iac-bios-2016-04-06.xlsx')

    def assign_judges(self):
        print('Assigning authors...')
        assign_authors(testing=self.debug)

    def fix_fjc_positions(self, infile=None):
        """
        Addresses issue #624.

        We had some errant regexes in the district court assignments. This code
        reassigns the court fields for these judges where the new regexes
        differs from the old ones.

        :param infile: The import file with fjc-data.xslx
        :return: None
        """

        if infile is None:
            self.ensure_input_file()
            infile = self.options['input_file']
        textfields = ['firstname', 'midname', 'lastname', 'gender',
                      'Place of Birth (City)', 'Place of Birth (State)',
                      'Place of Death (City)', 'Place of Death (State)']
        df = pd.read_excel(infile, 0)
        for x in textfields:
            df[x] = df[x].replace(np.nan, '', regex=True)
        df['Employment text field'].replace(to_replace=r';\sno', value=r', no',
                                            inplace=True, regex=True)
        for i, item in df.iterrows():

            fjc_check = Person.objects.get(
                fjc_id=item['Judge Identification Number'])

            for posnum in range(1, 7):
                if posnum > 1:
                    pos_str = ' (%s)' % posnum
                else:
                    pos_str = ''

                if pd.isnull(item['Court Name' + pos_str]):
                    continue
                courtid = get_fed_court_object(item['Court Name' + pos_str])
                if courtid is None:
                    raise
                date_start = process_date_string(
                    item['Commission Date' + pos_str])
                date_recess_appointment = process_date_string(
                    item['Recess Appointment date' + pos_str])
                if pd.isnull(date_start) and not pd.isnull(
                        date_recess_appointment):
                    date_start = date_recess_appointment
                if pd.isnull(date_start):
                    # if still no start date, skip
                    continue
                position = Position.objects.get(person=fjc_check,
                                                date_start=date_start)

                if position.court.pk == courtid:
                    print "Court IDs are both %s. No changes made." % courtid
                    continue
                else:
                    print "Court IDs are different! Old: %s, New: %s" % (
                        position.court.pk, courtid)
                    court = Court.objects.get(pk=courtid)
                    position.court = court

                    if not self.debug:
                        position.save()
                        add_or_update_people.delay([position.person.pk])

    VALID_ACTIONS = {
        'import-fjc-judges': import_fjc_judges,
        'import-state-judges': import_state_judges,
        'import-presidents': import_presidents,
        'import-all': import_all,
        'assign-judges': assign_judges,
        'fix-fjc-positions': fix_fjc_positions,
    }


