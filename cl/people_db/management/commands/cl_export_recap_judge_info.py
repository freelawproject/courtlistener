from __future__ import print_function
from collections import Counter, OrderedDict

import pandas
from django.core.management import BaseCommand
from django.db.models import Q

from pandas import to_pickle
from unidecode import unidecode
from juriscraper.lib.judge_parsers import normalize_judge_string

from cl.search.models import Court, Docket


class Command(BaseCommand):
    help = 'Export a CSV of RECAP judges.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            default=False,
            help="Don't change the data."
        )

    def handle(self, *args, **options):
        self.debug = options['debug']
        self.options = options
        self.generate_data()

    def generate_data(self):
        """Make a CSV of the data extracted from the database.

        CSV will have the following format:
            Court, Name, Title, Count, 2000, 2011...

        {
            'ca2': {
                "harold baller": {
                    "Mag judge": {
                        "years": {
                            "1999': 22,
                            "2000': 14,
                        },
                        'total count': 36,
                    },
                }
            }
        }
        """
        courts = Court.objects.filter(jurisdiction__in=['FB', 'FD', 'F', 'FBP',
                                                        'FS'])
        out = {}
        for court in courts:
            out[court.pk] = {}
            dockets = (court.dockets
                       .exclude(Q(assigned_to_str='') & Q(referred_to_str=''))
                       .filter(source__in=Docket.RECAP_SOURCES)
                       .only('assigned_to_str', 'referred_to_str',
                             'date_filed'))
            print("Processing %s dockets in %s" % (dockets.count(), court.pk))
            for docket in dockets:
                for judge_type in ['assigned', 'referred']:
                    judge = getattr(docket, '%s_to_str' % judge_type)
                    if not judge:
                        continue

                    name, title = normalize_judge_string(unidecode(judge))
                    if not name:
                        continue
                    if name not in out[court.pk]:
                        # No entry for this person.
                        out[court.pk][name] = {
                            title: Counter([docket.date_filed.year]),
                        }
                    else:
                        # Person already exists.
                        if title not in out[court.pk][name]:
                            # Title not yet found.
                            out[court.pk][name][title] = Counter(
                                [docket.date_filed.year])
                        else:
                            # Title already exists.
                            out[court.pk][name][title][
                                docket.date_filed.year] += 1

        self.export_files(out)

    @staticmethod
    def export_files(out):
        to_pickle(out, 'recap_export.pkl')
        out_csv = []
        for court, v in out.items():
            for judge_name, data in v.items():
                for title, years in data.items():
                    row = OrderedDict([
                        ('court', court),
                        ('name', judge_name),
                        ('title', title),
                        ('total count', sum(years.values()))
                    ])
                    for year, count in years.items():
                        row[str(year)] = count
                    out_csv.append(row)
        df = pandas.DataFrame(out_csv)
        df = df[['court', 'name', 'title', 'total count'] + sorted(
            [x for x in df.columns if x.isdigit()])]
        df.to_csv('recap_export.csv', index=False)
